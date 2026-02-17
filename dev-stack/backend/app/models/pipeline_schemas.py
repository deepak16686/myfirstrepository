"""
Pipeline Generator Request/Response Models

Pydantic models for pipeline generation, validation, commit,
reinforcement learning, and self-healing endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ============================================================================
# Pipeline Generation
# ============================================================================

class GeneratePipelineRequest(BaseModel):
    """Request to generate pipeline files"""
    repo_url: str = Field(..., description="GitLab repository URL")
    gitlab_token: str = Field(..., description="GitLab access token")
    additional_context: Optional[str] = Field(
        None,
        description="Additional requirements or context for generation"
    )
    model: str = Field(
        default="pipeline-generator-v5",
        description="Ollama model to use for generation"
    )
    use_template_only: bool = Field(
        default=False,
        description="If True, skip LLM and use default templates directly"
    )


class GeneratePipelineResponse(BaseModel):
    """Response with generated pipeline files"""
    success: bool
    gitlab_ci: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int


class GenerateWithValidationRequest(BaseModel):
    """Request to generate pipeline with dry-run validation and auto-fixing"""
    repo_url: str = Field(..., description="GitLab repository URL")
    gitlab_token: str = Field(..., description="GitLab access token")
    additional_context: Optional[str] = Field(
        None,
        description="Additional requirements or context for generation"
    )
    model: str = Field(
        default="pipeline-generator-v5",
        description="Ollama model to use for generation"
    )
    max_fix_attempts: int = Field(
        default=3,
        description="Maximum number of LLM fix attempts if validation fails"
    )
    store_on_success: bool = Field(
        default=True,
        description="Store successful templates in ChromaDB for future use"
    )


class GenerateWithValidationResponse(BaseModel):
    """Response with validated pipeline files"""
    success: bool
    gitlab_ci: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int
    validation_passed: bool
    validation_skipped: Optional[bool] = None
    validation_reason: Optional[str] = None
    validation_results: Optional[Dict[str, Any]] = None
    validation_errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    fix_attempts: Optional[int] = None
    fix_history: Optional[List[Dict[str, Any]]] = None


# ============================================================================
# Commit
# ============================================================================

class CommitRequest(BaseModel):
    """Request to commit files to GitLab"""
    repo_url: str
    gitlab_token: str
    gitlab_ci: str
    dockerfile: str
    branch_name: Optional[str] = Field(
        None,
        description="Branch name (auto-generated if not provided)"
    )
    commit_message: str = Field(
        default="Add CI/CD pipeline configuration [AI Generated]"
    )


class CommitResponse(BaseModel):
    """Response from commit operation"""
    success: bool
    commit_id: str
    branch: str
    web_url: Optional[str]
    project_id: int


# ============================================================================
# Pipeline Status & Validation
# ============================================================================

class PipelineStatusRequest(BaseModel):
    """Request to get pipeline status"""
    repo_url: str
    gitlab_token: str
    branch: str


class DryRunRequest(BaseModel):
    """Request to validate pipeline without committing"""
    gitlab_ci: str = Field(..., description="Pipeline YAML to validate")
    dockerfile: str = Field(..., description="Dockerfile to validate")
    gitlab_token: Optional[str] = Field(None, description="GitLab token for CI lint API (optional)")
    project_path: Optional[str] = Field(None, description="Project path for project-specific lint (optional)")


class DryRunResponse(BaseModel):
    """Response with validation results"""
    success: bool
    valid: bool
    errors: List[str]
    warnings: List[str]
    validation_results: Dict[str, Any]
    summary: str


# ============================================================================
# Feedback & Reinforcement Learning
# ============================================================================

class FeedbackRequest(BaseModel):
    """Request to store feedback for reinforcement learning"""
    repo_url: str
    gitlab_token: str
    branch: str
    original_gitlab_ci: str
    original_dockerfile: str
    error_type: str = Field(..., description="Type of error that was fixed")
    fix_description: str = Field(..., description="Description of what was fixed")


class RecordPipelineResultRequest(BaseModel):
    """Request to record pipeline result for RL"""
    repo_url: str
    gitlab_token: str
    branch: str
    pipeline_id: int


class StoreTemplateRequest(BaseModel):
    """Request to store a pipeline template manually"""
    language: str
    framework: str = "generic"
    gitlab_ci: str
    dockerfile: Optional[str] = None
    description: Optional[str] = None


# ============================================================================
# Workflow
# ============================================================================

class FullWorkflowRequest(BaseModel):
    """Request for complete workflow: generate -> commit -> monitor"""
    repo_url: str
    gitlab_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    auto_commit: bool = False  # Default to False - require user approval
    branch_name: Optional[str] = None
    use_template_only: bool = Field(
        default=False,
        description="If True, skip LLM and use default templates directly"
    )


# ============================================================================
# Self-Healing & LLM Fix
# ============================================================================

class SelfHealRequest(BaseModel):
    """Request for self-healing pipeline workflow"""
    repo_url: str = Field(..., description="GitLab repository URL")
    gitlab_token: str = Field(..., description="GitLab access token")
    additional_context: Optional[str] = Field(
        None,
        description="Additional context for LLM generation"
    )
    auto_commit: bool = Field(
        default=True,
        description="Automatically commit and run pipeline"
    )
    max_attempts: int = Field(
        default=10,
        description="Maximum fix attempts before giving up"
    )


class FixRequest(BaseModel):
    """Request for LLM fix"""
    dockerfile: str
    gitlab_ci: str
    error_log: str = Field(..., description="Error log from failed job")
    job_name: str = Field(default="unknown", description="Name of failed job")
    language: str = Field(default="unknown")
    framework: str = Field(default="generic")


class FixFromJobRequest(BaseModel):
    """Request to fix from GitLab job ID"""
    dockerfile: str
    gitlab_ci: str
    job_id: int
    project_id: int
    gitlab_token: str
    language: str = "unknown"
    framework: str = "generic"
