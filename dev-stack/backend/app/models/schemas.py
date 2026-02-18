"""
File: app/models/schemas.py
Purpose: Pydantic schemas for general-purpose API requests and responses -- covers tool
    configuration CRUD, GitLab/SonarQube/Trivy/Nexus resource models, unified AI tool-call
    contracts, connectivity reporting, and Jira access-request models.
When Used: Imported by routers (tools, gitlab, sonarqube, trivy, nexus, unified, connectivity)
    and services that need typed representations of external tool resources.
Why Created: Provides a shared schema library for all non-pipeline-specific endpoints, keeping
    data contracts centralized so that multiple routers can reference the same model classes
    (e.g., ToolInfo, APIResponse, ConnectivityResult) without duplication.
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ============================================================================
# Common Schemas
# ============================================================================

class ToolStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ToolInfo(BaseModel):
    name: str
    enabled: bool
    status: ToolStatus
    base_url: str
    version: Optional[str] = None


class ToolConfigCreate(BaseModel):
    name: str
    base_url: str
    enabled: bool = True
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ToolConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    enabled: Optional[bool] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


# ============================================================================
# GitLab Schemas
# ============================================================================

class GitLabProject(BaseModel):
    id: int
    name: str
    path_with_namespace: str
    description: Optional[str] = None
    web_url: str
    default_branch: Optional[str] = None
    visibility: str
    created_at: Optional[datetime] = None


class GitLabPipeline(BaseModel):
    id: int
    project_id: int
    status: str
    ref: str
    sha: str
    web_url: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GitLabJob(BaseModel):
    id: int
    name: str
    stage: str
    status: str
    web_url: str
    duration: Optional[float] = None


class GitLabTriggerPipeline(BaseModel):
    ref: str = "main"
    variables: Optional[Dict[str, str]] = None


# ============================================================================
# SonarQube Schemas
# ============================================================================

class SonarQubeProject(BaseModel):
    key: str
    name: str
    qualifier: str
    visibility: Optional[str] = None
    last_analysis_date: Optional[str] = None


class SonarQubeMetric(BaseModel):
    metric: str
    value: str
    component: str


class SonarQubeQualityGate(BaseModel):
    project_key: str
    status: str
    conditions: List[Dict[str, Any]] = []


class SonarQubeIssue(BaseModel):
    key: str
    rule: str
    severity: str
    component: str
    message: str
    line: Optional[int] = None
    status: str
    type: str


class SonarQubeAnalysisRequest(BaseModel):
    project_key: str
    project_name: Optional[str] = None
    sources: str = "."


# ============================================================================
# Trivy Schemas
# ============================================================================

class TrivyScanRequest(BaseModel):
    image: str
    severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
    ignore_unfixed: bool = False


class TrivyVulnerability(BaseModel):
    vulnerability_id: str
    pkg_name: str
    installed_version: str
    fixed_version: Optional[str] = None
    severity: str
    title: Optional[str] = None
    description: Optional[str] = None


class TrivyScanResult(BaseModel):
    target: str
    vulnerabilities: List[TrivyVulnerability] = []
    total_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int


# ============================================================================
# Nexus Schemas
# ============================================================================

class NexusRepository(BaseModel):
    name: str
    format: str
    type: str
    url: str
    online: bool


class NexusComponent(BaseModel):
    id: str
    repository: str
    format: str
    group: Optional[str] = None
    name: str
    version: str


class NexusAsset(BaseModel):
    id: str
    path: str
    download_url: str
    format: str
    content_type: Optional[str] = None


class NexusUploadRequest(BaseModel):
    repository: str
    group_id: str
    artifact_id: str
    version: str
    packaging: str = "jar"


# ============================================================================
# Pipeline Schemas
# ============================================================================

class PipelineStage(BaseModel):
    name: str
    status: str
    duration: Optional[float] = None
    jobs: List[Dict[str, Any]] = []


class PipelineRun(BaseModel):
    id: str
    project: str
    source: str  # gitlab, jenkins, etc.
    status: str
    stages: List[PipelineStage] = []
    created_at: datetime
    finished_at: Optional[datetime] = None
    web_url: Optional[str] = None


# ============================================================================
# Unified Tool Call Schema (for AI integration)
# ============================================================================

class ToolCallRequest(BaseModel):
    """Schema for AI-initiated tool calls"""
    tool: str
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    """Response from tool call"""
    tool: str
    action: str
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time: float


# ============================================================================
# Connectivity Schemas
# ============================================================================

class AccessGroup(BaseModel):
    name: str
    description: str


class ConnectivityResult(BaseModel):
    name: str
    display_name: str
    icon: str
    status: ToolStatus
    version: Optional[str] = None
    latency_ms: Optional[float] = None
    auth_type: Optional[str] = None
    base_url: str
    error: Optional[str] = None
    access_groups: List[AccessGroup] = []


class ConnectivityReport(BaseModel):
    timestamp: str
    total: int
    healthy: int
    unhealthy: int
    unknown: int
    tools: List[ConnectivityResult]


class ToolAccessDetail(BaseModel):
    tool: str
    groups: List[str] = []


class AccessRequest(BaseModel):
    tools: List[ToolAccessDetail]
    reason: str
    requester_name: str
    requester_email: str


class AccessRequestResponse(BaseModel):
    success: bool
    jira_issue_key: Optional[str] = None
    jira_issue_url: Optional[str] = None
    message: str
