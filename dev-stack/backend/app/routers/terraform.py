"""
File: terraform.py
Purpose: Provides the full lifecycle for Terraform HCL configuration generation -- chat interface,
    multi-file .tf generation with LLM validation, terraform init/plan/apply execution, commit
    to Gitea, reinforcement-learning feedback, and self-healing fix loops, supporting vSphere,
    Azure, AWS, and GCP providers with VM, Kubernetes, container, and networking resource types.
When Used: Invoked by the frontend Terraform Generator tool card chat and API calls when a user
    selects a cloud provider and resource type, describes infrastructure requirements, runs
    terraform plan, or commits .tf files to Git via the /terraform/* routes.
Why Created: Extends the platform's code-generation pattern (used for CI pipelines) to
    infrastructure-as-code, with its own chat state, workspace management, provider-specific
    environment variable injection, and terraform CLI execution.
"""
import re
import uuid
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.config import settings
from app.services.terraform import terraform_generator
from app.services.terraform.analyzer import get_providers_tree, build_context_description
from app.services.terraform.workspace import workspace_manager
from app.services.terraform.executor import terraform_executor
from app.services.terraform.learning import (
    get_relevant_feedback,
    store_feedback as store_rl_feedback,
    store_successful_config,
    record_plan_result,
)
from app.services.terraform.committer import commit_to_repo
from app.services.terraform_llm_fixer import terraform_llm_fixer
from app.services.pipeline_progress import progress_store

router = APIRouter(prefix="/terraform", tags=["Terraform Generator"])


# ============================================================================
# Request/Response Models
# ============================================================================

class TerraformContext(BaseModel):
    provider: str           # "vsphere", "azure", "aws", "gcp"
    resource_type: str      # "vm", "kubernetes", "containers", "networking"
    sub_type: Optional[str] = None  # "linux", "windows"


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    context: Optional[TerraformContext] = None


class GenerateRequest(BaseModel):
    context: TerraformContext
    additional_requirements: Optional[str] = None
    model: str = "pipeline-generator-v5"
    use_template_only: bool = False


class GenerateValidatedRequest(BaseModel):
    context: TerraformContext
    additional_requirements: Optional[str] = None
    model: str = "pipeline-generator-v5"
    max_fix_attempts: int = 5


class PlanRequest(BaseModel):
    files: Dict[str, str]
    context: TerraformContext
    terraform_tfvars: Optional[str] = None


class ApplyRequest(BaseModel):
    workspace_id: str
    auto_approve: bool = False


class CommitRequest(BaseModel):
    repo_url: str
    git_token: str
    files: Dict[str, str]
    branch_name: Optional[str] = None
    commit_message: str = "Add Terraform configuration [AI Generated]"


class FixRequest(BaseModel):
    files: Dict[str, str]
    error_log: str
    context: TerraformContext


class SelfHealRequest(BaseModel):
    context: TerraformContext
    additional_requirements: Optional[str] = None
    max_attempts: int = 10
    terraform_tfvars: Optional[str] = None


class FeedbackRequest(BaseModel):
    context: TerraformContext
    original_files: Dict[str, str]
    corrected_files: Dict[str, str]
    error_type: str
    fix_description: str


class StoreTemplateRequest(BaseModel):
    provider: str
    resource_type: str
    sub_type: Optional[str] = None
    files: Dict[str, str]
    description: Optional[str] = None


class DestroyRequest(BaseModel):
    workspace_id: str


# ============================================================================
# Chat Interface (for frontend chatbot)
# ============================================================================

# In-memory state for chat conversations
_chat_pending: Dict[str, Dict] = {}  # conversation_id -> pending terraform data
_chat_context: Dict[str, TerraformContext] = {}  # conversation_id -> context


def _is_approval(text: str) -> bool:
    """Check if the user message is approving deployment/commit."""
    lower = text.lower().strip()
    approval_words = [
        'yes', 'commit', 'approve', 'go ahead', 'do it', 'push',
        'deploy', 'confirm', 'ok', 'sure', 'proceed', 'ship it',
        'apply', 'apply it', 'yes please', 'lgtm',
    ]
    return any(lower.startswith(w) or lower == w for w in approval_words)


def _is_destroy(text: str) -> bool:
    """Check if user wants to destroy infrastructure."""
    lower = text.lower().strip()
    return any(kw in lower for kw in ['destroy', 'tear down', 'teardown', 'delete infra'])


def _is_status_check(text: str) -> bool:
    """Check if user is asking about status."""
    lower = text.lower().strip()
    return any(kw in lower for kw in ['status', 'check', 'result', 'how is', 'progress'])


def _is_plan_request(text: str) -> bool:
    """Check if user wants to run terraform plan."""
    lower = text.lower().strip()
    return any(kw in lower for kw in ['plan', 'validate', 'check plan', 'dry run', 'dry-run'])


@router.post("/chat")
async def terraform_chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Chat interface for Terraform Generator.

    Handles natural language messages:
    - Description/requirements -> generate Terraform config
    - "apply" / "commit" -> deploy or commit
    - "plan" -> run terraform plan
    - "status" -> check workspace status
    - "destroy" -> terraform destroy
    """
    message = request.message.strip()
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Store context if provided
    if request.context:
        _chat_context[conversation_id] = request.context

    context = _chat_context.get(conversation_id)

    try:
        # Case 1: Apply/commit approval
        if _is_approval(message):
            pending = _chat_pending.get(conversation_id)
            if not pending:
                return {
                    "conversation_id": conversation_id,
                    "message": "No Terraform configuration to apply. Please describe your infrastructure requirements first.",
                }

            files = pending.get("files", {})

            # Commit to Gitea if user said "commit"
            if "commit" in message.lower():
                git_token = settings.terraform_git_token or settings.jenkins_git_token
                if not git_token:
                    return {
                        "conversation_id": conversation_id,
                        "message": "**Error:** No Git token configured for Terraform. Set `TERRAFORM_GIT_TOKEN` in environment.",
                    }

                # TODO: Make repo URL configurable
                repo_url = f"{settings.terraform_git_url}/terraform-projects/infrastructure"
                commit_result = await commit_to_repo(
                    repo_url=repo_url,
                    git_token=git_token,
                    files=files,
                    commit_message=f"Add Terraform config [{context.provider}/{context.resource_type}] [AI Generated]" if context else "Add Terraform configuration [AI Generated]",
                )

                if commit_result.get("success"):
                    web_url = commit_result.get("web_url", "")
                    return {
                        "conversation_id": conversation_id,
                        "message": (
                            f"**Terraform configuration committed!**\n\n"
                            f"- Branch: `{commit_result.get('branch', 'N/A')}`\n"
                            f"- Commit: `{commit_result.get('commit_id', 'N/A')[:12]}`\n"
                            f"- Repository: [{web_url}]({web_url})\n\n"
                            f"You can now clone the repo and run `terraform init && terraform plan`."
                        ),
                    }
                else:
                    return {
                        "conversation_id": conversation_id,
                        "message": f"**Commit failed:** {commit_result.get('error', 'Unknown error')}",
                    }

            # Otherwise, show the plan/apply info
            return {
                "conversation_id": conversation_id,
                "message": (
                    "**Ready to proceed!** You can:\n\n"
                    "- Say **\"commit\"** to push the .tf files to a Git repository\n"
                    "- Say **\"plan\"** to run `terraform plan` and validate\n"
                    "- Or describe additional changes you'd like to make"
                ),
            }

        # Case 2: Plan request
        if _is_plan_request(message):
            pending = _chat_pending.get(conversation_id)
            if not pending:
                return {
                    "conversation_id": conversation_id,
                    "message": "No Terraform configuration to plan. Please describe your requirements first.",
                }

            files = pending.get("files", {})
            workspace_id = workspace_manager.create(
                pending.get("provider", "unknown"),
                pending.get("resource_type", "unknown"),
                files,
            )

            workspace_path = workspace_manager.get_path(workspace_id)
            env_vars = _get_provider_env_vars(pending.get("provider", ""))

            # Run init + plan
            init_result = await terraform_executor.init(workspace_path)
            if not init_result["success"]:
                workspace_manager.cleanup(workspace_id)
                return {
                    "conversation_id": conversation_id,
                    "message": f"**Terraform init failed:**\n```\n{init_result['output'][:2000]}\n```\n\nWould you like me to fix these errors?",
                }

            plan_result = await terraform_executor.plan(workspace_path, env_vars=env_vars)
            workspace_manager.cleanup(workspace_id)

            if plan_result["success"]:
                changes = plan_result.get("resource_changes", {})
                return {
                    "conversation_id": conversation_id,
                    "message": (
                        f"**Terraform plan succeeded!**\n\n"
                        f"Resources: **{changes.get('add', 0)}** to add, "
                        f"**{changes.get('change', 0)}** to change, "
                        f"**{changes.get('destroy', 0)}** to destroy\n\n"
                        f"<details><summary>Plan output</summary>\n\n```\n{plan_result['output'][:3000]}\n```\n</details>\n\n"
                        f"Say **\"commit\"** to save to Git, or **\"apply\"** to deploy."
                    ),
                }
            else:
                return {
                    "conversation_id": conversation_id,
                    "message": f"**Terraform plan failed:**\n```\n{plan_result['output'][:2000]}\n```\n\nI'll try to fix the errors. One moment...",
                }

        # Case 3: Destroy
        if _is_destroy(message):
            return {
                "conversation_id": conversation_id,
                "message": "**Destroy** is not yet supported via chat. Please run `terraform destroy` manually in your workspace.",
            }

        # Case 4: Status check
        if _is_status_check(message):
            pending = _chat_pending.get(conversation_id)
            if pending:
                ctx = pending.get("context_desc", "unknown")
                file_count = len(pending.get("files", {}))
                return {
                    "conversation_id": conversation_id,
                    "message": (
                        f"**Current session:** Terraform config for {ctx}\n"
                        f"- Files generated: {file_count}\n"
                        f"- Status: Ready to commit or plan\n\n"
                        f"Say **\"commit\"** to push to Git, **\"plan\"** to validate, or describe changes."
                    ),
                }
            return {
                "conversation_id": conversation_id,
                "message": "No active Terraform session. Describe your infrastructure requirements to get started.",
            }

        # Case 5: Generate new configuration (default for any other message)
        if not context:
            return {
                "conversation_id": conversation_id,
                "message": (
                    "Please select a **cloud provider** and **resource type** from the navigation cards first, "
                    "then describe your requirements here.\n\n"
                    "Or tell me what you need, e.g.:\n"
                    "- *\"Create a Linux VM with 4 CPUs and 16GB RAM on Azure\"*\n"
                    "- *\"Set up a 3-node Kubernetes cluster on AWS\"*\n"
                    "- *\"Create a VPC with public and private subnets on GCP\"*"
                ),
            }

        context_desc = build_context_description(context.provider, context.resource_type, context.sub_type)

        result = await terraform_generator.generate_with_validation(
            provider=context.provider,
            resource_type=context.resource_type,
            sub_type=context.sub_type,
            additional_requirements=message,
            model="pipeline-generator-v5",
            max_fix_attempts=5,
        )

        if not result.get("success"):
            return {
                "conversation_id": conversation_id,
                "message": f"**Error generating Terraform config:** {result.get('error', 'Unknown error')}\n\nPlease try again with more specific requirements.",
            }

        files = result.get("files", {})
        model_used = result.get("model_used", "unknown")

        # Store pending for commit/apply
        _chat_pending[conversation_id] = {
            "files": files,
            "provider": context.provider,
            "resource_type": context.resource_type,
            "sub_type": context.sub_type,
            "context_desc": context_desc,
            "model_used": model_used,
        }

        # Source banner
        if model_used == "chromadb-successful":
            source_msg = "**Template exists in RAG** - using a proven configuration.\n\n"
        elif model_used == "default-template":
            source_msg = "**Using built-in default template** for this resource type.\n\n"
        else:
            source_msg = f"**LLM-generated** configuration (`{model_used}`).\n\n"

        # Validation info
        if result.get("validation_skipped"):
            val_msg = "Validation: *Skipped (proven template)*\n\n"
        elif result.get("validation_passed"):
            fix_attempts = result.get("fix_attempts", 0)
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

        # Build file display
        file_sections = []
        for fname, content in files.items():
            if content.strip():
                lang = "hcl" if fname.endswith(".tf") else ""
                file_sections.append(f"### {fname}\n```{lang}\n{content[:2000]}\n```")

        files_display = "\n\n".join(file_sections)

        response_msg = (
            f"{source_msg}"
            f"Generated Terraform configuration for **{context_desc}**\n\n"
            f"{val_msg}"
            f"{files_display}\n\n"
            f"**Next steps:**\n"
            f"- Say **\"plan\"** to run `terraform plan`\n"
            f"- Say **\"commit\"** to push to Git\n"
            f"- Or describe changes you'd like to make"
        )

        return {
            "conversation_id": conversation_id,
            "message": response_msg,
        }

    except Exception as e:
        print(f"[Terraform Chat] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "conversation_id": conversation_id,
            "message": f"**Error:** {str(e)}\n\nPlease check the backend logs and try again.",
        }


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/providers")
async def get_providers():
    """Return the provider/resource/subtype tree for frontend rendering."""
    return get_providers_tree()


@router.post("/generate")
async def generate_terraform(request: GenerateRequest):
    """Generate Terraform HCL files for a given context."""
    try:
        result = await terraform_generator.generate_terraform_files(
            provider=request.context.provider,
            resource_type=request.context.resource_type,
            sub_type=request.context.sub_type,
            additional_requirements=request.additional_requirements,
            model=request.model,
            use_template_only=request.use_template_only,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-validated")
async def generate_validated(request: GenerateValidatedRequest):
    """Generate Terraform files with validation and auto-fix loop."""
    try:
        result = await terraform_generator.generate_with_validation(
            provider=request.context.provider,
            resource_type=request.context.resource_type,
            sub_type=request.context.sub_type,
            additional_requirements=request.additional_requirements,
            model=request.model,
            max_fix_attempts=request.max_fix_attempts,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plan")
async def run_plan(request: PlanRequest):
    """Run terraform init + plan on provided HCL files."""
    workspace_id = None
    try:
        workspace_id = workspace_manager.create(
            request.context.provider,
            request.context.resource_type,
            request.files,
        )
        workspace_path = workspace_manager.get_path(workspace_id)

        if request.terraform_tfvars:
            import os
            tfvars_path = os.path.join(workspace_path, "terraform.tfvars")
            with open(tfvars_path, "w") as f:
                f.write(request.terraform_tfvars)

        env_vars = _get_provider_env_vars(request.context.provider)

        init_result = await terraform_executor.init(workspace_path)
        if not init_result["success"]:
            return {
                "success": False,
                "stage": "init",
                "output": init_result["output"],
                "errors": init_result["errors"],
            }

        plan_result = await terraform_executor.plan(workspace_path, env_vars=env_vars)
        return {
            "success": plan_result["success"],
            "stage": "plan",
            "output": plan_result["output"],
            "errors": plan_result.get("errors", []),
            "warnings": plan_result.get("warnings", []),
            "resource_changes": plan_result.get("resource_changes"),
            "workspace_id": workspace_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if workspace_id:
            workspace_manager.cleanup(workspace_id)


@router.post("/apply")
async def run_apply(request: ApplyRequest):
    """Run terraform apply on a workspace."""
    workspace_path = workspace_manager.get_path(request.workspace_id)
    if not workspace_path:
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        env_vars = {}
        info = workspace_manager.get_info(request.workspace_id)
        if info:
            env_vars = _get_provider_env_vars(info.get("provider", ""))

        result = await terraform_executor.apply(
            workspace_path,
            auto_approve=request.auto_approve,
            env_vars=env_vars,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit")
async def commit_terraform(request: CommitRequest):
    """Commit .tf files to a Gitea repository."""
    try:
        result = await commit_to_repo(
            repo_url=request.repo_url,
            git_token=request.git_token,
            files=request.files,
            branch_name=request.branch_name,
            commit_message=request.commit_message,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix")
async def fix_terraform(request: FixRequest):
    """Single LLM fix pass given error log."""
    try:
        errors = [request.error_log] if request.error_log else []
        result = await terraform_llm_fixer.fix_terraform(
            files=request.files,
            errors=errors,
            warnings=[],
            provider=request.context.provider,
            resource_type=request.context.resource_type,
            sub_type=request.context.sub_type,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal")
async def self_heal(request: SelfHealRequest):
    """Full self-healing: generate -> plan -> fix -> retry loop."""
    try:
        # Generate initial files
        gen_result = await terraform_generator.generate_terraform_files(
            provider=request.context.provider,
            resource_type=request.context.resource_type,
            sub_type=request.context.sub_type,
            additional_requirements=request.additional_requirements,
        )

        if not gen_result.get("success"):
            return gen_result

        # Run iterative fix
        fix_result = await terraform_llm_fixer.iterative_fix(
            files=gen_result["files"],
            provider=request.context.provider,
            resource_type=request.context.resource_type,
            sub_type=request.context.sub_type,
            max_attempts=request.max_attempts,
            terraform_tfvars=request.terraform_tfvars,
        )

        return {
            "success": fix_result.get("success", False),
            "files": fix_result.get("files", {}),
            "attempts": fix_result.get("attempts", 0),
            "fix_history": fix_result.get("fix_history", []),
            "model_used": gen_result.get("model_used", "unknown"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def store_feedback(request: FeedbackRequest):
    """Store correction feedback for RL."""
    try:
        result = await store_rl_feedback(
            original_files=request.original_files,
            corrected_files=request.corrected_files,
            provider=request.context.provider,
            resource_type=request.context.resource_type,
            error_type=request.error_type,
            fix_description=request.fix_description,
        )
        return {"success": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/history")
async def feedback_history(provider: Optional[str] = None, resource_type: Optional[str] = None):
    """Get feedback history filtered by provider/resource."""
    try:
        feedback = await get_relevant_feedback(
            provider=provider or "any",
            resource_type=resource_type or "any",
            limit=20,
        )
        return {"success": True, "feedback": feedback}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/record")
async def learn_record(provider: str, resource_type: str, success: bool, plan_output: str = ""):
    """Record a plan/apply result for RL."""
    try:
        result = await record_plan_result(
            workspace_id="manual",
            provider=provider,
            resource_type=resource_type,
            success=success,
            plan_output=plan_output,
        )
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/successful")
async def get_successful(provider: Optional[str] = None, resource_type: Optional[str] = None):
    """Get successful Terraform configs."""
    from app.services.terraform.templates import get_best_template_files
    try:
        files = await get_best_template_files(
            provider=provider or "any",
            resource_type=resource_type or "any",
        )
        return {"success": True, "files": files}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/learn/store-template")
async def store_template(request: StoreTemplateRequest):
    """Manually store a proven Terraform template."""
    try:
        result = await store_successful_config(
            files=request.files,
            provider=request.provider,
            resource_type=request.resource_type,
            sub_type=request.sub_type,
        )
        return {"success": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/{workspace_id}")
async def get_progress(workspace_id: str):
    """Poll terraform operation progress."""
    # Use project_id=hash of workspace_id for compatibility with progress_store
    project_id = abs(hash(workspace_id)) % (10**8)
    progress = progress_store.get(project_id, workspace_id)
    if progress:
        return {"found": True, **progress.to_dict()}
    return {"found": False}


@router.post("/destroy")
async def destroy_terraform(request: DestroyRequest):
    """Run terraform destroy on a workspace."""
    workspace_path = workspace_manager.get_path(request.workspace_id)
    if not workspace_path:
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        env_vars = {}
        info = workspace_manager.get_info(request.workspace_id)
        if info:
            env_vars = _get_provider_env_vars(info.get("provider", ""))

        result = await terraform_executor.destroy(
            workspace_path,
            auto_approve=True,
            env_vars=env_vars,
        )
        workspace_manager.cleanup(request.workspace_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workspace/{workspace_id}")
async def cleanup_workspace(workspace_id: str):
    """Cleanup a terraform workspace."""
    workspace_manager.cleanup(workspace_id)
    return {"success": True, "message": f"Workspace {workspace_id} cleaned up"}


# ============================================================================
# Helper Functions
# ============================================================================

def _get_provider_env_vars(provider: str) -> Dict[str, str]:
    """Get cloud provider environment variables for terraform CLI."""
    env_vars = {}

    if provider == "vsphere":
        if settings.terraform_vsphere_server:
            env_vars["VSPHERE_SERVER"] = settings.terraform_vsphere_server
        if settings.terraform_vsphere_user:
            env_vars["VSPHERE_USER"] = settings.terraform_vsphere_user
        if settings.terraform_vsphere_password:
            env_vars["VSPHERE_PASSWORD"] = settings.terraform_vsphere_password

    elif provider == "azure":
        if settings.terraform_azure_subscription_id:
            env_vars["ARM_SUBSCRIPTION_ID"] = settings.terraform_azure_subscription_id
        if settings.terraform_azure_client_id:
            env_vars["ARM_CLIENT_ID"] = settings.terraform_azure_client_id
        if settings.terraform_azure_client_secret:
            env_vars["ARM_CLIENT_SECRET"] = settings.terraform_azure_client_secret
        if settings.terraform_azure_tenant_id:
            env_vars["ARM_TENANT_ID"] = settings.terraform_azure_tenant_id

    elif provider == "aws":
        if settings.terraform_aws_access_key:
            env_vars["AWS_ACCESS_KEY_ID"] = settings.terraform_aws_access_key
        if settings.terraform_aws_secret_key:
            env_vars["AWS_SECRET_ACCESS_KEY"] = settings.terraform_aws_secret_key
        if settings.terraform_aws_region:
            env_vars["AWS_DEFAULT_REGION"] = settings.terraform_aws_region

    elif provider == "gcp":
        if settings.terraform_gcp_project:
            env_vars["GOOGLE_PROJECT"] = settings.terraform_gcp_project
        if settings.terraform_gcp_credentials_file:
            env_vars["GOOGLE_APPLICATION_CREDENTIALS"] = settings.terraform_gcp_credentials_file

    return env_vars
