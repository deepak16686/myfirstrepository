"""
Unified tool caller for AI integration
Provides a single endpoint for AI models to call any tool
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import time

from app.config import tools_manager
from app.models.schemas import ToolCallRequest, ToolCallResponse
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

router = APIRouter(prefix="/call", tags=["Unified Tool Caller"])


INTEGRATION_MAP = {
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


def get_integration(tool_name: str):
    """Get integration instance for a tool"""
    config = tools_manager.get_tool(tool_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not configured")
    if not config.enabled:
        raise HTTPException(status_code=503, detail=f"Tool '{tool_name}' is disabled")

    integration_class = INTEGRATION_MAP.get(tool_name)
    if not integration_class:
        raise HTTPException(status_code=400, detail=f"No integration available for '{tool_name}'")

    return integration_class(config)


@router.post("/", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest):
    """
    Unified tool call endpoint for AI integration.

    This endpoint allows AI models to call any configured tool using a unified schema.

    Example request:
    ```json
    {
        "tool": "gitlab",
        "action": "list_projects",
        "params": {"search": "test", "per_page": 10}
    }
    ```

    Example response:
    ```json
    {
        "tool": "gitlab",
        "action": "list_projects",
        "success": true,
        "result": [...],
        "error": null,
        "execution_time": 0.5
    }
    ```
    """
    start_time = time.time()

    try:
        integration = get_integration(request.tool)
    except HTTPException as e:
        return ToolCallResponse(
            tool=request.tool,
            action=request.action,
            success=False,
            result=None,
            error=e.detail,
            execution_time=time.time() - start_time
        )

    try:
        # Get the method from the integration
        method = getattr(integration, request.action, None)
        if method is None:
            return ToolCallResponse(
                tool=request.tool,
                action=request.action,
                success=False,
                result=None,
                error=f"Action '{request.action}' not found on {request.tool}",
                execution_time=time.time() - start_time
            )

        # Call the method with params
        result = await method(**request.params)

        # Convert Pydantic models to dict for JSON serialization
        if hasattr(result, 'model_dump'):
            result = result.model_dump()
        elif isinstance(result, list):
            result = [r.model_dump() if hasattr(r, 'model_dump') else r for r in result]

        return ToolCallResponse(
            tool=request.tool,
            action=request.action,
            success=True,
            result=result,
            error=None,
            execution_time=time.time() - start_time
        )
    except Exception as e:
        return ToolCallResponse(
            tool=request.tool,
            action=request.action,
            success=False,
            result=None,
            error=str(e),
            execution_time=time.time() - start_time
        )
    finally:
        await integration.close()


@router.get("/actions/{tool_name}")
async def list_tool_actions(tool_name: str):
    """
    List available actions for a tool.

    This helps AI models discover what actions are available.
    """
    try:
        integration = get_integration(tool_name)
    except HTTPException as e:
        raise e

    # Get all public methods (actions)
    actions = []
    for name in dir(integration):
        if not name.startswith('_'):
            method = getattr(integration, name)
            if callable(method) and hasattr(method, '__code__'):
                # Get method signature
                import inspect
                sig = inspect.signature(method)
                params = [
                    {
                        "name": p.name,
                        "required": p.default == inspect.Parameter.empty,
                        "default": None if p.default == inspect.Parameter.empty else p.default
                    }
                    for p in sig.parameters.values()
                    if p.name != 'self'
                ]
                actions.append({
                    "name": name,
                    "params": params,
                    "doc": method.__doc__
                })

    await integration.close()
    return {"tool": tool_name, "actions": actions}


@router.get("/schema")
async def get_tool_schema():
    """
    Get the complete schema of all tools and their actions.

    This is useful for AI models to understand the available capabilities.
    """
    schema = {}

    for tool_name in INTEGRATION_MAP.keys():
        config = tools_manager.get_tool(tool_name)
        if not config:
            continue

        try:
            integration = INTEGRATION_MAP[tool_name](config)
            actions = []

            import inspect
            for name in dir(integration):
                if not name.startswith('_'):
                    method = getattr(integration, name)
                    if callable(method) and hasattr(method, '__code__'):
                        sig = inspect.signature(method)
                        params = [
                            {
                                "name": p.name,
                                "required": p.default == inspect.Parameter.empty,
                                "type": str(p.annotation) if p.annotation != inspect.Parameter.empty else "any"
                            }
                            for p in sig.parameters.values()
                            if p.name != 'self'
                        ]
                        actions.append({
                            "name": name,
                            "params": params,
                            "description": (method.__doc__ or "").strip().split('\n')[0] if method.__doc__ else ""
                        })

            schema[tool_name] = {
                "enabled": config.enabled,
                "base_url": config.base_url,
                "actions": actions
            }
            await integration.close()
        except Exception:
            schema[tool_name] = {"enabled": False, "error": "Failed to load integration"}

    return schema
