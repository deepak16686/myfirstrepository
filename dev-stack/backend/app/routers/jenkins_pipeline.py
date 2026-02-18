"""
File: jenkins_pipeline.py
Purpose: Provides the full lifecycle for Jenkins Declarative Pipeline generation -- chat interface,
    Jenkinsfile/Dockerfile generation with LLM validation, commit to Gitea, Jenkins build
    monitoring, reinforcement-learning feedback storage, and self-healing fix loops with
    background task orchestration.
When Used: Invoked by the frontend Jenkins Generator tool card chat and API calls when a user
    pastes a Gitea repo URL to generate a Jenkinsfile, approves a commit, or monitors a running
    Jenkins multibranch build via the /jenkins-pipeline/* routes.
Why Created: Mirrors the GitLab pipeline router architecture but targets Jenkins Declarative
    Pipelines on Gitea-hosted repos (jenkins-projects org), with its own chat state, URL
    translation between Docker-internal and browser-accessible Gitea URLs, and Jenkins-specific
    build/stage monitoring.
"""
import re
import uuid
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

from app.config import settings
from app.services.jenkins_pipeline import jenkins_pipeline_generator
from app.services.jenkins_pipeline.learning import (
    get_relevant_feedback,
    store_feedback as store_rl_feedback,
    record_build_result as rl_record_build_result,
    compare_and_learn,
)
from app.services.jenkins_pipeline.image_seeder import ensure_images_in_nexus
from app.services.jenkins_llm_fixer import jenkins_llm_fixer
from app.services.pipeline_progress import progress_store

router = APIRouter(prefix="/jenkins-pipeline", tags=["Jenkins Pipeline"])


# ============================================================================
# Request/Response Models
# ============================================================================

class AnalyzeRequest(BaseModel):
    repo_url: str
    git_token: str


class GenerateJenkinsfileRequest(BaseModel):
    repo_url: str
    git_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    use_template_only: bool = False
    agent_label: str = "docker"


class GenerateWithValidationRequest(BaseModel):
    repo_url: str
    git_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    use_template_only: bool = False
    agent_label: str = "docker"
    max_fix_attempts: int = 5


class GenerateJenkinsfileResponse(BaseModel):
    success: bool
    jenkinsfile: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int


class CommitRequest(BaseModel):
    repo_url: str
    git_token: str
    jenkinsfile: str
    dockerfile: str
    branch_name: Optional[str] = None
    commit_message: str = "Add Jenkinsfile and Dockerfile [AI Generated]"


class CommitResponse(BaseModel):
    success: bool
    branch: Optional[str] = None
    commit_id: Optional[str] = None
    web_url: Optional[str] = None
    project_id: Optional[int] = None
    error: Optional[str] = None


class BuildStatusRequest(BaseModel):
    job_name: str
    build_number: Optional[int] = None


class TriggerBuildRequest(BaseModel):
    job_name: str


class FeedbackRequest(BaseModel):
    repo_url: str
    git_token: str
    branch: str
    original_jenkinsfile: str
    original_dockerfile: str
    corrected_jenkinsfile: str
    corrected_dockerfile: str
    error_type: str
    fix_description: str


class RecordResultRequest(BaseModel):
    job_name: str
    build_number: int
    status: str = "success"
    repo_url: Optional[str] = None
    git_token: Optional[str] = None
    branch: Optional[str] = None


class StoreTemplateRequest(BaseModel):
    language: str
    framework: Optional[str] = "generic"
    jenkinsfile: str
    dockerfile: str
    description: Optional[str] = None


class FullWorkflowRequest(BaseModel):
    repo_url: str
    git_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    auto_commit: bool = True
    branch_name: Optional[str] = None
    use_template_only: bool = False
    agent_label: str = "docker"
    job_name: Optional[str] = None


class SelfHealRequest(BaseModel):
    repo_url: str
    git_token: str
    additional_context: Optional[str] = None
    auto_commit: bool = True
    max_attempts: int = 10
    agent_label: str = "docker"


class DryRunRequest(BaseModel):
    jenkinsfile: str
    dockerfile: str


class FixRequest(BaseModel):
    jenkinsfile: str
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
    internal_host = settings.jenkins_git_url.replace("http://", "")
    url = url.replace("localhost:3002", internal_host)
    url = url.replace("127.0.0.1:3002", internal_host)
    return url


def _to_browser_url(url: str) -> str:
    """Translate Docker-internal Gitea URL to browser-accessible URL."""
    internal_host = settings.jenkins_git_url.replace("http://", "")
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
async def jenkins_chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Chat interface for Jenkins Pipeline Generator.

    Handles natural language messages:
    - URL detected -> generate pipeline
    - Approval words -> commit pipeline
    - Status keywords -> check build status
    """
    message = request.message.strip()
    conversation_id = request.conversation_id or str(uuid.uuid4())
    git_token = settings.jenkins_git_token

    try:
        # Case 1: User provides a repository URL -> generate pipeline
        url = _extract_url(message)
        display_url = _to_browser_url(url) if url else None
        if url:
            result = await jenkins_pipeline_generator.generate_with_validation(
                repo_url=url,
                git_token=git_token,
                model="pipeline-generator-v5",
                max_fix_attempts=10
            )

            if not result.get("success") and not result.get("jenkinsfile"):
                return {
                    "conversation_id": conversation_id,
                    "message": f"**Error generating pipeline.** Could not create a valid Jenkinsfile for `{display_url}`.\n\nPlease check the repository URL and try again."
                }

            # Store pending pipeline for commit
            analysis = result.get("analysis", {})
            model_used = result.get("model_used", "unknown")
            template_source = result.get("template_source", "")

            _chat_pending[conversation_id] = {
                "repo_url": url,
                "jenkinsfile": result.get("jenkinsfile", ""),
                "dockerfile": result.get("dockerfile", ""),
                "analysis": analysis,
                "model_used": model_used,
                "template_source": template_source
            }

            # Build response message
            lang = analysis.get("language", "unknown")
            framework = analysis.get("framework", "generic")
            fix_attempts = result.get("fix_attempts", 0)
            has_warnings = result.get("has_warnings", False)

            # Source banner (matching GitLab chat style)
            if template_source == "reinforcement_learning":
                source_msg = "**Template exists in RAG** - using a proven pipeline that has succeeded before.\n\n"
            elif model_used == "default-template":
                source_msg = "**Using a built-in default template** for this language.\n\n"
            else:
                source_msg = f"**No template in RAG for this language.** LLM (`{model_used}`) is creating and testing a new pipeline configuration.\n\n"

            # Validation info
            if result.get("validation_skipped"):
                val_msg = "Validation: *Skipped (proven template)*\n\n"
            elif result.get("validation_passed"):
                val_msg = f"Validation: **Passed**"
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
                f"Generated **Jenkinsfile** and **Dockerfile** for `{display_url}`\n\n"
                f"- Language: **{lang}**\n"
                f"- Framework: **{framework}**\n\n"
                f"{val_msg}"
                f"### Jenkinsfile\n```groovy\n{result.get('jenkinsfile', '')[:3000]}\n```\n\n"
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
                    "message": "No pipeline to commit. Please provide a repository URL first to generate a Jenkinsfile."
                }

            # Build commit message
            analysis = pending.get("analysis", {})
            lang = analysis.get("language", "unknown")
            framework = analysis.get("framework", "generic")
            template_source = pending.get("template_source", "")
            model_used = pending.get("model_used", "unknown")

            if template_source == "reinforcement_learning":
                commit_msg = f"Add Jenkinsfile + Dockerfile [RL Template] - Proven {lang}/{framework} from ChromaDB"
            elif model_used == "default-template":
                commit_msg = f"Add Jenkinsfile + Dockerfile [Built-in Template] - Default {lang} configuration"
            else:
                commit_msg = f"Add Jenkinsfile + Dockerfile [LLM Generated] - {lang}/{framework} by {model_used}"

            commit_result = await jenkins_pipeline_generator.commit_to_repo(
                repo_url=pending["repo_url"],
                git_token=git_token,
                jenkinsfile=pending["jenkinsfile"],
                dockerfile=pending["dockerfile"],
                commit_message=commit_msg
            )

            if commit_result.get("success"):
                branch = commit_result.get("branch", "main")
                web_url = commit_result.get("web_url", "")

                # Derive job_name for multibranch pipeline: {repo}/job/{branch}
                parsed = jenkins_pipeline_generator.parse_repo_url(pending["repo_url"])
                job_name = f"{parsed['repo']}/job/{branch}"
                # Use hash-based project_id since Gitea has no numeric IDs (0 is falsy in JS)
                project_id = abs(hash(pending["repo_url"])) % (10**8)

                # Start background monitoring (like GitLab does in pipeline.py:372-382)
                progress = progress_store.create(project_id=project_id, branch=branch, max_attempts=10)
                progress.model_used = model_used
                background_tasks.add_task(
                    monitor_build_for_learning,
                    job_name=job_name,
                    repo_url=pending["repo_url"],
                    git_token=git_token,
                    branch=branch,
                    project_id=project_id,
                    jenkinsfile=pending["jenkinsfile"],
                    dockerfile=pending["dockerfile"],
                    language=analysis.get("language", "unknown"),
                    framework=analysis.get("framework", "generic"),
                )

                # Clean up pending
                del _chat_pending[conversation_id]

                # Build Jenkins build URL for the user
                jenkins_build_url = f"http://localhost:8080/jenkins/job/{parsed['repo']}/job/{branch}/"

                return {
                    "conversation_id": conversation_id,
                    "message": (
                        f"**Pipeline committed successfully!**\n\n"
                        f"- Branch: `{branch}`\n"
                        f"- Commit: `{commit_result.get('commit_id', 'N/A')[:12]}`\n"
                        f"- Gitea: [{web_url}]({web_url})\n"
                        f"- Jenkins: [{parsed['repo']} / {branch}]({jenkins_build_url})\n\n"
                        f"Monitoring Jenkins build for `{parsed['repo']}`..."
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
                        f"Pipeline generated for `{repo_url}` but not yet committed.\n\n"
                        f"Say **commit** to push the files, or provide a new URL to regenerate."
                    )
                }
            return {
                "conversation_id": conversation_id,
                "message": "No active pipeline session. Provide a repository URL to generate a Jenkinsfile."
            }

        # Case 4: Unknown message
        return {
            "conversation_id": conversation_id,
            "message": (
                "I can help you generate Jenkins pipelines with a full **9-stage** pipeline. Here's what I can do:\n\n"
                "1. **Generate a pipeline** - Provide a repository URL\n"
                "2. **Commit files** - Say 'commit' after reviewing the generated files\n"
                "3. **Check status** - Say 'status' to check the current state\n\n"
                "**Example:** `Generate a pipeline for http://localhost:3002/jenkins-projects/java-springboot-api`"
            )
        }

    except Exception as e:
        print(f"[Jenkins Chat] Error: {e}")
        return {
            "conversation_id": conversation_id,
            "message": f"**Error:** {str(e)}\n\nPlease check the backend logs and try again."
        }


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/analyze")
async def analyze_repository(request: AnalyzeRequest):
    """Analyze a Gitea repository to detect language, framework, and structure."""
    try:
        analysis = await jenkins_pipeline_generator.analyze_repository(
            request.repo_url,
            request.git_token
        )
        return {"success": True, **analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=GenerateJenkinsfileResponse)
async def generate_jenkinsfile(request: GenerateJenkinsfileRequest):
    """
    Generate Jenkinsfile and Dockerfile for a repository.

    Uses:
    1. Proven templates from ChromaDB (if available)
    2. LLM generation with reference templates
    3. Default templates as fallback
    """
    try:
        result = await jenkins_pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            git_token=request.git_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            agent_label=request.agent_label
        )

        # Auto-seed images in Nexus
        try:
            await ensure_images_in_nexus(result["jenkinsfile"])
        except Exception as e:
            print(f"[Jenkins] Image seeding warning: {e}")

        return GenerateJenkinsfileResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-validated")
async def generate_with_validation(request: GenerateWithValidationRequest):
    """
    Generate Jenkinsfile with validation and automatic LLM-based fixing.
    Iteratively validates and fixes until the pipeline passes or max attempts reached.
    """
    try:
        # Step 1: Generate
        result = await jenkins_pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            git_token=request.git_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            agent_label=request.agent_label
        )

        jenkinsfile = result["jenkinsfile"]
        dockerfile = result["dockerfile"]
        analysis = result["analysis"]

        # Step 2: Validate and fix iteratively
        fix_result = await jenkins_llm_fixer.iterative_fix(
            jenkinsfile=jenkinsfile,
            dockerfile=dockerfile,
            analysis=analysis,
            max_attempts=request.max_fix_attempts,
            model=request.model
        )

        # Step 3: Auto-seed images
        try:
            await ensure_images_in_nexus(fix_result["jenkinsfile"])
        except Exception as e:
            print(f"[Jenkins] Image seeding warning: {e}")

        return {
            "success": True,
            "jenkinsfile": fix_result["jenkinsfile"],
            "dockerfile": fix_result["dockerfile"],
            "analysis": analysis,
            "model_used": result["model_used"],
            "feedback_used": result["feedback_used"],
            "validation_passed": fix_result.get("success", False),
            "fix_attempts": fix_result.get("attempts", 0),
            "fix_history": fix_result.get("fix_history", []),
            "has_warnings": fix_result.get("has_warnings", False),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit", response_model=CommitResponse)
async def commit_jenkinsfile(request: CommitRequest, background_tasks: BackgroundTasks):
    """
    Commit generated Jenkinsfile and Dockerfile to the Gitea repository.
    Creates a new branch with the pipeline configuration.
    """
    try:
        result = await jenkins_pipeline_generator.commit_to_repo(
            repo_url=request.repo_url,
            git_token=request.git_token,
            jenkinsfile=request.jenkinsfile,
            dockerfile=request.dockerfile,
            branch_name=request.branch_name,
            commit_message=request.commit_message
        )
        return CommitResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status")
async def get_build_status(request: BuildStatusRequest):
    """Get Jenkins build status for a job."""
    try:
        status = await jenkins_pipeline_generator.get_build_status(
            job_name=request.job_name,
            build_number=request.build_number
        )
        return {"success": True, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger")
async def trigger_build(request: TriggerBuildRequest):
    """Trigger a Jenkins build for a job."""
    try:
        result = await jenkins_pipeline_generator.trigger_build(
            job_name=request.job_name
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def store_feedback(request: FeedbackRequest):
    """Store manual corrections for reinforcement learning."""
    try:
        # Compare original vs corrected files
        differences = await compare_and_learn(
            repo_url=request.repo_url,
            git_token=request.git_token,
            branch=request.branch,
            generated_files={
                "Jenkinsfile": request.original_jenkinsfile,
                "Dockerfile": request.original_dockerfile
            }
        )

        jenkinsfile_diff = differences.get("Jenkinsfile", {})
        dockerfile_diff = differences.get("Dockerfile", {})

        if jenkinsfile_diff.get("changed") or dockerfile_diff.get("changed"):
            analysis = await jenkins_pipeline_generator.analyze_repository(
                request.repo_url,
                request.git_token
            )

            success = await store_rl_feedback(
                original_jenkinsfile=request.original_jenkinsfile,
                corrected_jenkinsfile=request.corrected_jenkinsfile,
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
                    "jenkinsfile": jenkinsfile_diff.get("changed", False),
                    "dockerfile": dockerfile_diff.get("changed", False)
                }
            }
        else:
            return {
                "success": True,
                "message": "No changes detected between original and current files",
                "changes_detected": {"jenkinsfile": False, "dockerfile": False}
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
async def record_build_result(request: RecordResultRequest):
    """
    Record Jenkins build result for reinforcement learning.
    Called automatically by the learn-record step in Jenkinsfile post block.
    Also supports enhanced recording with repo_url/git_token for fetching actual files.
    """
    try:
        if request.repo_url and request.git_token and request.branch:
            # Enhanced: fetch actual files from repo and store
            result = await rl_record_build_result(
                repo_url=request.repo_url,
                git_token=request.git_token,
                branch=request.branch,
                job_name=request.job_name,
                build_number=request.build_number
            )
            return result
        else:
            # Basic: just record success status
            result = await jenkins_pipeline_generator.record_build_result(
                job_name=request.job_name,
                build_number=request.build_number,
                status=request.status
            )
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/successful")
async def get_successful_jenkinsfiles(
    language: str,
    framework: Optional[str] = None,
    limit: int = 10
):
    """Get successful Jenkinsfile configurations for a language/framework."""
    try:
        templates = await jenkins_pipeline_generator.get_best_template_files(
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
async def get_best_jenkinsfile(
    language: str,
    framework: Optional[str] = None
):
    """Get the best performing Jenkinsfile configuration."""
    try:
        best = await jenkins_pipeline_generator.get_best_template_files(
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
    """Manually store a proven Jenkinsfile template."""
    try:
        import hashlib
        import httpx
        from app.config import settings

        content = f"{request.jenkinsfile}\n{request.dockerfile}"
        content_hash = hashlib.md5(content.encode()).hexdigest()[:12]
        doc_id = f"manual_{request.language}_{request.framework}_{content_hash}"

        doc_content = f"""## Manual Jenkins Pipeline Template
Language: {request.language}
Framework: {request.framework}
Source: manual_upload
Description: {request.description or ''}

### Jenkinsfile
```groovy
{request.jenkinsfile}
```

### Dockerfile
```dockerfile
{request.dockerfile}
```
"""

        from app.services.jenkins_pipeline.templates import _resolve_collection_uuid

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Store in both template and successful collections
            for coll_name in ["jenkins_pipeline_templates", "jenkins_successful_pipelines"]:
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
async def get_jenkins_progress(project_id: int, branch: str):
    """Get real-time progress of Jenkins build monitoring and self-healing."""
    progress = progress_store.get(project_id, branch)
    if not progress:
        return {"found": False, "message": "No monitoring in progress for this pipeline"}
    return {"found": True, **progress.to_dict()}


@router.post("/workflow")
async def full_workflow(
    request: FullWorkflowRequest,
    background_tasks: BackgroundTasks
):
    """
    Complete workflow: analyze -> generate -> validate -> commit -> trigger -> monitor.

    Returns immediately with generation results, monitors build in background.
    """
    try:
        # Step 1: Generate pipeline files
        result = await jenkins_pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            git_token=request.git_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            agent_label=request.agent_label
        )

        # Step 2: Auto-seed images
        try:
            await ensure_images_in_nexus(result["jenkinsfile"])
        except Exception as e:
            print(f"[Jenkins Workflow] Image seeding warning: {e}")

        response = {
            "success": True,
            "generation": result
        }

        # Step 3: Commit if auto_commit is enabled
        if request.auto_commit:
            commit_result = await jenkins_pipeline_generator.commit_to_repo(
                repo_url=request.repo_url,
                git_token=request.git_token,
                jenkinsfile=result["jenkinsfile"],
                dockerfile=result["dockerfile"],
                branch_name=request.branch_name
            )
            response["commit"] = commit_result

            # Step 4: Trigger Jenkins build if job_name provided
            if commit_result.get("success") and request.job_name:
                trigger_result = await jenkins_pipeline_generator.trigger_build(
                    request.job_name
                )
                response["trigger"] = trigger_result

                # Step 5: Create progress tracking
                project_id = commit_result.get("project_id", 0)
                branch = commit_result.get("branch", "")
                prog = progress_store.create(project_id=project_id, branch=branch, max_attempts=10)
                prog.model_used = result.get("model_used", "unknown")

                # Step 6: Schedule background monitoring
                if trigger_result.get("success"):
                    background_tasks.add_task(
                        monitor_build_for_learning,
                        job_name=request.job_name,
                        repo_url=request.repo_url,
                        git_token=request.git_token,
                        branch=branch,
                        project_id=project_id,
                        jenkinsfile=result["jenkinsfile"],
                        dockerfile=result["dockerfile"],
                        language=result.get("analysis", {}).get("language", "unknown"),
                        framework=result.get("analysis", {}).get("framework", "generic"),
                    )
                    response["monitoring"] = {
                        "status": "scheduled",
                        "job_name": request.job_name,
                        "rl_enabled": True,
                        "self_healing_enabled": True,
                    }

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal")
async def self_heal_pipeline(request: SelfHealRequest):
    """
    Self-healing workflow: re-generate with LLM fix loop + commit.
    """
    try:
        # Generate with validation loop
        result = await jenkins_pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            git_token=request.git_token,
            additional_context=request.additional_context or "",
            use_template_only=False,
            agent_label=request.agent_label
        )

        jenkinsfile = result["jenkinsfile"]
        dockerfile = result["dockerfile"]
        analysis = result["analysis"]

        # Run iterative fix
        fix_result = await jenkins_llm_fixer.iterative_fix(
            jenkinsfile=jenkinsfile,
            dockerfile=dockerfile,
            analysis=analysis,
            max_attempts=request.max_attempts,
        )

        response = {
            "success": fix_result.get("success", False),
            "jenkinsfile": fix_result["jenkinsfile"],
            "dockerfile": fix_result["dockerfile"],
            "analysis": analysis,
            "fix_attempts": fix_result.get("attempts", 0),
            "fix_history": fix_result.get("fix_history", []),
        }

        if request.auto_commit and fix_result.get("success"):
            commit_result = await jenkins_pipeline_generator.commit_to_repo(
                repo_url=request.repo_url,
                git_token=request.git_token,
                jenkinsfile=fix_result["jenkinsfile"],
                dockerfile=fix_result["dockerfile"],
            )
            response["commit"] = commit_result

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal/async")
async def self_heal_pipeline_async(
    request: SelfHealRequest,
    background_tasks: BackgroundTasks
):
    """
    Self-healing workflow - async execution.
    Returns immediately, processes in background.
    """
    try:
        background_tasks.add_task(
            _run_self_heal,
            request.repo_url,
            request.git_token,
            request.additional_context or "",
            request.auto_commit,
            request.agent_label,
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
    """Validate Jenkinsfile and Dockerfile before committing."""
    try:
        errors = []
        warnings = []

        jenkinsfile = request.jenkinsfile.strip()
        dockerfile = request.dockerfile.strip()

        # Jenkinsfile validation
        if not jenkinsfile:
            errors.append("Jenkinsfile is empty")
        else:
            if 'pipeline {' not in jenkinsfile and 'pipeline{' not in jenkinsfile:
                errors.append("Missing 'pipeline { }' block")
            if 'agent' not in jenkinsfile:
                errors.append("Missing 'agent' directive")
            if 'stages {' not in jenkinsfile and 'stages{' not in jenkinsfile:
                errors.append("Missing 'stages { }' block")
            if 'environment' not in jenkinsfile:
                warnings.append("Missing 'environment' block")
            if 'post {' not in jenkinsfile and 'post{' not in jenkinsfile:
                warnings.append("Missing 'post { }' block")

            # Check for public registry references
            public_registries = ['docker.io/', 'gcr.io/', 'quay.io/', 'ghcr.io/']
            for reg in public_registries:
                if reg in jenkinsfile:
                    errors.append(f"Public registry reference found: {reg}")

            # Check required stages
            required = ['Compile', 'Build Image', 'Test Image', 'Static Analysis',
                       'SonarQube', 'Trivy Scan', 'Push Release']
            for stage in required:
                if f"stage('{stage}')" not in jenkinsfile and f'stage("{stage}")' not in jenkinsfile:
                    warnings.append(f"Missing stage: {stage}")

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
                "jenkinsfile_validation": {
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
async def fix_pipeline_error(request: FixRequest):
    """LLM Fix - Analyze Jenkins pipeline error and generate fix."""
    try:
        analysis = {
            "language": request.language or "unknown",
            "framework": request.framework or "generic",
            "package_manager": "unknown"
        }

        # Parse error log into error list
        error_lines = [line.strip() for line in request.error_log.split('\n') if line.strip()]

        result = await jenkins_llm_fixer.fix_pipeline(
            jenkinsfile=request.jenkinsfile,
            dockerfile=request.dockerfile,
            errors=error_lines,
            warnings=[],
            analysis=analysis,
        )

        return {
            "success": 'error' not in result,
            "fixed_files": {
                "jenkinsfile": result.get("jenkinsfile", request.jenkinsfile),
                "dockerfile": result.get("dockerfile", request.dockerfile),
            },
            "error": result.get("error"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Background Tasks
# ============================================================================

async def monitor_build_for_learning(
    job_name: str,
    repo_url: str = "",
    git_token: str = "",
    branch: str = "",
    project_id: int = 0,
    jenkinsfile: str = "",
    dockerfile: str = "",
    language: str = "unknown",
    framework: str = "generic",
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30
):
    """Background task to monitor Jenkins build, record results for RL, and trigger self-healing."""
    print(f"[Jenkins Monitor] Starting build monitor for {job_name}")

    # Trigger branch scan so Jenkins discovers the new branch quickly
    repo_name = job_name.split("/job/")[0] if "/job/" in job_name else job_name
    scan_result = await jenkins_pipeline_generator.trigger_scan(repo_name)
    print(f"[Jenkins Monitor] Branch scan triggered for {repo_name}: {scan_result.get('success')}")

    max_checks = (max_wait_minutes * 60) // check_interval_seconds

    for check_num in range(max_checks):
        if check_num > 0:
            await asyncio.sleep(check_interval_seconds)

        try:
            status = await jenkins_pipeline_generator.get_build_status(job_name)

            build_status = status.get("status", "unknown")
            build_number = status.get("build_number", 0)
            building = status.get("building", True)
            build_url = status.get("url", "")
            # Convert internal Jenkins URL to browser-accessible URL
            if build_url:
                build_url = build_url.replace("http://localhost:8080", "http://localhost:8080")

            print(f"[Jenkins Monitor] {job_name} #{build_number}: {build_status} (building={building})")

            if project_id and branch:
                # Fetch stage details when a build exists
                stage_msg = ""
                if build_number > 0:
                    stages = await jenkins_pipeline_generator.get_build_stages(job_name, build_number)
                    if stages:
                        stage_parts = []
                        for s in stages:
                            icon = {"SUCCESS": "\u2705", "FAILED": "\u274c", "IN_PROGRESS": "\u23f3", "NOT_EXECUTED": "\u23f8"}.get(s["status"], "\u2b1c")
                            dur = f" ({s['duration_sec']}s)" if s["duration_sec"] > 0 else ""
                            stage_parts.append(f"{icon} {s['name']}{dur}")
                        stage_msg = " | " + " \u2192 ".join(stage_parts)

                jenkins_link = f"http://localhost:8080/jenkins/job/{job_name}/{build_number}/console"
                if build_status == "not_found":
                    progress_store.update(project_id, branch, "build_running",
                        "Waiting for Jenkins to discover the branch...")
                elif building:
                    progress_store.update(project_id, branch, "build_running",
                        f"Build #{build_number} running{stage_msg} | [Console]({jenkins_link})")
                else:
                    progress_store.update(project_id, branch, "build_running",
                        f"Build #{build_number} finished: {build_status}{stage_msg}")

            if not building:
                if build_status == "success":
                    # Record for RL
                    if repo_url and git_token and branch:
                        await rl_record_build_result(
                            repo_url=repo_url,
                            git_token=git_token,
                            branch=branch,
                            job_name=job_name,
                            build_number=build_number
                        )
                    else:
                        await jenkins_pipeline_generator.record_build_result(
                            job_name, build_number
                        )
                    print(f"[Jenkins Monitor] Build success recorded for {job_name}")

                    if project_id and branch:
                        # Include final stage summary
                        stages = await jenkins_pipeline_generator.get_build_stages(job_name, build_number)
                        stage_parts = []
                        for s in stages:
                            icon = {"SUCCESS": "\u2705", "FAILED": "\u274c"}.get(s["status"], "\u2b1c")
                            stage_parts.append(f"{icon} {s['name']} ({s['duration_sec']}s)")
                        stage_summary = "\n".join(stage_parts) if stage_parts else ""
                        jenkins_link = f"http://localhost:8080/jenkins/job/{job_name}/{build_number}/console"
                        progress_store.complete(project_id, branch, "success",
                            f"Build #{build_number} succeeded! \u2705\n{stage_summary}\n[View Console]({jenkins_link})")
                    return

                elif build_status in ["failure", "unstable"]:
                    print(f"[Jenkins Monitor] Build FAILED for {job_name} - triggering self-heal")

                    if project_id and branch:
                        # Include failed stage info
                        stages = await jenkins_pipeline_generator.get_build_stages(job_name, build_number)
                        failed_stages = [s["name"] for s in stages if s["status"] == "FAILED"]
                        failed_info = f" (failed at: {', '.join(failed_stages)})" if failed_stages else ""
                        jenkins_link = f"http://localhost:8080/jenkins/job/{job_name}/{build_number}/console"
                        progress_store.update(project_id, branch, "build_failed",
                            f"Build #{build_number} failed{failed_info}. [Console]({jenkins_link}) | Starting self-healing...")

                    # Self-heal: re-generate with LLM fix and commit
                    if repo_url and git_token:
                        try:
                            analysis = {"language": language, "framework": framework, "package_manager": "unknown"}
                            fix_result = await jenkins_llm_fixer.iterative_fix(
                                jenkinsfile=jenkinsfile,
                                dockerfile=dockerfile,
                                analysis=analysis,
                                max_attempts=3,
                            )

                            # Track fixer model on progress
                            if project_id and branch and fix_result.get("fixer_model_used"):
                                prog = progress_store.get(project_id, branch)
                                if prog:
                                    prog.fixer_model_used = fix_result["fixer_model_used"]

                            if fix_result.get("success"):
                                await jenkins_pipeline_generator.commit_to_repo(
                                    repo_url=repo_url,
                                    git_token=git_token,
                                    jenkinsfile=fix_result["jenkinsfile"],
                                    dockerfile=fix_result["dockerfile"],
                                    branch_name=branch,
                                )
                                print(f"[Jenkins Monitor] Self-heal committed for {job_name}")

                                if project_id and branch:
                                    progress_store.complete(project_id, branch, "success",
                                        f"Pipeline fixed after {fix_result['attempts']} attempt(s)!")
                            else:
                                if project_id and branch:
                                    progress_store.complete(project_id, branch, "failed",
                                        f"Self-healing failed after {fix_result['attempts']} attempts.")
                        except Exception as heal_err:
                            print(f"[Jenkins Monitor] Self-heal error: {heal_err}")
                            if project_id and branch:
                                progress_store.complete(project_id, branch, "failed",
                                    f"Self-healing error: {heal_err}")
                    return

                else:
                    # aborted, not_built, etc.
                    print(f"[Jenkins Monitor] Build ended with status: {build_status}")
                    if project_id and branch:
                        progress_store.complete(project_id, branch, "failed",
                            f"Build #{build_number} ended with status: {build_status}")
                    return

        except Exception as e:
            print(f"[Jenkins Monitor] Error checking status: {e}")

    print(f"[Jenkins Monitor] Timeout waiting for build on {job_name}")
    if project_id and branch:
        progress_store.complete(project_id, branch, "failed",
            f"Timeout waiting for build after {max_wait_minutes} minutes.")


async def _run_self_heal(
    repo_url: str,
    git_token: str,
    additional_context: str,
    auto_commit: bool,
    agent_label: str,
    max_attempts: int = 10,
):
    """Background task for self-healing workflow."""
    try:
        result = await jenkins_pipeline_generator.generate_pipeline_files(
            repo_url=repo_url,
            git_token=git_token,
            additional_context=additional_context,
            use_template_only=False,
            agent_label=agent_label
        )

        analysis = result.get("analysis", {})

        fix_result = await jenkins_llm_fixer.iterative_fix(
            jenkinsfile=result["jenkinsfile"],
            dockerfile=result["dockerfile"],
            analysis=analysis,
            max_attempts=max_attempts,
        )

        if auto_commit and fix_result.get("success"):
            await jenkins_pipeline_generator.commit_to_repo(
                repo_url=repo_url,
                git_token=git_token,
                jenkinsfile=fix_result["jenkinsfile"],
                dockerfile=fix_result["dockerfile"],
            )
            print(f"[Jenkins Self-Heal] Committed fixed pipeline for {repo_url}")
        elif not fix_result.get("success"):
            print(f"[Jenkins Self-Heal] Fix failed after {fix_result.get('attempts')} attempts")
    except Exception as e:
        print(f"[Jenkins Self-Heal] Error: {e}")
