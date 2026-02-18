"""
File: tools.py
Purpose: Provides REST endpoints for listing all configured DevOps tools with their health status,
    adding/updating/removing tool configurations at runtime, and testing connectivity to
    individual tools on demand.
When Used: Invoked by the frontend Tools Management panel to display the tool inventory, let
    admins add new tool connections or modify existing ones, and run connectivity tests via the
    /tools/* routes.
Why Created: Separates tool configuration CRUD and health-check logic from the connectivity
    router (which is read-only and focused on the dashboard view), providing admin-level tool
    management capabilities that modify the tools_manager configuration.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from app.config import settings, tools_manager, ToolConfig
from app.models.schemas import (
    ToolInfo, ToolStatus, ToolConfigCreate, ToolConfigUpdate, APIResponse
)
from app.integrations.gitlab import GitLabIntegration
from app.integrations.sonarqube import SonarQubeIntegration
from app.integrations.trivy import TrivyIntegration
from app.integrations.nexus import NexusIntegration
from app.integrations.ollama import OllamaIntegration
from app.integrations.chromadb import ChromaDBIntegration
from app.integrations.github import GitHubIntegration
from app.integrations.jira import JiraIntegration
from app.integrations.splunk import SplunkIntegration
from app.integrations.jenkins import JenkinsIntegration

router = APIRouter(prefix="/tools", tags=["Tools Management"])


def get_integration(tool_name: str):
    """Get integration instance for a tool"""
    config = tools_manager.get_tool(tool_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    integrations = {
        "gitlab": GitLabIntegration,
        "sonarqube": SonarQubeIntegration,
        "trivy": TrivyIntegration,
        "nexus": NexusIntegration,
        "ollama": OllamaIntegration,
        "chromadb": ChromaDBIntegration,
        "github": GitHubIntegration,
        "jira": JiraIntegration,
        "splunk": SplunkIntegration,
        "jenkins": JenkinsIntegration,
    }

    integration_class = integrations.get(tool_name)
    if not integration_class:
        raise HTTPException(status_code=400, detail=f"No integration available for '{tool_name}'")

    return integration_class(config)


@router.get("/", response_model=List[ToolInfo])
async def list_tools():
    """List all configured tools with their status"""
    tools = []
    for name, config in tools_manager.list_tools().items():
        status = ToolStatus.UNKNOWN
        version = None

        if config.enabled:
            try:
                integration = get_integration(name)
                status = await integration.health_check()
                version = await integration.get_version()
                await integration.close()
            except Exception:
                status = ToolStatus.UNHEALTHY

        tools.append(ToolInfo(
            name=name,
            enabled=config.enabled,
            status=status,
            base_url=config.base_url,
            version=version
        ))

    return tools


@router.get("/{tool_name}", response_model=ToolInfo)
async def get_tool(tool_name: str):
    """Get status and info for a specific tool"""
    config = tools_manager.get_tool(tool_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    status = ToolStatus.UNKNOWN
    version = None

    if config.enabled:
        try:
            integration = get_integration(tool_name)
            status = await integration.health_check()
            version = await integration.get_version()
            await integration.close()
        except Exception as e:
            status = ToolStatus.UNHEALTHY

    return ToolInfo(
        name=tool_name,
        enabled=config.enabled,
        status=status,
        base_url=config.base_url,
        version=version
    )


@router.post("/", response_model=APIResponse)
async def add_tool(tool_config: ToolConfigCreate):
    """Add a new tool configuration"""
    config = ToolConfig(
        base_url=tool_config.base_url,
        enabled=tool_config.enabled,
        api_key=tool_config.api_key,
        username=tool_config.username,
        password=tool_config.password,
        token=tool_config.token,
        extra=tool_config.extra
    )
    tools_manager.add_tool(tool_config.name, config)
    tools_manager.save_config()

    return APIResponse(
        success=True,
        message=f"Tool '{tool_config.name}' added successfully"
    )


@router.put("/{tool_name}", response_model=APIResponse)
async def update_tool(tool_name: str, tool_config: ToolConfigUpdate):
    """Update an existing tool configuration"""
    existing = tools_manager.get_tool(tool_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    # Update only provided fields
    update_data = tool_config.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(existing, key, value)

    tools_manager.add_tool(tool_name, existing)
    tools_manager.save_config()

    return APIResponse(
        success=True,
        message=f"Tool '{tool_name}' updated successfully"
    )


@router.delete("/{tool_name}", response_model=APIResponse)
async def remove_tool(tool_name: str):
    """Remove a tool configuration"""
    if not tools_manager.remove_tool(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    tools_manager.save_config()
    return APIResponse(
        success=True,
        message=f"Tool '{tool_name}' removed successfully"
    )


@router.post("/{tool_name}/test", response_model=APIResponse)
async def test_tool_connection(tool_name: str):
    """Test connection to a specific tool"""
    try:
        integration = get_integration(tool_name)
        status = await integration.health_check()
        version = await integration.get_version()
        await integration.close()

        if status == ToolStatus.HEALTHY:
            return APIResponse(
                success=True,
                message=f"Connection to '{tool_name}' successful",
                data={"status": status, "version": version}
            )
        else:
            return APIResponse(
                success=False,
                message=f"Connection to '{tool_name}' failed",
                data={"status": status}
            )
    except Exception as e:
        return APIResponse(
            success=False,
            message=f"Connection to '{tool_name}' failed: {str(e)}"
        )
