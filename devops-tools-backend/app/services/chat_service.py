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
        },
        {
            "type": "function",
            "function": {
                "name": "validate_pipeline",
                "description": "Validate the pending generated pipeline using dry-run checks (YAML syntax, Dockerfile syntax, GitLab CI lint, Nexus image availability, pipeline structure). Use this when the user wants to verify, validate, or dry-run the pipeline before committing.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]

    SYSTEM_PROMPT = """You are an AI DevOps assistant that helps generate CI/CD pipelines for GitLab repositories.

Your capabilities:
1. Generate pipelines: When a user provides a GitLab repository URL, use the generate_pipeline tool. This automatically validates the pipeline and fixes any issues before returning results.
2. Validate pipelines: Use the validate_pipeline tool to run dry-run checks on the pending pipeline. Always offer this option before committing.
3. Commit pipelines: When the user approves (says "yes", "commit", "approve", etc.), use the commit_pipeline tool to commit the files to the repository.
4. Check status: When asked about pipeline status, use the check_pipeline_status tool.

Workflow - ALWAYS follow this order:
1. GENERATE: Generate and auto-validate the pipeline
2. REPORT: Tell the user the validation results (passed/failed/warnings)
3. VALIDATE (optional): If user asks, run additional dry-run validation via validate_pipeline
4. COMMIT: Only after the user confirms and validation is satisfactory

Guidelines:
- After generating a pipeline, ALWAYS report the validation status to the user:
  - If validation_passed is true: Tell the user validation passed and ask if they want to commit.
  - If validation_passed is false: Explain the validation errors and suggest regenerating or ask the user how to proceed.
  - If validation_skipped is true: Tell the user this is a proven template from RAG that was already validated.
  - Report any warnings even if validation passed.
  - If fix_attempts > 0: Mention that the pipeline had issues that were automatically fixed.
- NEVER commit a pipeline without first informing the user about its validation status.
- If the user asks to "validate", "dry-run", or "check" the pipeline, use the validate_pipeline tool.
- Always ask for confirmation before committing files.
- Explain what you're doing at each step.
- If there's an error, explain it clearly and suggest solutions.
- Be concise but informative.

IMPORTANT - Template Source Reporting:
After generating a pipeline, ALWAYS tell the user about the template source using the "source_message" from the tool result:
- If template_source is "rag": Tell the user "Template exists in RAG - using a proven pipeline that has succeeded before."
- If template_source is "llm": Tell the user "No template in RAG for this language. LLM is creating and testing a new template."
- If template_source is "builtin": Tell the user "Using a built-in default template for this language."
After committing, mention the template_source in your response so the user knows the commit message reflects the source."""

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
        model: str = "qwen3:32b"
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

        # Prepend template source banner directly (don't rely on LLM to report it)
        pending = self.pending_pipelines.get(conversation_id)
        if pending and "template_source" in pending:
            src = pending["template_source"]
            if src == "rag":
                banner = "**Template exists in RAG** - using a proven pipeline that has succeeded before.\n\n"
            elif src == "llm":
                banner = "**No template in RAG for this language.** LLM is creating and testing a new pipeline configuration.\n\n"
            elif src == "builtin":
                banner = "**Using a built-in default template** for this language.\n\n"
            else:
                banner = ""
            # Only prepend if LLM didn't already include correct info
            if banner and src == "llm" and "RAG" in assistant_message and "No template" not in assistant_message:
                # LLM hallucinated "RAG" when source is actually LLM — replace
                assistant_message = banner + assistant_message.replace(
                    "Template exists in RAG - using a proven pipeline that has succeeded before.",
                    ""
                ).replace(
                    "Template exists in RAG",
                    ""
                ).strip()
            elif banner and src == "rag" and "LLM" in assistant_message and "RAG" not in assistant_message:
                # LLM said LLM when source is actually RAG — replace
                assistant_message = banner + assistant_message
            elif banner:
                # Prepend banner for clarity
                assistant_message = banner + assistant_message

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
        elif tool_name == "validate_pipeline":
            return await self._tool_validate_pipeline(conversation_id)
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
                    f"{self.backend_url}/api/v1/pipeline/generate-validated",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.gitlab_token,
                        "model": "qwen3:32b",
                        "max_fix_attempts": 3,
                        "store_on_success": True
                    }
                )
                result = response.json()

                if result.get("success"):
                    # Determine template source for user messaging
                    model_used = result.get("model_used", "unknown")
                    if model_used in ("chromadb-direct", "template-only"):
                        template_source = "rag"
                        source_message = "Template found in RAG (ChromaDB) - using a proven pipeline configuration that has succeeded before."
                    elif model_used == "built-in-template":
                        template_source = "builtin"
                        source_message = "Using built-in default template for this language."
                    else:
                        template_source = "llm"
                        source_message = "No existing template found in RAG. LLM is creating a new pipeline configuration. It will be tested automatically and stored if successful."

                    # Extract validation results
                    validation_passed = result.get("validation_passed", False)
                    validation_skipped = result.get("validation_skipped", False)
                    validation_errors = result.get("validation_errors", [])
                    warnings = result.get("warnings", [])
                    fix_attempts = result.get("fix_attempts", 0)

                    # Store the generated pipeline for later commit
                    self.pending_pipelines[conversation_id] = {
                        "repo_url": repo_url,
                        "dockerfile": result.get("dockerfile", ""),
                        "gitlab_ci": result.get("gitlab_ci", ""),
                        "analysis": result.get("analysis", {}),
                        "template_source": template_source,
                        "model_used": model_used,
                        "validation_passed": validation_passed,
                        "validation_skipped": validation_skipped,
                        "validation_errors": validation_errors,
                        "fix_attempts": fix_attempts
                    }

                    return {
                        "success": True,
                        "message": "Pipeline generated and validated successfully" if validation_passed or validation_skipped else "Pipeline generated but has validation issues",
                        "template_source": template_source,
                        "source_message": source_message,
                        "validation_passed": validation_passed,
                        "validation_skipped": validation_skipped,
                        "validation_errors": validation_errors,
                        "warnings": warnings,
                        "fix_attempts": fix_attempts,
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

            # Build commit message based on template source
            template_source = pending.get("template_source", "unknown")
            model_used = pending.get("model_used", "unknown")
            language = pending.get("analysis", {}).get("language", "unknown")
            framework = pending.get("analysis", {}).get("framework", "generic")

            if template_source == "rag":
                commit_message = f"Add CI/CD pipeline [RAG Template] - Proven {language}/{framework} config from ChromaDB"
            elif template_source == "builtin":
                commit_message = f"Add CI/CD pipeline [Built-in Template] - Default {language} configuration"
            else:
                commit_message = f"Add CI/CD pipeline [LLM Generated] - New {language}/{framework} config by {model_used}, will be auto-tested"

            # Use the stored pipeline data
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/commit",
                    json={
                        "repo_url": pending["repo_url"],
                        "gitlab_token": self.gitlab_token,
                        "dockerfile": pending["dockerfile"],
                        "gitlab_ci": pending["gitlab_ci"],
                        "commit_message": commit_message
                    }
                )
                result = response.json()

                if result.get("success"):
                    # Clear pending pipeline
                    del self.pending_pipelines[conversation_id]
                    return {
                        "success": True,
                        "message": f"Pipeline committed successfully. Source: {commit_message}",
                        "template_source": template_source,
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

    async def _tool_validate_pipeline(self, conversation_id: str) -> Dict:
        """Validate the pending pipeline via dry-run checks"""
        pending = self.pending_pipelines.get(conversation_id)
        if not pending:
            return {
                "success": False,
                "error": "No pipeline generated yet. Please generate a pipeline first."
            }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/dry-run",
                    json={
                        "gitlab_ci": pending["gitlab_ci"],
                        "dockerfile": pending["dockerfile"],
                        "gitlab_token": self.gitlab_token
                    }
                )
                result = response.json()

                # Update pending pipeline with validation status
                pending["validation_passed"] = result.get("valid", False)
                pending["validation_errors"] = result.get("errors", [])

                return {
                    "success": True,
                    "valid": result.get("valid", False),
                    "errors": result.get("errors", []),
                    "warnings": result.get("warnings", []),
                    "summary": result.get("summary", "")
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
