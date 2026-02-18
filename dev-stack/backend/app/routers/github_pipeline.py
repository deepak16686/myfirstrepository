"""
File: github_pipeline.py
Purpose: Provides the full lifecycle for GitHub Actions workflow generation -- chat interface,
    YAML/Dockerfile generation with LLM validation, commit to Gitea, build monitoring via
    Gitea Actions API, reinforcement-learning feedback, and self-healing fix loops.
When Used: Invoked by the frontend GitHub Actions tool card chat and API calls when a user pastes
    a Gitea repo URL to generate a workflow, approves a commit, or monitors a running Gitea
    Actions build via the /github-pipeline/* routes.
Why Created: Mirrors the Jenkins pipeline router architecture but targets Gitea Actions (GitHub
    Actions compatible) workflows under the github-projects Gitea org, with its own chat state,
    URL translation, and Gitea Actions-specific monitoring logic.
"""
import re
import uuid
import asyncio
import hashlib
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.config import settings
from app.services.github_pipeline import github_pipeline_generator
from app.services.github_pipeline.learning import (
    get_relevant_feedback,
    store_feedback as store_rl_feedback,
    record_build_result as rl_record_build_result,
    compare_and_learn,
)
from app.services.github_pipeline.image_seeder import ensure_images_in_nexus
from app.services.github_llm_fixer import github_llm_fixer
from app.services.pipeline_progress import progress_store
from app.integrations.llm_provider import get_active_provider_name

router = APIRouter(prefix="/github-pipeline", tags=["GitHub Actions Pipeline"])


# ============================================================================
# Request/Response Models
# ============================================================================

class AnalyzeRequest(BaseModel):
    repo_url: str
    github_token: str


class GenerateWorkflowRequest(BaseModel):
    repo_url: str
    github_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    use_template_only: bool = False
    runner_type: str = "self-hosted"


class GenerateWithValidationRequest(BaseModel):
    repo_url: str
    github_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    use_template_only: bool = False
    runner_type: str = "self-hosted"
    max_fix_attempts: int = 5


class GenerateWorkflowResponse(BaseModel):
    success: bool
    workflow: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int


class CommitRequest(BaseModel):
    repo_url: str
    github_token: str
    workflow: str
    dockerfile: str
    branch_name: Optional[str] = None
    commit_message: str = "Add CI/CD workflow configuration [AI Generated]"


class CommitResponse(BaseModel):
    success: bool
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    web_url: Optional[str] = None
    error: Optional[str] = None


class WorkflowStatusRequest(BaseModel):
    repo_url: str
    github_token: str
    branch: str


class FeedbackRequest(BaseModel):
    repo_url: str
    github_token: str
    branch: str
    original_workflow: str
    original_dockerfile: str
    corrected_workflow: str
    corrected_dockerfile: str
    error_type: str
    fix_description: str


class FullWorkflowRequest(BaseModel):
    repo_url: str
    github_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    auto_commit: bool = True
    branch_name: Optional[str] = None
    use_template_only: bool = False
    runner_type: str = "self-hosted"


class SelfHealRequest(BaseModel):
    repo_url: str
    github_token: str
    additional_context: Optional[str] = None
    auto_commit: bool = True
    max_attempts: int = 10
    runner_type: str = "self-hosted"


class DryRunRequest(BaseModel):
    workflow: str
    dockerfile: str
    github_token: Optional[str] = None


class RecordResultRequest(BaseModel):
    repo_url: str
    github_token: str
    branch: str
    run_id: int


class StoreTemplateRequest(BaseModel):
    language: str
    framework: Optional[str] = "generic"
    workflow: str
    dockerfile: str
    description: Optional[str] = None


class FixRequest(BaseModel):
    workflow: str
    dockerfile: str
    error_log: str
    job_name: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None


# ============================================================================
# Chat Interface (for frontend chatbot)
# ============================================================================

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


# In-memory state for chat conversations
_chat_pending: Dict[str, Dict] = {}  # conversation_id -> pending pipeline data


def _to_internal_url(url: str) -> str:
    """Translate browser-accessible Gitea URL to Docker-internal URL."""
    internal_host = settings.github_url.replace("http://", "")
    url = url.replace("localhost:3002", internal_host)
    url = url.replace("127.0.0.1:3002", internal_host)
    return url


def _to_browser_url(url: str) -> str:
    """Translate Docker-internal Gitea URL to browser-accessible URL."""
    internal_host = settings.github_url.replace("http://", "")
    return url.replace(internal_host, "localhost:3002")


def _extract_url(text: str) -> Optional[str]:
    """Extract a URL from user message and translate to Docker-internal URL."""
    match = re.search(r'https?://[^\s<>"\']+', text)
    if not match:
        return None
    url = match.group(0).rstrip('.,;:)')
    return _to_internal_url(url)


def _is_approval(text: str) -> bool:
    """Check if the user message is approving/committing."""
    lower = text.lower().strip()
    approval_words = [
        'yes', 'commit', 'approve', 'go ahead', 'do it', 'push',
        'deploy', 'confirm', 'ok', 'sure', 'proceed', 'ship it',
        'commit it', 'push it', 'yes please', 'lgtm'
    ]
    return any(lower.startswith(w) or lower == w for w in approval_words)


def _is_status_check(text: str) -> bool:
    """Check if the user is asking about build status."""
    lower = text.lower().strip()
    return any(kw in lower for kw in ['status', 'build', 'check', 'result', 'how is'])


@router.post("/chat")
async def github_chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Chat interface for GitHub Actions Pipeline Generator.

    Handles natural language messages:
    - URL detected -> generate workflow
    - Approval words -> commit workflow
    - Status keywords -> check workflow status
    """
    message = request.message.strip()
    conversation_id = request.conversation_id or str(uuid.uuid4())
    github_token = settings.github_token

    try:
        # Case 1: User provides a repository URL -> generate workflow
        url = _extract_url(message)
        display_url = _to_browser_url(url) if url else None
        if url:
            result = await github_pipeline_generator.generate_with_validation(
                repo_url=url,
                github_token=github_token,
                model="pipeline-generator-v5",
                max_fix_attempts=10
            )

            if not result.get("success") and not result.get("workflow"):
                return {
                    "conversation_id": conversation_id,
                    "message": f"**Error generating workflow.** Could not create a valid GitHub Actions workflow for `{display_url}`.\n\nPlease check the repository URL and try again."
                }

            # Store pending pipeline for commit
            analysis = result.get("analysis", {})
            model_used = result.get("model_used", "unknown")
            template_source = result.get("template_source", "")

            _chat_pending[conversation_id] = {
                "repo_url": url,
                "workflow": result.get("workflow", ""),
                "dockerfile": result.get("dockerfile", ""),
                "analysis": analysis,
                "model_used": model_used,
                "template_source": template_source
            }

            # Build response message
            lang = analysis.get("language", "unknown")
            framework = analysis.get("framework", "generic")
            fix_attempts = result.get("fix_attempts", 0)

            # Source banner
            if template_source == "reinforcement_learning":
                source_msg = "**Template exists in RAG** - using a proven workflow that has succeeded before.\n\n"
            elif model_used == "default-template":
                source_msg = "**Using a built-in default template** for this language.\n\n"
            else:
                source_msg = f"**No template in RAG for this language.** LLM (`{model_used}`) is creating and testing a new workflow configuration.\n\n"

            # Validation info
            if result.get("validation_skipped"):
                val_msg = "Validation: *Skipped (proven template)*\n\n"
            elif result.get("validation_passed"):
                val_msg = "Validation: **Passed**"
                if fix_attempts > 1:
                    val_msg += f" (auto-fixed in {fix_attempts} attempts)"
                val_msg += "\n\n"
            else:
                errors = result.get("validation_errors", [])
                val_msg = f"Validation: **Issues found** - {len(errors)} error(s)\n"
                for err in errors[:5]:
                    val_msg += f"- {err}\n"
                val_msg += "\n"

            response_msg = (
                f"{source_msg}"
                f"Generated **GitHub Actions workflow** and **Dockerfile** for `{display_url}`\n\n"
                f"- Language: **{lang}**\n"
                f"- Framework: **{framework}**\n\n"
                f"{val_msg}"
                f"### .github/workflows/ci.yml\n```yaml\n{result.get('workflow', '')[:3000]}\n```\n\n"
                f"### Dockerfile\n```dockerfile\n{result.get('dockerfile', '')[:1500]}\n```\n\n"
                f"Would you like to **commit** these files to the repository?"
            )

            return {
                "conversation_id": conversation_id,
                "message": response_msg
            }

        # Case 2: User approves -> commit the pending pipeline
        if _is_approval(message):
            pending = _chat_pending.get(conversation_id)
            if not pending:
                return {
                    "conversation_id": conversation_id,
                    "message": "No workflow to commit. Please provide a repository URL first to generate a GitHub Actions workflow."
                }

            # Build commit message
            analysis = pending.get("analysis", {})
            lang = analysis.get("language", "unknown")
            framework = analysis.get("framework", "generic")
            template_source = pending.get("template_source", "")
            model_used = pending.get("model_used", "unknown")

            if template_source == "reinforcement_learning":
                commit_msg = f"Add CI/CD workflow + Dockerfile [RL Template] - Proven {lang}/{framework} from ChromaDB"
            elif model_used == "default-template":
                commit_msg = f"Add CI/CD workflow + Dockerfile [Built-in Template] - Default {lang} configuration"
            else:
                commit_msg = f"Add CI/CD workflow + Dockerfile [LLM Generated] - {lang}/{framework} by {model_used}"

            commit_result = await github_pipeline_generator.commit_to_github(
                repo_url=pending["repo_url"],
                github_token=github_token,
                workflow=pending["workflow"],
                dockerfile=pending["dockerfile"],
                commit_message=commit_msg
            )

            if commit_result.get("success"):
                branch = commit_result.get("branch", "main")
                web_url = commit_result.get("web_url", "")
                browser_web_url = _to_browser_url(web_url) if web_url else ""

                # Derive project_id from repo URL (Gitea has no numeric IDs)
                parsed = github_pipeline_generator.parse_repo_url(pending["repo_url"])
                project_id = abs(hash(pending["repo_url"])) % (10**8)

                # Start background monitoring
                progress = progress_store.create(project_id=project_id, branch=branch, max_attempts=10)
                progress.model_used = model_used
                background_tasks.add_task(
                    monitor_workflow_for_learning,
                    repo_url=pending["repo_url"],
                    github_token=github_token,
                    branch=branch,
                    project_id=project_id,
                    workflow=pending["workflow"],
                    dockerfile=pending["dockerfile"],
                    language=analysis.get("language", "unknown"),
                    framework=analysis.get("framework", "generic"),
                )

                # Clean up pending
                del _chat_pending[conversation_id]

                # Build Gitea Actions URL for the user
                gitea_actions_url = f"http://localhost:3002/{parsed['owner']}/{parsed['repo']}/actions"

                return {
                    "conversation_id": conversation_id,
                    "message": (
                        f"**Workflow committed successfully!**\n\n"
                        f"- Branch: `{branch}`\n"
                        f"- Commit: `{commit_result.get('commit_sha', 'N/A')[:12]}`\n"
                        f"- Gitea: [{browser_web_url}]({browser_web_url})\n"
                        f"- Actions: [{parsed['repo']} actions]({gitea_actions_url})\n\n"
                        f"Monitoring Gitea Actions workflow for `{parsed['repo']}`..."
                    ),
                    "monitoring": {
                        "project_id": project_id,
                        "branch": branch
                    }
                }
            else:
                return {
                    "conversation_id": conversation_id,
                    "message": f"**Commit failed:** {commit_result.get('error', 'Unknown error')}\n\nPlease check the repository permissions and try again."
                }

        # Case 3: Status check
        if _is_status_check(message):
            pending = _chat_pending.get(conversation_id)
            if pending:
                repo_url = pending.get("repo_url", "")
                return {
                    "conversation_id": conversation_id,
                    "message": (
                        f"Workflow generated for `{_to_browser_url(repo_url)}` but not yet committed.\n\n"
                        f"Say **commit** to push the files, or provide a new URL to regenerate."
                    )
                }
            return {
                "conversation_id": conversation_id,
                "message": "No active workflow session. Provide a repository URL to generate a GitHub Actions workflow."
            }

        # Case 4: Unknown message
        return {
            "conversation_id": conversation_id,
            "message": (
                "I can help you generate GitHub Actions workflows with a full **9-job** pipeline. Here's what I can do:\n\n"
                "1. **Generate a workflow** - Provide a repository URL\n"
                "2. **Commit files** - Say 'commit' after reviewing the generated files\n"
                "3. **Check status** - Say 'status' to check the current state\n\n"
                "**Example:** `Generate a workflow for http://localhost:3002/github-projects/java-springboot-api`"
            )
        }

    except Exception as e:
        print(f"[GitHub Chat] Error: {e}")
        return {
            "conversation_id": conversation_id,
            "message": f"**Error:** {str(e)}\n\nPlease check the backend logs and try again."
        }


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/analyze")
async def analyze_repository(request: AnalyzeRequest):
    """Analyze a GitHub/Gitea repository to detect language, framework, and structure."""
    try:
        analysis = await github_pipeline_generator.analyze_repository(
            request.repo_url,
            request.github_token
        )
        return {"success": True, **analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=GenerateWorkflowResponse)
async def generate_workflow(request: GenerateWorkflowRequest):
    """
    Generate GitHub Actions workflow and Dockerfile for a repository.

    Uses:
    1. Proven templates from ChromaDB (if available)
    2. LLM generation with reference templates
    3. Default templates as fallback
    """
    try:
        result = await github_pipeline_generator.generate_workflow_files(
            repo_url=request.repo_url,
            github_token=request.github_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            runner_type=request.runner_type
        )

        # Auto-seed images in Nexus
        try:
            await ensure_images_in_nexus(result["workflow"])
        except Exception as e:
            print(f"[GitHub Pipeline] Image seeding warning: {e}")

        return GenerateWorkflowResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-validated")
async def generate_with_validation(request: GenerateWithValidationRequest):
    """
    Generate workflow with validation and automatic LLM-based fixing.
    Iteratively validates and fixes until the workflow passes or max attempts reached.
    """
    try:
        result = await github_pipeline_generator.generate_with_validation(
            repo_url=request.repo_url,
            github_token=request.github_token,
            model=request.model,
            max_fix_attempts=request.max_fix_attempts,
            additional_context=request.additional_context or "",
            runner_type=request.runner_type
        )

        # Auto-seed images
        try:
            await ensure_images_in_nexus(result["workflow"])
        except Exception as e:
            print(f"[GitHub Pipeline] Image seeding warning: {e}")

        return {
            "success": True,
            "workflow": result["workflow"],
            "dockerfile": result["dockerfile"],
            "analysis": result["analysis"],
            "model_used": result["model_used"],
            "feedback_used": result.get("feedback_used", 0),
            "validation_passed": result.get("validation_passed", False),
            "fix_attempts": result.get("fix_attempts", 0),
            "fix_history": result.get("fix_history", []),
            "has_warnings": result.get("has_warnings", False),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit", response_model=CommitResponse)
async def commit_workflow(request: CommitRequest):
    """
    Commit generated workflow and Dockerfile to the repository.
    Creates a new branch with the CI/CD configuration.
    """
    try:
        result = await github_pipeline_generator.commit_to_github(
            repo_url=request.repo_url,
            github_token=request.github_token,
            workflow=request.workflow,
            dockerfile=request.dockerfile,
            branch_name=request.branch_name,
            commit_message=request.commit_message
        )
        return CommitResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status")
async def get_workflow_status(request: WorkflowStatusRequest):
    """Get the latest workflow run status for a branch."""
    try:
        status = await github_pipeline_generator.get_workflow_status(
            repo_url=request.repo_url,
            github_token=request.github_token,
            branch=request.branch
        )
        return {"success": True, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def store_feedback(request: FeedbackRequest):
    """Store manual corrections for reinforcement learning."""
    try:
        # Compare original vs corrected files
        differences = await compare_and_learn(
            repo_url=request.repo_url,
            github_token=request.github_token,
            branch=request.branch,
            generated_files={
                ".github/workflows/ci.yml": request.original_workflow,
                "Dockerfile": request.original_dockerfile
            }
        )

        workflow_diff = differences.get(".github/workflows/ci.yml", {})
        dockerfile_diff = differences.get("Dockerfile", {})

        if workflow_diff.get("changed") or dockerfile_diff.get("changed"):
            analysis = await github_pipeline_generator.analyze_repository(
                request.repo_url,
                request.github_token
            )

            success = await store_rl_feedback(
                original_workflow=request.original_workflow,
                corrected_workflow=request.corrected_workflow,
                original_dockerfile=request.original_dockerfile,
                corrected_dockerfile=request.corrected_dockerfile,
                language=analysis['language'],
                framework=analysis['framework'],
                error_type=request.error_type,
                fix_description=request.fix_description
            )

            return {
                "success": success,
                "message": "Feedback stored for reinforcement learning",
                "changes_detected": {
                    "workflow": workflow_diff.get("changed", False),
                    "dockerfile": dockerfile_diff.get("changed", False)
                }
            }
        else:
            return {
                "success": True,
                "message": "No changes detected between original and current files",
                "changes_detected": {"workflow": False, "dockerfile": False}
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/history")
async def get_feedback_history(
    language: Optional[str] = None,
    framework: Optional[str] = None,
    limit: int = 20
):
    """Get feedback history filtered by language and framework."""
    try:
        feedback = await get_relevant_feedback(
            language=language or "",
            framework=framework or "",
            limit=limit
        )
        return {
            "success": True,
            "feedback": feedback,
            "count": len(feedback)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/record")
async def record_workflow_result(request: RecordResultRequest):
    """
    Record workflow run result for reinforcement learning.
    Called automatically by the learn-record job in workflows.
    """
    try:
        result = await rl_record_build_result(
            repo_url=request.repo_url,
            github_token=request.github_token,
            branch=request.branch,
            run_id=request.run_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/successful")
async def get_successful_workflows(
    language: str,
    framework: Optional[str] = None,
    limit: int = 10
):
    """Get successful workflow configurations for a language/framework."""
    try:
        templates = await github_pipeline_generator.get_best_template_files(
            language=language,
            framework=framework
        )
        return {
            "success": True,
            "templates": templates if templates else [],
            "count": 1 if templates else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/best")
async def get_best_workflow(
    language: str,
    framework: Optional[str] = None
):
    """Get the best performing workflow configuration."""
    try:
        best = await github_pipeline_generator.get_best_template_files(
            language=language,
            framework=framework
        )
        if best:
            return {"success": True, **best}
        return {"success": False, "message": "No templates found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/store-template")
async def store_template(request: StoreTemplateRequest):
    """Manually store a proven workflow template."""
    try:
        import httpx

        content = f"{request.workflow}\n{request.dockerfile}"
        content_hash = hashlib.md5(content.encode()).hexdigest()[:12]
        doc_id = f"manual_{request.language}_{request.framework}_{content_hash}"

        doc_content = f"""## Manual GitHub Actions Workflow Template
Language: {request.language}
Framework: {request.framework}
Source: manual_upload
Description: {request.description or ''}

### .github/workflows/ci.yml
```yaml
{request.workflow}
```

### Dockerfile
```dockerfile
{request.dockerfile}
```
"""

        from app.services.github_pipeline.templates import _resolve_collection_uuid

        async with httpx.AsyncClient(timeout=30.0) as client:
            for coll_name in ["github_actions_templates", "github_actions_successful_pipelines"]:
                coll_uuid = await _resolve_collection_uuid(client, coll_name)
                if not coll_uuid:
                    continue
                h = hashlib.sha256(doc_content.encode()).digest()
                embedding = [float(h[i % len(h)]) / 255.0 - 0.5 for i in range(384)]
                await client.post(
                    f"{settings.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{coll_uuid}/add",
                    json={
                        "ids": [f"{doc_id}_{coll_name[:8]}"],
                        "documents": [doc_content],
                        "embeddings": [embedding],
                        "metadatas": [{
                            "language": request.language,
                            "framework": request.framework or "generic",
                            "source": "manual_upload",
                            "description": request.description or "",
                            "content_hash": content_hash,
                            "success_count": 1,
                            "duration": 0,
                        }]
                    }
                )

        return {
            "success": True,
            "message": f"Template stored for {request.language}/{request.framework}",
            "doc_id": doc_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/{project_id}/{branch:path}")
async def get_github_progress(project_id: int, branch: str):
    """Get real-time progress of GitHub Actions workflow monitoring and self-healing."""
    progress = progress_store.get(project_id, branch)
    if not progress:
        return {"found": False, "message": "No monitoring in progress for this workflow"}
    return {"found": True, **progress.to_dict()}


@router.post("/workflow")
async def full_workflow(
    request: FullWorkflowRequest,
    background_tasks: BackgroundTasks
):
    """
    Complete workflow: analyze -> generate -> validate -> commit -> monitor.

    Returns immediately with generation results, monitors workflow in background.
    """
    try:
        # Step 1: Generate workflow files with validation
        result = await github_pipeline_generator.generate_with_validation(
            repo_url=request.repo_url,
            github_token=request.github_token,
            model=request.model,
            additional_context=request.additional_context or "",
            runner_type=request.runner_type
        )

        # Step 2: Auto-seed images
        try:
            await ensure_images_in_nexus(result["workflow"])
        except Exception as e:
            print(f"[GitHub Workflow] Image seeding warning: {e}")

        response = {
            "success": True,
            "generation": result
        }

        # Step 3: Commit if auto_commit is enabled
        if request.auto_commit:
            commit_result = await github_pipeline_generator.commit_to_github(
                repo_url=request.repo_url,
                github_token=request.github_token,
                workflow=result["workflow"],
                dockerfile=result["dockerfile"],
                branch_name=request.branch_name
            )
            response["commit"] = commit_result

            # Step 4: Schedule background monitoring
            if commit_result.get("success"):
                project_id = abs(hash(request.repo_url)) % (10**8)
                branch = commit_result.get("branch", "")
                prog = progress_store.create(project_id=project_id, branch=branch, max_attempts=10)
                prog.model_used = result.get("model_used", "unknown")

                background_tasks.add_task(
                    monitor_workflow_for_learning,
                    repo_url=request.repo_url,
                    github_token=request.github_token,
                    branch=branch,
                    project_id=project_id,
                    workflow=result["workflow"],
                    dockerfile=result["dockerfile"],
                    language=result.get("analysis", {}).get("language", "unknown"),
                    framework=result.get("analysis", {}).get("framework", "generic"),
                )
                response["monitoring"] = {
                    "status": "scheduled",
                    "project_id": project_id,
                    "branch": branch,
                    "rl_enabled": True,
                    "self_healing_enabled": True,
                }

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal")
async def self_heal_workflow(request: SelfHealRequest):
    """Self-healing workflow: re-generate with LLM fix loop + commit."""
    try:
        # Generate with validation loop
        result = await github_pipeline_generator.generate_workflow_files(
            repo_url=request.repo_url,
            github_token=request.github_token,
            additional_context=request.additional_context or "",
            use_template_only=False,
            runner_type=request.runner_type
        )

        workflow = result["workflow"]
        dockerfile = result["dockerfile"]
        analysis = result["analysis"]

        # Run iterative fix
        fix_result = await github_llm_fixer.iterative_fix(
            workflow=workflow,
            dockerfile=dockerfile,
            analysis=analysis,
            max_attempts=request.max_attempts,
        )

        response = {
            "success": fix_result.get("success", False),
            "workflow": fix_result["workflow"],
            "dockerfile": fix_result["dockerfile"],
            "analysis": analysis,
            "fix_attempts": fix_result.get("attempts", 0),
            "fix_history": fix_result.get("fix_history", []),
        }

        if request.auto_commit and fix_result.get("success"):
            commit_result = await github_pipeline_generator.commit_to_github(
                repo_url=request.repo_url,
                github_token=request.github_token,
                workflow=fix_result["workflow"],
                dockerfile=fix_result["dockerfile"],
            )
            response["commit"] = commit_result

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal/async")
async def self_heal_workflow_async(
    request: SelfHealRequest,
    background_tasks: BackgroundTasks
):
    """Self-healing workflow - async execution."""
    try:
        background_tasks.add_task(
            _run_self_heal,
            request.repo_url,
            request.github_token,
            request.additional_context or "",
            request.auto_commit,
            request.runner_type,
            request.max_attempts,
        )

        return {
            "success": True,
            "status": "started",
            "message": "Self-healing workflow started in background"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dry-run")
async def dry_run_validation(request: DryRunRequest):
    """Validate workflow and Dockerfile before committing."""
    try:
        errors = []
        warnings = []

        workflow = request.workflow.strip()
        dockerfile = request.dockerfile.strip()

        # Workflow validation
        if not workflow:
            errors.append("Workflow is empty")
        else:
            if 'on:' not in workflow and 'on :' not in workflow:
                errors.append("Missing 'on:' trigger block")
            if 'jobs:' not in workflow:
                errors.append("Missing 'jobs:' block")
            if 'runs-on:' in workflow and 'self-hosted' not in workflow:
                errors.append("Jobs must use 'runs-on: self-hosted'")

            # Check for public registry references
            public_registries = ['docker.io/', 'gcr.io/', 'quay.io/', 'ghcr.io/']
            for reg in public_registries:
                if reg in workflow:
                    errors.append(f"Public registry reference found: {reg}")

            # Check required jobs
            required = ['compile', 'build-image', 'test-image', 'static-analysis',
                       'sonarqube', 'trivy-scan', 'push-release']
            for job in required:
                if f'{job}:' not in workflow and f'"{job}"' not in workflow and f"'{job}'" not in workflow:
                    warnings.append(f"Missing job: {job}")

        # Dockerfile validation
        if not dockerfile:
            warnings.append("Dockerfile is empty")
        else:
            if 'FROM' not in dockerfile.upper():
                errors.append("Dockerfile missing FROM statement")
            for reg in ['docker.io/', 'gcr.io/', 'quay.io/']:
                if reg in dockerfile:
                    errors.append(f"Dockerfile uses public registry: {reg}")

        return {
            "success": True,
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "results": {
                "workflow_validation": {
                    "valid": len([e for e in errors if 'Dockerfile' not in e]) == 0,
                    "errors": [e for e in errors if 'Dockerfile' not in e],
                    "warnings": [w for w in warnings if 'Dockerfile' not in w]
                },
                "dockerfile_validation": {
                    "valid": len([e for e in errors if 'Dockerfile' in e]) == 0,
                    "errors": [e for e in errors if 'Dockerfile' in e],
                    "warnings": [w for w in warnings if 'Dockerfile' in w]
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix")
async def fix_workflow_error(request: FixRequest):
    """LLM Fix - Analyze GitHub Actions workflow error and generate fix."""
    try:
        analysis = {
            "language": request.language or "unknown",
            "framework": request.framework or "generic",
            "package_manager": "unknown"
        }

        # Parse error log into error list
        error_lines = [line.strip() for line in request.error_log.split('\n') if line.strip()]

        result = await github_llm_fixer.fix_pipeline(
            workflow=request.workflow,
            dockerfile=request.dockerfile,
            errors=error_lines,
            warnings=[],
            analysis=analysis,
        )

        return {
            "success": 'error' not in result,
            "fixed_files": {
                "workflow": result.get("workflow", request.workflow),
                "dockerfile": result.get("dockerfile", request.dockerfile),
            },
            "error": result.get("error"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Background Tasks
# ============================================================================

async def _fetch_failed_job_log(api_base: str, headers: dict, run_id: int) -> tuple:
    """Fetch log and name from the first failed job in a workflow run.
    Returns (error_log, job_name) tuple."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            jobs_resp = await client.get(
                f"{api_base}/actions/runs/{run_id}/jobs",
                headers=headers
            )
            if jobs_resp.status_code != 200:
                return None, None

            jobs_data = jobs_resp.json()
            jobs_list = jobs_data.get("jobs", [])

            failed_job = None
            for job in jobs_list:
                if job.get("conclusion") == "failure":
                    failed_job = job
                    break

            if not failed_job:
                return None, None

            job_name = failed_job.get("name", "unknown")
            job_id = failed_job.get("id")
            if not job_id:
                return None, job_name

            # Gitea Actions log endpoint: /actions/jobs/{job_id}/logs
            log_resp = await client.get(
                f"{api_base}/actions/jobs/{job_id}/logs",
                headers=headers
            )
            if log_resp.status_code == 200:
                log_text = log_resp.text
                if log_text and len(log_text) > 10:
                    return log_text[:8000], job_name

    except Exception as e:
        print(f"[GitHub Monitor] Failed to fetch job logs: {e}")

    return None, None


async def monitor_workflow_for_learning(
    repo_url: str,
    github_token: str,
    branch: str,
    project_id: int = 0,
    workflow: str = "",
    dockerfile: str = "",
    language: str = "unknown",
    framework: str = "generic",
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30,
    max_heal_attempts: int = 10
):
    """
    Background task to monitor Gitea Actions workflow, self-heal on failure, and record to RL only on success.

    Self-healing loop:
    1. Monitor workflow run until completion
    2. On success -> record to RAG/ChromaDB -> done
    3. On failure -> fetch actual error logs -> LLM fix -> commit -> monitor new run
    4. Repeat up to max_heal_attempts times
    5. Only save to RAG when pipeline fully succeeds
    """
    import httpx

    parsed = github_pipeline_generator.parse_repo_url(repo_url)
    api_base = f"{settings.github_url}/api/v1/repos/{parsed['owner']}/{parsed['repo']}"
    headers = {"Authorization": f"token {github_token}"}
    gitea_actions_url = f"http://localhost:3002/{parsed['owner']}/{parsed['repo']}/actions"

    print(f"[GitHub Monitor] Starting workflow monitor for {parsed['owner']}/{parsed['repo']} branch={branch} (max_heal={max_heal_attempts})")

    current_workflow = workflow
    current_dockerfile = dockerfile
    max_checks = (max_wait_minutes * 60) // check_interval_seconds
    # Track the highest run ID we've already processed so we can detect new runs after self-heal
    previous_max_run_id = 0

    for heal_attempt in range(max_heal_attempts + 1):
        # heal_attempt 0 = initial run, 1..N = after self-heal commits
        if heal_attempt > 0:
            print(f"[GitHub Monitor] Monitoring self-heal attempt {heal_attempt}/{max_heal_attempts} (waiting for run > #{previous_max_run_id})")
            if project_id:
                progress_store.update(project_id, branch, "build_running",
                    f"Self-heal attempt {heal_attempt}/{max_heal_attempts} - watching new workflow run...")

        last_run_id = None
        last_conclusion = None
        last_jobs_info = ""
        run_completed = False

        for check_num in range(max_checks):
            if check_num > 0:
                await asyncio.sleep(check_interval_seconds)

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    runs_resp = await client.get(
                        f"{api_base}/actions/runs",
                        headers=headers,
                        params={"branch": branch, "limit": 10}
                    )

                if runs_resp.status_code != 200:
                    if project_id:
                        progress_store.update(project_id, branch, "build_running",
                            "Waiting for Gitea Actions to start...")
                    continue

                runs_data = runs_resp.json()
                workflow_runs = runs_data.get("workflow_runs", [])

                if not workflow_runs:
                    if project_id:
                        progress_store.update(project_id, branch, "build_running",
                            "Waiting for workflow run to appear...")
                    continue

                # Find the latest non-cancelled run that is newer than previous_max_run_id
                run = None
                for candidate in workflow_runs:
                    cid = candidate.get("id", 0)
                    cstatus = candidate.get("status", "")
                    cconclusion = candidate.get("conclusion", "")
                    # Skip runs we already processed
                    if cid <= previous_max_run_id:
                        continue
                    # Skip cancelled runs (Gitea cancels old runs when new commits arrive)
                    if cstatus == "completed" and cconclusion == "cancelled":
                        continue
                    run = candidate
                    break

                if not run:
                    if project_id:
                        progress_store.update(project_id, branch, "build_running",
                            f"Waiting for new workflow run (after #{previous_max_run_id})...")
                    continue

                run_id = run.get("id", 0)
                run_status = run.get("status", "unknown")
                conclusion = run.get("conclusion", "")

                print(f"[GitHub Monitor] Run #{run_id}: status={run_status}, conclusion={conclusion}")

                # Fetch jobs for this run
                jobs_info = ""
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        jobs_resp = await client.get(
                            f"{api_base}/actions/runs/{run_id}/jobs",
                            headers=headers
                        )
                    if jobs_resp.status_code == 200:
                        jobs_data = jobs_resp.json()
                        jobs_list = jobs_data.get("jobs", [])
                        if jobs_list:
                            job_parts = []
                            for j in jobs_list:
                                j_status = j.get("conclusion") or j.get("status", "pending")
                                icon = {"success": "\u2705", "failure": "\u274c", "in_progress": "\u23f3", "queued": "\u23f8"}.get(j_status, "\u2b1c")
                                job_parts.append(f"{icon} {j.get('name', 'unknown')}")
                            jobs_info = " | " + " \u2192 ".join(job_parts)
                except Exception:
                    pass

                if project_id:
                    attempt_prefix = f"[Fix {heal_attempt}/{max_heal_attempts}] " if heal_attempt > 0 else ""
                    if run_status in ("queued", "waiting", "pending"):
                        progress_store.update(project_id, branch, "build_running",
                            f"{attempt_prefix}Workflow queued... | [Actions]({gitea_actions_url})")
                    elif run_status == "in_progress":
                        progress_store.update(project_id, branch, "build_running",
                            f"{attempt_prefix}Workflow running{jobs_info} | [Actions]({gitea_actions_url})")
                    elif run_status == "completed":
                        progress_store.update(project_id, branch, "build_running",
                            f"{attempt_prefix}Workflow finished: {conclusion}{jobs_info}")

                if run_status == "completed":
                    last_run_id = run_id
                    last_conclusion = conclusion
                    last_jobs_info = jobs_info
                    run_completed = True
                    break

            except Exception as e:
                print(f"[GitHub Monitor] Error checking status: {e}")

        # --- Handle run completion ---

        if not run_completed:
            # Timeout
            print(f"[GitHub Monitor] Timeout waiting for workflow on {parsed['owner']}/{parsed['repo']}")
            if project_id:
                progress_store.complete(project_id, branch, "failed",
                    f"Timeout waiting for workflow after {max_wait_minutes} minutes.")
            return

        if last_conclusion == "success":
            # SUCCESS - Only NOW record to RAG
            await rl_record_build_result(
                repo_url=repo_url,
                github_token=github_token,
                branch=branch,
                run_id=last_run_id
            )
            attempts_msg = f" after {heal_attempt} fix(es)" if heal_attempt > 0 else ""
            print(f"[GitHub Monitor] Workflow SUCCESS{attempts_msg} for {parsed['repo']} - saved to RAG")

            if project_id:
                progress_store.complete(project_id, branch, "success",
                    f"\u2705 Workflow succeeded{attempts_msg}!{last_jobs_info}\n[View Actions]({gitea_actions_url})")
            return

        if last_conclusion not in ("failure", "cancelled"):
            # Other conclusion (skipped, neutral)
            print(f"[GitHub Monitor] Workflow ended with conclusion: {last_conclusion}")
            if project_id:
                progress_store.complete(project_id, branch, "failed",
                    f"Workflow ended with conclusion: {last_conclusion}")
            return

        # --- FAILURE: attempt self-healing ---

        if heal_attempt >= max_heal_attempts:
            print(f"[GitHub Monitor] All {max_heal_attempts} self-heal attempts exhausted for {parsed['repo']}")
            if project_id:
                progress_store.complete(project_id, branch, "failed",
                    f"\u274c Workflow failed after {max_heal_attempts} self-heal attempts.{last_jobs_info}\n[View Actions]({gitea_actions_url})")
            return

        if not current_workflow or not current_dockerfile:
            if project_id:
                progress_store.complete(project_id, branch, "failed",
                    f"Workflow failed ({last_conclusion}). No source files available for self-healing.")
            return

        print(f"[GitHub Monitor] Workflow FAILED (run #{last_run_id}) - self-heal {heal_attempt + 1}/{max_heal_attempts}")

        if project_id:
            progress_store.update(project_id, branch, "build_failed",
                f"Workflow failed ({last_conclusion}){last_jobs_info}. Fetching error logs for self-heal {heal_attempt + 1}/{max_heal_attempts}...")

        # Fetch actual error logs from the failed run
        error_log, failed_job_name = await _fetch_failed_job_log(api_base, headers, last_run_id)

        fix_applied = False
        if error_log:
            print(f"[GitHub Monitor] Got error log from job '{failed_job_name}' ({len(error_log)} chars)")
            if project_id:
                progress_store.update(project_id, branch, "build_failed",
                    f"Got error log from '{failed_job_name}'. LLM generating fix...")

            # Use actual error logs for LLM fix
            fix_result = await github_llm_fixer.generate_fix(
                dockerfile=current_dockerfile,
                workflow=current_workflow,
                error_log=error_log,
                job_name=failed_job_name or "unknown",
                language=language,
                framework=framework
            )

            if fix_result.success and (fix_result.workflow or fix_result.dockerfile):
                current_workflow = fix_result.workflow or current_workflow
                current_dockerfile = fix_result.dockerfile or current_dockerfile
                fix_applied = True
                print(f"[GitHub Monitor] LLM fix applied: {fix_result.explanation}")
                # Track fixer model on progress
                if project_id:
                    prog = progress_store.get(project_id, branch)
                    if prog:
                        prog.fixer_model_used = get_active_provider_name()
            else:
                print(f"[GitHub Monitor] Log-based LLM fix failed: {fix_result.explanation}")

        if not fix_applied:
            # Fallback: static validation-based fix
            print("[GitHub Monitor] Falling back to static validation fix...")
            if project_id:
                progress_store.update(project_id, branch, "build_failed",
                    "No logs or log-based fix failed. Trying static validation fix...")

            analysis = {"language": language, "framework": framework, "package_manager": "unknown"}
            static_fix = await github_llm_fixer.iterative_fix(
                workflow=current_workflow,
                dockerfile=current_dockerfile,
                analysis=analysis,
                max_attempts=2
            )
            if static_fix.get("success"):
                current_workflow = static_fix["workflow"]
                current_dockerfile = static_fix["dockerfile"]
                print("[GitHub Monitor] Static fix applied")
            else:
                print("[GitHub Monitor] Static fix also had issues, committing best effort")

        # Record the current run ID so the next iteration skips all runs up to this one
        previous_max_run_id = last_run_id

        # Commit the fix
        try:
            if project_id:
                progress_store.update(project_id, branch, "build_running",
                    f"Committing self-heal fix {heal_attempt + 1}/{max_heal_attempts}...")

            await github_pipeline_generator.commit_to_github(
                repo_url=repo_url,
                github_token=github_token,
                workflow=current_workflow,
                dockerfile=current_dockerfile,
                branch_name=branch,
            )
            print(f"[GitHub Monitor] Self-heal commit #{heal_attempt + 1} pushed to {branch}")

            # Wait for Gitea to trigger the new workflow run
            await asyncio.sleep(10)

        except Exception as commit_err:
            print(f"[GitHub Monitor] Self-heal commit error: {commit_err}")
            if project_id:
                progress_store.complete(project_id, branch, "failed",
                    f"Self-healing commit failed: {commit_err}")
            return

        # Loop continues: will monitor the new workflow run


async def _run_self_heal(
    repo_url: str,
    github_token: str,
    additional_context: str,
    auto_commit: bool,
    runner_type: str,
    max_attempts: int = 10,
):
    """Background task for self-healing workflow."""
    try:
        result = await github_pipeline_generator.generate_workflow_files(
            repo_url=repo_url,
            github_token=github_token,
            additional_context=additional_context,
            use_template_only=False,
            runner_type=runner_type
        )

        analysis = result.get("analysis", {})

        fix_result = await github_llm_fixer.iterative_fix(
            workflow=result["workflow"],
            dockerfile=result["dockerfile"],
            analysis=analysis,
            max_attempts=max_attempts,
        )

        if auto_commit and fix_result.get("success"):
            await github_pipeline_generator.commit_to_github(
                repo_url=repo_url,
                github_token=github_token,
                workflow=fix_result["workflow"],
                dockerfile=fix_result["dockerfile"],
            )
            print(f"[GitHub Self-Heal] Committed fixed workflow for {repo_url}")
        elif not fix_result.get("success"):
            print(f"[GitHub Self-Heal] Fix failed after {fix_result.get('attempts')} attempts")
    except Exception as e:
        print(f"[GitHub Self-Heal] Error: {e}")
