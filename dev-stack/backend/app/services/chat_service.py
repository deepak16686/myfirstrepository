"""
File: chat_service.py
Purpose: Orchestrates LLM-powered chat conversations using Ollama with tool calling, enabling users to generate, commit, validate, and monitor GitLab CI pipelines through natural language commands.
When Used: Called by the chat router when users send messages in the GitLab pipeline chat interface, which can trigger tool calls for pipeline generation, commit, status checking, validation, and tool connectivity testing.
Why Created: Provides the conversational AI interface for GitLab pipeline management, using Ollama's native tool-calling capability (not available via Claude CLI) to map user intents to backend API operations.
"""
import json
import re
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
                "description": "Generate CI/CD pipeline files for a GitLab repository only after the pipeline requirements have been clarified and the user has confirmed the resolved values.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_url": {
                            "type": "string",
                            "description": "The GitLab repository URL (e.g., https://gitlab.deepaksharma.live/gitlab/root/my-project)"
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
        },
        {
            "type": "function",
            "function": {
                "name": "check_tool_connectivity",
                "description": "Check connectivity and health status of DevOps tools (GitLab, SonarQube, Trivy, Nexus, Ollama, ChromaDB, Jira, Splunk, Jenkins, Redis, PostgreSQL). Use this when the user asks about tool status, health, connectivity, or access.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Optional specific tool name to check. If empty, checks all tools."
                        }
                    },
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
1. DISCOVER: Analyze the repository and identify what can be proven from code.
2. CLARIFY: Ask questions for anything missing or ambiguous, especially Docker image vs direct artifact output.
3. CONFIRM: Show the resolved values and ask the user to proceed.
4. GENERATE: Generate and auto-validate the pipeline only after confirmation.
5. VALIDATE (optional): If user asks, run additional dry-run validation via validate_pipeline.
6. COMMIT: Only after the user confirms and validation is satisfactory.

Guidelines:
- After generating a pipeline, ALWAYS report the validation status to the user:
  - If validation_passed is true: Tell the user validation passed and ask if they want to commit.
  - If validation_passed is false: Explain the validation errors and suggest regenerating or ask the user how to proceed.
  - Report any warnings even if validation passed.
  - If fix_attempts > 0: Mention that the pipeline had issues that were automatically fixed.
- NEVER commit a pipeline without first informing the user about its validation status.
- If the user asks to "validate", "dry-run", or "check" the pipeline, use the validate_pipeline tool.
- Always ask for confirmation before committing files.
- Explain what you're doing at each step.
- If there's an error, explain it clearly and suggest solutions.
- Be concise but informative.
- When the user asks about tool status, health, connectivity, or access, use the check_tool_connectivity tool.

IMPORTANT - Template Source Reporting:
After generating a pipeline, ALWAYS tell the user about the template source using the "source_message" from the tool result:
- If template_source is "rag": Tell the user "Template found in RAG for this language/build-tool. It was validated before committing."
- If template_source is "llm": Tell the user "No matching template in RAG. LLM created a new pipeline, validated before committing."
- If template_source is "builtin": Tell the user "Using a built-in default template for this language."
NEVER say "validation skipped" — all pipelines are always validated before committing.
After committing, mention the template_source in your response so the user knows the commit message reflects the source."""

    def __init__(self, config: Settings):
        self.config = config
        self.ollama_url = config.ollama_url
        self.gitlab_token = config.gitlab_token
        self.backend_url = "http://devops-tools-backend:8003"  # Self-reference for tool calls (container name for Docker network)

        # In-memory conversation storage (use DB in production)
        self.conversations: Dict[str, List[Dict]] = {}
        self.pending_pipelines: Dict[str, Dict] = {}  # Store generated but not committed pipelines
        self.pipeline_requirement_sessions: Dict[str, Dict[str, Any]] = {}

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

        deterministic_response = await self._handle_pipeline_requirements_message(
            conversation_id,
            user_message
        )
        if deterministic_response:
            self.conversations[conversation_id].append({
                "role": "assistant",
                "content": deterministic_response
            })
            return {
                "conversation_id": conversation_id,
                "message": deterministic_response,
                "pending_pipeline": self.pending_pipelines.get(conversation_id),
                "monitoring": None
            }

        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            *self.conversations[conversation_id]
        ]

        # Call LLM with tools
        response = await self._call_llm(messages, model)

        # Track tool results for monitoring info extraction
        tool_results = []

        # Check if LLM wants to use a tool
        if response.get("message", {}).get("tool_calls"):
            tool_calls = response["message"]["tool_calls"]

            # Process each tool call
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
                banner = "**Template found in RAG** - using a matching template from a previous successful pipeline.\n\n"
            elif src == "llm":
                banner = "**No matching template in RAG.** LLM created a new pipeline configuration.\n\n"
            elif src == "builtin":
                banner = "**Using a built-in default template** for this language.\n\n"
            elif src == "direct_artifact":
                banner = "**Direct artifact pipeline** - no Dockerfile will be committed.\n\n"
            else:
                banner = ""
            # Only prepend if LLM didn't already include correct info
            if banner and src == "llm" and "RAG" in assistant_message and "No matching" not in assistant_message:
                # LLM hallucinated "RAG" when source is actually LLM — replace
                assistant_message = banner + assistant_message.replace(
                    "Template found in RAG",
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

        # Check if a commit was just performed — extract monitoring info for frontend polling
        monitoring_info = None
        for tr in tool_results:
            if tr["tool"] == "commit_pipeline" and tr["result"].get("success"):
                monitoring_info = {
                    "project_id": tr["result"].get("project_id"),
                    "branch": tr["result"].get("branch")
                }
                break

        return {
            "conversation_id": conversation_id,
            "message": assistant_message,
            "pending_pipeline": self.pending_pipelines.get(conversation_id),
            "monitoring": monitoring_info
        }

    async def _handle_pipeline_requirements_message(
        self,
        conversation_id: str,
        user_message: str
    ) -> Optional[str]:
        """Deterministic requirements-first flow for GitLab pipeline generation."""
        session = self.pipeline_requirement_sessions.get(conversation_id)

        if session:
            if session.get("state") == "awaiting_confirmation":
                if self._is_affirmative(user_message):
                    requirements = session["values"]
                    result = await self._tool_generate_pipeline(
                        conversation_id,
                        session["repo_url"],
                        requirements=requirements,
                        skip_requirements_gate=True
                    )
                    self.pipeline_requirement_sessions.pop(conversation_id, None)
                    return self._format_generation_result(result)

                self._apply_user_requirement_answers(session, user_message)
                questions = self._missing_requirement_questions(session)
                if questions:
                    session["state"] = "awaiting_answers"
                    return self._format_requirement_questions(session, questions)
                session["state"] = "awaiting_confirmation"
                return self._format_requirement_confirmation(session)

            self._apply_user_requirement_answers(session, user_message)
            questions = self._missing_requirement_questions(session)
            if questions:
                session["state"] = "awaiting_answers"
                return self._format_requirement_questions(session, questions)
            session["state"] = "awaiting_confirmation"
            return self._format_requirement_confirmation(session)

        repo_url = self._extract_repo_url(user_message)
        if repo_url and self._has_pipeline_generation_intent(user_message):
            return await self._begin_pipeline_requirements_session(conversation_id, repo_url, user_message)

        return None

    async def _begin_pipeline_requirements_session(self, conversation_id: str, repo_url: str, user_message: str) -> str:
        if not self.gitlab_token:
            return "GitLab token is missing. Please configure a GitLab token with api scope before generating a pipeline."

        try:
            from app.services.pipeline import pipeline_generator
            analysis = await pipeline_generator.analyze_repository(repo_url, self.gitlab_token)
        except Exception as exc:
            return f"I could not analyze the repository yet: {exc}"

        values, sources = self._build_initial_requirement_values(analysis)
        session = {
            "repo_url": repo_url,
            "analysis": analysis,
            "values": values,
            "sources": sources,
            "state": "awaiting_answers",
        }
        self.pipeline_requirement_sessions[conversation_id] = session
        self._apply_user_requirement_answers(session, user_message)

        questions = self._missing_requirement_questions(session)
        if questions:
            return self._format_requirement_questions(session, questions, include_detected=True)

        session["state"] = "awaiting_confirmation"
        return self._format_requirement_confirmation(session)

    def _build_initial_requirement_values(self, analysis: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, str]]:
        values: Dict[str, Any] = {}
        sources: Dict[str, str] = {}

        def set_value(key: str, value: Any, source: str) -> None:
            if value not in (None, "", [], {}):
                values[key] = value
                sources[key] = source

        language = analysis.get("language", "unknown")
        set_value("language", language, "detected")

        version = (
            analysis.get("java_version")
            or analysis.get("node_version")
            or analysis.get("python_version")
            or analysis.get("go_version")
            or analysis.get("ruby_version")
            or analysis.get("language_version")
        )
        set_value("language_version", version, "detected")
        if language == "java" and version:
            set_value("java_version", version, "detected")

        build_tool = analysis.get("build_tool") or analysis.get("package_manager")
        if build_tool and build_tool != "unknown":
            set_value("build_tool", build_tool, "detected")

        framework = analysis.get("framework")
        if framework == "gradle":
            framework = "generic"
        if framework:
            set_value("framework", framework, "detected" if framework != "generic" else "inferred")
        set_value("framework_version", analysis.get("framework_version"), "detected")
        set_value("packaging", analysis.get("packaging"), "detected")

        module_type = self._infer_module_type(analysis)
        set_value("module_type", module_type, "inferred")
        set_value("module_path", ".", "inferred")

        if analysis.get("has_dockerfile"):
            set_value("output_mode", "docker-image", "detected")
            set_value("dockerfile_strategy", "reuse-existing", "detected")

        set_value("registry_strategy", "nexus", "default")
        set_value("runner_type", "docker", "default")
        return values, sources

    def _infer_module_type(self, analysis: Dict[str, Any]) -> str:
        root_files = set(analysis.get("files") or [])
        all_paths = analysis.get("all_paths") or []
        root_build = {"pom.xml", "build.gradle", "build.gradle.kts", "package.json", "pyproject.toml", "go.mod"}
        nested_builds = [
            path for path in all_paths
            if "/" in path and path.split("/")[-1] in root_build
        ]
        if "settings.gradle" in root_files or "settings.gradle.kts" in root_files or len(nested_builds) > 1:
            return "multi-module"
        return "single-module"

    def _missing_requirement_questions(self, session: Dict[str, Any]) -> List[Dict[str, str]]:
        values = session["values"]
        language = str(values.get("language", "unknown")).lower()
        questions: List[Dict[str, str]] = []

        if not values.get("output_mode"):
            questions.append({
                "field": "output_mode",
                "question": "Should the pipeline create and push a Docker image, or only build a direct artifact?"
            })

        if language == "unknown":
            questions.append({
                "field": "language",
                "question": "What is the main application language?"
            })

        if language == "java" and not values.get("language_version"):
            questions.append({
                "field": "language_version",
                "question": "Which Java version should the pipeline use? Example: 8, 11, 17, 21."
            })

        if language == "java" and not values.get("build_tool"):
            questions.append({
                "field": "build_tool",
                "question": "Which Java build tool should be used: Gradle or Maven?"
            })

        framework_source = session["sources"].get("framework")
        if language == "java" and (
            values.get("framework") in (None, "")
            or (values.get("framework") == "generic" and framework_source != "user")
        ):
            questions.append({
                "field": "framework",
                "question": "Is this generic Java, Spring Boot, Quarkus, or Micronaut?"
            })

        if language == "java" and not values.get("packaging"):
            questions.append({
                "field": "packaging",
                "question": "What artifact packaging is expected: JAR, WAR, or native image?"
            })

        output_mode = str(values.get("output_mode", "")).replace("_", "-").lower()
        if output_mode in ("direct-artifact", "artifact", "artifact-only") and not values.get("artifact_publish_target"):
            questions.append({
                "field": "artifact_publish_target",
                "question": "For direct artifact mode, should the artifact stay as GitLab job artifacts or be prepared for Nexus publishing?"
            })

        return questions

    def _apply_user_requirement_answers(self, session: Dict[str, Any], message: str) -> None:
        values = session["values"]
        sources = session["sources"]
        text = message.lower()

        def set_user(key: str, value: Any) -> None:
            if value not in (None, ""):
                values[key] = value
                sources[key] = "user"

        if any(word in text for word in ("docker image", "container image", "docker", "image")):
            set_user("output_mode", "docker-image")
            set_user("dockerfile_strategy", "generate" if not session["analysis"].get("has_dockerfile") else "reuse-existing")
        if any(word in text for word in ("direct artifact", "artifact only", "artifact-only", "jar only", "war only")):
            set_user("output_mode", "direct-artifact")
            set_user("dockerfile_strategy", "none")

        java_match = re.search(r"\b(?:java\s*)?(8|11|17|21|25|26)\b", text)
        if java_match and str(values.get("language", "")).lower() == "java":
            set_user("language_version", java_match.group(1))
            set_user("java_version", java_match.group(1))

        if "gradle" in text:
            set_user("build_tool", "gradle")
        elif "maven" in text or "mvn" in text:
            set_user("build_tool", "maven")

        if "spring boot" in text or "spring-boot" in text:
            set_user("framework", "spring-boot")
        elif "quarkus" in text:
            set_user("framework", "quarkus")
        elif "micronaut" in text:
            set_user("framework", "micronaut")
        elif "generic" in text or "plain java" in text or "no framework" in text:
            set_user("framework", "generic")

        if re.search(r"\bwar\b", text):
            set_user("packaging", "war")
        elif re.search(r"\bjar\b", text):
            set_user("packaging", "jar")
        elif "native" in text:
            set_user("packaging", "native-image")

        if "nexus" in text:
            set_user("artifact_publish_target", "nexus")
        elif "gitlab artifact" in text or "gitlab artifacts" in text or "job artifact" in text or "job artifacts" in text:
            set_user("artifact_publish_target", "gitlab-artifacts")

        self._derive_requirement_defaults(session)

    def _derive_requirement_defaults(self, session: Dict[str, Any]) -> None:
        values = session["values"]
        sources = session["sources"]
        language = str(values.get("language", "")).lower()
        build_tool = str(values.get("build_tool", "")).lower()
        packaging = str(values.get("packaging", "")).lower()

        output_mode = str(values.get("output_mode", "")).replace("_", "-").lower()
        if output_mode == "docker-image" and not values.get("dockerfile_strategy"):
            values["dockerfile_strategy"] = "generate"
            sources["dockerfile_strategy"] = "inferred"

        if output_mode == "direct-artifact" and not values.get("dockerfile_strategy"):
            values["dockerfile_strategy"] = "none"
            sources["dockerfile_strategy"] = "inferred"

        if language == "java" and packaging and not values.get("artifact_pattern"):
            if build_tool == "maven":
                values["artifact_pattern"] = "target/*.war" if packaging == "war" else "target/*.jar"
            else:
                values["artifact_pattern"] = "build/libs/*.war" if packaging == "war" else "build/libs/*.jar"
            sources["artifact_pattern"] = "inferred"

    def _format_requirement_questions(
        self,
        session: Dict[str, Any],
        questions: List[Dict[str, str]],
        include_detected: bool = False
    ) -> str:
        parts = []
        if include_detected:
            parts.append("I analyzed the repository and filled what I could from the code.")
            parts.append(self._format_requirement_values(session, detected_only=True))
        parts.append("I need these details before creating the pipeline:")
        for index, item in enumerate(questions, 1):
            parts.append(f"{index}. {item['question']}")
        parts.append("You can answer all questions in one message.")
        return "\n\n".join(parts)

    def _format_requirement_confirmation(self, session: Dict[str, Any]) -> str:
        self._derive_requirement_defaults(session)
        return (
            "Here are the pipeline values I will use:\n\n"
            f"{self._format_requirement_values(session)}\n\n"
            "Reply `proceed` to create and validate the pipeline, or tell me what to change."
        )

    def _format_requirement_values(self, session: Dict[str, Any], detected_only: bool = False) -> str:
        values = session["values"]
        sources = session["sources"]
        display_order = [
            ("language", "Language"),
            ("language_version", "Language version"),
            ("build_tool", "Build tool"),
            ("framework", "Framework"),
            ("framework_version", "Framework version"),
            ("packaging", "Packaging"),
            ("module_type", "Module type"),
            ("module_path", "Module path"),
            ("output_mode", "Output mode"),
            ("dockerfile_strategy", "Dockerfile strategy"),
            ("artifact_pattern", "Artifact pattern"),
            ("artifact_publish_target", "Artifact publish target"),
            ("registry_strategy", "Registry"),
            ("runner_type", "Runner"),
        ]
        lines = []
        for key, label in display_order:
            if key not in values:
                continue
            source = sources.get(key, "unknown")
            if detected_only and source not in ("detected", "inferred"):
                continue
            lines.append(f"- {label}: `{values[key]}` ({source})")
        return "\n".join(lines) if lines else "- No values detected yet."

    def _format_generation_result(self, result: Dict[str, Any]) -> str:
        if not result.get("success"):
            return f"Pipeline generation failed: {result.get('error', 'Unknown error')}"

        source_message = result.get("source_message", "")
        validation_passed = result.get("validation_passed", False)
        warnings = result.get("warnings") or []
        errors = result.get("validation_errors") or []
        analysis = result.get("analysis") or {}

        parts = [source_message or "Pipeline generated."]
        parts.append(
            "Validation passed." if validation_passed else "Pipeline generated, but validation found issues."
        )
        parts.append(
            f"Resolved stack: {analysis.get('language', 'unknown')} / "
            f"{analysis.get('build_tool') or analysis.get('package_manager') or 'unknown'} / "
            f"{analysis.get('framework', 'generic')}."
        )
        if warnings:
            parts.append("Warnings:\n" + "\n".join(f"- {warning}" for warning in warnings[:5]))
        if errors:
            parts.append("Errors:\n" + "\n".join(f"- {error}" for error in errors[:5]))
        parts.append("If this looks good, reply `commit` to commit the generated pipeline to GitLab.")
        return "\n\n".join(parts)

    def _build_generation_context(self, requirements: Dict[str, Any]) -> str:
        if not requirements:
            return ""
        lines = ["Confirmed pipeline requirements from chatbot clarification:"]
        for key in sorted(requirements.keys()):
            value = requirements[key]
            if value not in (None, "", [], {}):
                lines.append(f"- {key}: {value}")
        output_mode = str(requirements.get("output_mode", "")).replace("_", "-").lower()
        if output_mode in ("direct-artifact", "artifact", "artifact-only"):
            lines.append("- Generate a direct artifact pipeline. Do not create or commit a Dockerfile.")
        elif output_mode == "docker-image":
            lines.append("- Generate a Docker image pipeline with .gitlab-ci.yml and Dockerfile.")
        return "\n".join(lines)

    def _extract_repo_url(self, message: str) -> Optional[str]:
        match = re.search(r"(https?://[^\s`]+|git@[\w.\-]+:[^\s`]+)", message)
        if not match:
            return None
        return match.group(1).rstrip(".,)")

    def _has_pipeline_generation_intent(self, message: str) -> bool:
        text = message.lower()
        if "pipeline" not in text and "ci" not in text:
            return False
        return any(word in text for word in ("generate", "create", "add", "build", "prepare", "make"))

    def _is_affirmative(self, message: str) -> bool:
        text = message.strip().lower()
        if text.startswith(("no", "not ", "don't", "do not")):
            return False
        if any(word in text for word in ("change", "instead", "modify")):
            return False
        affirmative_words = ("yes", "proceed", "continue", "go ahead", "looks good")
        return text in {"y", "ok", "okay"} or any(word in text for word in affirmative_words)

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
        elif tool_name == "check_tool_connectivity":
            return await self._tool_check_connectivity(
                arguments.get("tool_name", "")
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _tool_generate_pipeline(
        self,
        conversation_id: str,
        repo_url: str,
        requirements: Optional[Dict[str, Any]] = None,
        skip_requirements_gate: bool = False
    ) -> Dict:
        """Generate pipeline using the pipeline service"""
        if not self.gitlab_token:
            return {
                "error": "GitLab token is missing or invalid. Please provide a GitLab personal access token with api scope to proceed. Would you like to provide one now?"
            }
        if not skip_requirements_gate and not requirements:
            return {
                "success": False,
                "requires_clarification": True,
                "error": "Pipeline requirements must be clarified and confirmed before generation."
            }
        try:
            additional_context = self._build_generation_context(requirements or {})
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/generate-validated",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.gitlab_token,
                        "additional_context": additional_context,
                        "model": "qwen3:32b",
                        "max_fix_attempts": 3,
                        "store_on_success": True,
                        "pipeline_requirements": requirements or {}
                    }
                )
                result = response.json()

                if result.get("success"):
                    # Determine template source for user messaging
                    model_used = result.get("model_used", "unknown")
                    if model_used == "direct-artifact-template":
                        template_source = "direct_artifact"
                        source_message = "Direct artifact mode selected. Created a pipeline that publishes artifacts without committing a Dockerfile."
                    elif model_used in ("chromadb-direct", "template-only") or model_used.startswith("claude-rag"):
                        template_source = "rag"
                        source_message = "Template found in RAG (ChromaDB) - using a matching template from a previous successful pipeline."
                    elif model_used == "built-in-template":
                        template_source = "builtin"
                        source_message = "Using built-in default template for this language."
                    else:
                        template_source = "llm"
                        source_message = "No matching template found in RAG. LLM created a new pipeline configuration."

                    # Extract validation results
                    validation_passed = result.get("validation_passed", False)
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
                        "pipeline_requirements": requirements or {},
                        "model_used": model_used,
                        "validation_passed": validation_passed,
                        "validation_errors": validation_errors,
                        "fix_attempts": fix_attempts
                    }

                    return {
                        "success": True,
                        "message": "Pipeline generated and validated successfully" if validation_passed else "Pipeline generated but has validation issues",
                        "template_source": template_source,
                        "source_message": source_message,
                        "validation_passed": validation_passed,
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
            elif template_source == "direct_artifact":
                commit_message = f"Add CI/CD pipeline [Direct Artifact] - {language}/{framework} artifact workflow"
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
                        "commit_id": result.get("commit_id", ""),
                        "project_id": result.get("project_id"),
                        "web_url": result.get("web_url", "")
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
                        "gitlab_token": self.gitlab_token,
                        "require_dockerfile": pending.get("template_source") != "direct_artifact"
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

    async def _tool_check_connectivity(self, tool_name: str = "") -> Dict:
        """Check tool connectivity via the connectivity API"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if tool_name:
                    response = await client.get(
                        f"{self.backend_url}/api/v1/connectivity/{tool_name}"
                    )
                    result = response.json()
                    return {
                        "success": True,
                        "tool": tool_name,
                        "status": result.get("status"),
                        "version": result.get("version"),
                        "latency_ms": result.get("latency_ms"),
                        "error": result.get("error"),
                        "base_url": result.get("base_url")
                    }
                else:
                    response = await client.get(
                        f"{self.backend_url}/api/v1/connectivity/"
                    )
                    result = response.json()
                    return {
                        "success": True,
                        "total": result.get("total"),
                        "healthy": result.get("healthy"),
                        "unhealthy": result.get("unhealthy"),
                        "unknown": result.get("unknown"),
                        "tools": result.get("tools", [])
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
