"""
Chat Service - Orchestrates LLM conversations with tool calling
"""
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx

from app.config import Settings


class ChatService:
    """Service for managing chat conversations with LLM and tool calling"""

    # Tool definitions for LLM
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "generate_pipeline",
                "description": "Generate CI/CD pipeline (Dockerfile and .gitlab-ci.yml) for a GitLab repository. Use this when the user provides a GitLab repository URL and wants to create a pipeline.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_url": {
                            "type": "string",
                            "description": "The GitLab repository URL (e.g., http://gitlab-server/root/my-project)"
                        }
                    },
                    "required": ["repo_url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "commit_pipeline",
                "description": "Commit the generated pipeline files (Dockerfile and .gitlab-ci.yml) to the GitLab repository. Use this when the user approves/confirms they want to commit the pipeline.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_url": {
                            "type": "string",
                            "description": "The GitLab repository URL to commit to"
                        }
                    },
                    "required": ["repo_url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_pipeline_status",
                "description": "Check the status of a GitLab CI/CD pipeline. Use this when the user wants to know if the pipeline succeeded or failed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_url": {
                            "type": "string",
                            "description": "The GitLab repository URL"
                        },
                        "branch": {
                            "type": "string",
                            "description": "The branch name to check (default: main)"
                        }
                    },
                    "required": ["repo_url"]
                }
            }
        }
    ]

    SYSTEM_PROMPT = """You are an AI DevOps assistant that helps generate CI/CD pipelines for GitLab repositories.

Your capabilities:
1. Generate pipelines: When a user provides a GitLab repository URL, use the generate_pipeline tool to analyze the repository and create appropriate Dockerfile and .gitlab-ci.yml files.
2. Commit pipelines: When the user approves (says "yes", "commit", "approve", etc.), use the commit_pipeline tool to commit the files to the repository.
3. Check status: When asked about pipeline status, use the check_pipeline_status tool.

Guidelines:
- Always ask for confirmation before committing files
- Explain what you're doing at each step
- If there's an error, explain it clearly and suggest solutions
- Be concise but informative"""

    def __init__(self, config: Settings):
        self.config = config
        self.ollama_url = config.ollama_url
        self.gitlab_token = config.gitlab_token
        self.backend_url = "http://devops-tools-backend:8003"  # Self-reference for tool calls (container name for Docker network)

        # In-memory conversation storage (use DB in production)
        self.conversations: Dict[str, List[Dict]] = {}
        self.pending_pipelines: Dict[str, Dict] = {}  # Store generated but not committed pipelines

    async def create_conversation(self) -> str:
        """Create a new conversation and return its ID"""
        conversation_id = str(uuid.uuid4())
        self.conversations[conversation_id] = []
        return conversation_id

    async def get_conversation(self, conversation_id: str) -> List[Dict]:
        """Get conversation history"""
        return self.conversations.get(conversation_id, [])

    async def chat(
        self,
        conversation_id: str,
        user_message: str,
        model: str = "llama3.1:8b"
    ) -> Dict[str, Any]:
        """
        Process a chat message and return the response.
        Handles tool calling automatically.
        """
        # Initialize conversation if needed
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []

        # Add user message to history
        self.conversations[conversation_id].append({
            "role": "user",
            "content": user_message
        })

        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            *self.conversations[conversation_id]
        ]

        # Call LLM with tools
        response = await self._call_llm(messages, model)

        # Check if LLM wants to use a tool
        if response.get("message", {}).get("tool_calls"):
            tool_calls = response["message"]["tool_calls"]

            # Process each tool call
            tool_results = []
            for tool_call in tool_calls:
                result = await self._execute_tool(
                    conversation_id,
                    tool_call["function"]["name"],
                    tool_call["function"]["arguments"]
                )
                tool_results.append({
                    "tool": tool_call["function"]["name"],
                    "result": result
                })

            # Add assistant's tool call message
            self.conversations[conversation_id].append({
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls
            })

            # Add tool results
            for i, tool_call in enumerate(tool_calls):
                self.conversations[conversation_id].append({
                    "role": "tool",
                    "content": json.dumps(tool_results[i]["result"]),
                    "tool_call_id": tool_call.get("id", f"call_{i}")
                })

            # Get final response from LLM after tool execution
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                *self.conversations[conversation_id]
            ]
            response = await self._call_llm(messages, model, tools=None)

        # Extract assistant message
        assistant_message = response.get("message", {}).get("content", "")

        # Add to conversation history
        self.conversations[conversation_id].append({
            "role": "assistant",
            "content": assistant_message
        })

        return {
            "conversation_id": conversation_id,
            "message": assistant_message,
            "pending_pipeline": self.pending_pipelines.get(conversation_id)
        }

    async def _call_llm(
        self,
        messages: List[Dict],
        model: str,
        tools: Optional[List] = None
    ) -> Dict:
        """Call Ollama LLM API"""
        if tools is None:
            tools = self.TOOLS

        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }

        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            return response.json()

    async def _execute_tool(
        self,
        conversation_id: str,
        tool_name: str,
        arguments: Dict
    ) -> Dict:
        """Execute a tool and return the result"""

        if tool_name == "generate_pipeline":
            return await self._tool_generate_pipeline(
                conversation_id,
                arguments.get("repo_url", "")
            )
        elif tool_name == "commit_pipeline":
            return await self._tool_commit_pipeline(
                conversation_id,
                arguments.get("repo_url", "")
            )
        elif tool_name == "check_pipeline_status":
            return await self._tool_check_status(
                arguments.get("repo_url", ""),
                arguments.get("branch", "main")
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _tool_generate_pipeline(
        self,
        conversation_id: str,
        repo_url: str
    ) -> Dict:
        """Generate pipeline using the pipeline service"""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.gitlab_token,
                        "model": "llama3.1:8b"
                    }
                )
                result = response.json()

                if result.get("success"):
                    # Store the generated pipeline for later commit
                    self.pending_pipelines[conversation_id] = {
                        "repo_url": repo_url,
                        "dockerfile": result.get("dockerfile", ""),
                        "gitlab_ci": result.get("gitlab_ci", ""),
                        "analysis": result.get("analysis", {})
                    }

                    return {
                        "success": True,
                        "message": "Pipeline generated successfully",
                        "analysis": result.get("analysis", {}),
                        "dockerfile": result.get("dockerfile", ""),
                        "gitlab_ci": result.get("gitlab_ci", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("detail", "Failed to generate pipeline")
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _tool_commit_pipeline(
        self,
        conversation_id: str,
        repo_url: str
    ) -> Dict:
        """Commit the generated pipeline to GitLab"""
        try:
            # Get pending pipeline
            pending = self.pending_pipelines.get(conversation_id)
            if not pending:
                return {
                    "success": False,
                    "error": "No pipeline generated yet. Please generate a pipeline first."
                }

            # Use the stored pipeline data
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/commit",
                    json={
                        "repo_url": pending["repo_url"],
                        "gitlab_token": self.gitlab_token,
                        "dockerfile": pending["dockerfile"],
                        "gitlab_ci": pending["gitlab_ci"],
                        "commit_message": "Add CI/CD pipeline [AI Generated]"
                    }
                )
                result = response.json()

                if result.get("success"):
                    # Clear pending pipeline
                    del self.pending_pipelines[conversation_id]
                    return {
                        "success": True,
                        "message": "Pipeline committed successfully",
                        "branch": result.get("branch", ""),
                        "commit_id": result.get("commit_id", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("detail", "Failed to commit pipeline")
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _tool_check_status(
        self,
        repo_url: str,
        branch: str
    ) -> Dict:
        """Check pipeline status"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/status",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.gitlab_token,
                        "branch": branch
                    }
                )
                return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
