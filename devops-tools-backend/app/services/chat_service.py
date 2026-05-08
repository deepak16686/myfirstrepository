"""
Chat Service - Orchestrates LLM conversations with tool calling
"""
import json
import re
import time
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx

from app.config import Settings
from app.integrations.llm_provider import get_active_provider_name


class ChatService:
    """Service for managing chat conversations with LLM and tool calling"""

    # Tool definitions for LLM
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "run_pipeline",
                "description": (
                    "End-to-end pipeline runner for a GitLab repo. "
                    "Analyzes the repo, checks the RAG store for a "
                    "previously-successful template matching the detected "
                    "language/framework, and:\n"
                    "  • If RAG hit → uses the proven template directly.\n"
                    "  • If no RAG hit → generates a pipeline with the LLM "
                    "and runs an iterative fixer loop (up to 10 attempts) "
                    "against the GitLab CI dry-run validator.\n"
                    "  • If validation passes → commits .gitlab-ci.yml + "
                    "Dockerfile to a new branch (which auto-triggers a "
                    "GitLab pipeline run) and starts a self-healing monitor.\n"
                    "  • If the LLM fixer exhausts all 10 attempts → returns "
                    "a hard failure WITHOUT committing.\n"
                    "RAG persistence happens only after the GitLab pipeline "
                    "actually succeeds (via the in-pipeline learn_record job)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_url": {
                            "type": "string",
                            "description": "The GitLab repository URL (e.g., http://gitlab-server/gitlab/group/my-project)"
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

    SYSTEM_PROMPT = """You are an AI DevOps assistant that runs CI/CD pipelines for GitLab repositories.

Your behavior:
1. When the user pastes a GitLab repository URL (or asks to generate/run/setup a pipeline), call the `run_pipeline` tool. Do NOT ask for confirmation — the tool handles the full flow:
   - Analyzes the repository (detects language, framework, build files).
   - Checks the RAG store for a template that succeeded for this language/framework before. If found, uses it directly.
   - If not found, generates a pipeline with the LLM and runs an iterative fixer loop (up to 10 attempts) against the GitLab CI dry-run validator.
   - If validation passes, commits the files (auto-triggers the GitLab pipeline) and starts a self-healing monitor.
   - If the LLM fixer cannot validate after 10 attempts, the tool returns a failure — do NOT try to commit anyway; just relay the error to the user so they can review.

2. When asked about pipeline status, use the `check_pipeline_status` tool.

3. After `run_pipeline` succeeds, tell the user the branch name AND include the GitLab pipeline link from the tool output so they can click through and watch the run live in GitLab. The portal will also show a live progress card below your message.

4. When `run_pipeline` reports `validation_failed` (fixer exhausted), explain that the LLM could not produce a valid pipeline after 10 attempts, list the top 2-3 errors, and suggest the user retry or refine their request.

Be concise. Don't add filler. The tool result already contains everything the user needs to see."""

    def __init__(self, config: Settings):
        self.config = config
        self.ollama_url = config.ollama_url
        self.gitlab_token = config.gitlab_token
        self.backend_url = "http://devops-tools-backend:8003"  # Self-reference for tool calls (container name for Docker network)

        # In-memory conversation storage (use DB in production)
        self.conversations: Dict[str, List[Dict]] = {}
        self.pending_pipelines: Dict[str, Dict] = {}  # Store generated but not committed pipelines
        # Store monitoring targets from the most recent commit-and-monitor call
        # so the top-level /chat response can surface them to the frontend
        # PipelineProgressCard. Keyed by conversation_id.
        self.monitorings: Dict[str, Dict] = {}
        # Store the most recent generation metadata (source/RAG/fixer info)
        # so the chat response can render a generation badge under the
        # originating assistant bubble. Keyed by conversation_id.
        self.generations: Dict[str, Dict] = {}
        # Live in-flight phase, keyed by request_id (preferred) or
        # conversation_id. Updated by `_tool_run_pipeline` at each phase
        # transition (analyzing → checking_rag → rag_hit | llm_generating →
        # llm_fixing → committing → monitoring | validation_failed). The
        # frontend polls GET /api/v1/chat/inflight/{key} every ~1.5s while
        # its main chat POST is in flight to render a live status card.
        self.inflight: Dict[str, Dict[str, Any]] = {}
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
        model: str = "llama3.1:8b",
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a chat message and return the response.
        Handles tool calling automatically.

        ``request_id`` is an optional client-generated id used as the inflight
        polling key. The frontend generates a UUID per send, passes it on the
        chat POST, then polls ``/api/v1/chat/inflight/{request_id}`` while
        the main response is in flight. We fall back to ``conversation_id``
        if the client didn't supply one.
        """
        # Initialize conversation if needed
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        # Choose the inflight key — prefer the client-provided request_id
        # because conversation_id is empty for the very first message.
        inflight_key = request_id or conversation_id

        # Add user message to history
        self.conversations[conversation_id].append({
            "role": "user",
            "content": user_message
        })

        deterministic_response = await self._handle_pipeline_requirements_message(
            conversation_id,
            user_message,
            inflight_key=inflight_key,
        )
        if deterministic_response is not None:
            self.conversations[conversation_id].append({
                "role": "assistant",
                "content": deterministic_response,
            })
            out = {
                "conversation_id": conversation_id,
                "message": deterministic_response,
                "pending_pipeline": self.pending_pipelines.get(conversation_id),
            }
            monitoring = self.monitorings.get(conversation_id)
            if monitoring:
                out["monitoring"] = monitoring
            generation = self.generations.get(conversation_id)
            if generation:
                out["generation"] = generation
                self.generations.pop(conversation_id, None)
            return out

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
                    tool_call["function"]["arguments"],
                    inflight_key=inflight_key,
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

            pipeline_result = next(
                (
                    item["result"]
                    for item in tool_results
                    if item["tool"] in (
                        "run_pipeline",
                        "generate_pipeline",
                        "commit_pipeline",
                        "setup_pipeline",
                    )
                ),
                None,
            )
            if pipeline_result is not None:
                response = {
                    "message": {
                        "content": self._format_run_pipeline_result(
                            pipeline_result
                        )
                    }
                }
            else:
                # Get final response from LLM after non-pipeline tool execution.
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

        out = {
            "conversation_id": conversation_id,
            "message": assistant_message,
            "pending_pipeline": self.pending_pipelines.get(conversation_id),
        }
        # Surface the most recent commit-and-monitor target so the frontend
        # PipelineProgressCard can start polling /api/v1/pipeline/progress.
        monitoring = self.monitorings.get(conversation_id)
        if monitoring:
            out["monitoring"] = monitoring
        # Surface the most recent generation metadata so the frontend can
        # render a "RAG hit" / "LLM + fixer (N attempts)" badge under the
        # assistant bubble that triggered the generate_pipeline tool call.
        generation = self.generations.get(conversation_id)
        if generation:
            out["generation"] = generation
            # One-shot delivery: clear so the next chat turn doesn't re-attach
            # the same badge to an unrelated assistant message.
            self.generations.pop(conversation_id, None)
        return out

    async def _handle_pipeline_requirements_message(
        self,
        conversation_id: str,
        user_message: str,
        inflight_key: Optional[str] = None,
    ) -> Optional[str]:
        """Deterministic requirements-first flow for GitLab pipeline runs."""
        session = self.pipeline_requirement_sessions.get(conversation_id)

        if session:
            if session.get("state") == "awaiting_confirmation":
                if self._is_affirmative(user_message):
                    requirements = dict(session["values"])
                    self.pipeline_requirement_sessions.pop(conversation_id, None)
                    result = await self._tool_run_pipeline(
                        conversation_id,
                        session["repo_url"],
                        requirements=requirements,
                        skip_requirements_gate=True,
                        inflight_key=inflight_key,
                    )
                    return self._format_run_pipeline_result(result)

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
            return await self._begin_pipeline_requirements_session(
                conversation_id,
                repo_url,
                user_message,
            )

        return None

    async def _begin_pipeline_requirements_session(
        self,
        conversation_id: str,
        repo_url: str,
        user_message: str,
    ) -> str:
        if not self.gitlab_token:
            return "GitLab token is missing. Configure a GitLab token with api scope before generating a pipeline."

        try:
            from app.services.pipeline import pipeline_generator
            analysis = await pipeline_generator.analyze_repository(
                repo_url,
                self.gitlab_token,
            )
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
            return self._format_requirement_questions(
                session,
                questions,
                include_detected=True,
            )

        session["state"] = "awaiting_confirmation"
        return self._format_requirement_confirmation(session)

    def _build_initial_requirement_values(
        self,
        analysis: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, str]]:
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
        if str(language).lower() == "java" and version:
            set_value("java_version", version, "detected")

        build_tool = analysis.get("build_tool") or analysis.get("package_manager")
        if build_tool and build_tool != "unknown":
            set_value("build_tool", build_tool, "detected")

        framework = analysis.get("framework")
        if framework == "gradle":
            framework = "generic"
        if framework:
            set_value(
                "framework",
                framework,
                "detected" if framework != "generic" else "inferred",
            )
        set_value("framework_version", analysis.get("framework_version"), "detected")
        set_value("packaging", analysis.get("packaging"), "detected")

        set_value("module_type", self._infer_module_type(analysis), "inferred")
        set_value("module_path", ".", "inferred")

        if analysis.get("has_dockerfile"):
            set_value("output_mode", "docker-image", "detected")
            set_value("dockerfile_strategy", "reuse-existing", "detected")

        set_value("registry_strategy", "nexus", "default")
        set_value("runner_type", "docker", "default")
        return values, sources

    def _infer_module_type(self, analysis: Dict[str, Any]) -> str:
        root_files = set(analysis.get("files") or [])
        all_paths = analysis.get("all_paths") or analysis.get("all_files") or []
        root_build = {
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "package.json",
            "pyproject.toml",
            "go.mod",
        }
        nested_builds = [
            path
            for path in all_paths
            if "/" in str(path) and str(path).split("/")[-1] in root_build
        ]
        if (
            "settings.gradle" in root_files
            or "settings.gradle.kts" in root_files
            or len(nested_builds) > 1
        ):
            return "multi-module"
        return "single-module"

    def _missing_requirement_questions(self, session: Dict[str, Any]) -> List[Dict[str, str]]:
        values = session["values"]
        language = str(values.get("language", "unknown")).lower()
        questions: List[Dict[str, str]] = []

        if not values.get("output_mode"):
            questions.append({
                "field": "output_mode",
                "question": "Should the pipeline create and push a Docker image, or only build a direct artifact?",
            })

        if language == "unknown":
            questions.append({
                "field": "language",
                "question": "What is the main application language?",
            })

        if language == "java" and not values.get("language_version"):
            questions.append({
                "field": "language_version",
                "question": "Which Java version should the pipeline use? Example: 8, 11, 17, 21.",
            })

        if language == "java" and not values.get("build_tool"):
            questions.append({
                "field": "build_tool",
                "question": "Which Java build tool should be used: Gradle or Maven?",
            })

        framework_source = session["sources"].get("framework")
        if language == "java" and (
            values.get("framework") in (None, "")
            or (values.get("framework") == "generic" and framework_source != "user")
        ):
            questions.append({
                "field": "framework",
                "question": "Is this generic Java, Spring Boot, Quarkus, or Micronaut?",
            })

        if language == "java" and not values.get("packaging"):
            questions.append({
                "field": "packaging",
                "question": "What artifact packaging is expected: JAR, WAR, or native image?",
            })

        output_mode = str(values.get("output_mode", "")).replace("_", "-").lower()
        if output_mode in ("direct-artifact", "artifact", "artifact-only") and not values.get("artifact_publish_target"):
            questions.append({
                "field": "artifact_publish_target",
                "question": "For direct artifact mode, should the artifact stay as GitLab job artifacts, publish to GitLab Package Registry, or be prepared for Nexus publishing?",
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

        if any(word in text for word in ("docker image", "container image", "container pipeline")):
            set_user("output_mode", "docker-image")
            set_user(
                "dockerfile_strategy",
                "generate" if not session["analysis"].get("has_dockerfile") else "reuse-existing",
            )
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

        if "package registry" in text or "gitlab package" in text or "gitlab packages" in text:
            set_user("artifact_publish_target", "gitlab-packages")
        elif "nexus" in text:
            set_user("artifact_publish_target", "nexus")
        elif (
            "gitlab artifact" in text
            or "gitlab artifacts" in text
            or "job artifact" in text
            or "job artifacts" in text
        ):
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
        include_detected: bool = False,
    ) -> str:
        parts = []
        if include_detected:
            parts.append("I analyzed the repository and filled what I could from the code.")
            parts.append(self._format_requirement_values(session, detected_only=True))
        parts.append("I need these details before creating and running the pipeline:")
        for index, item in enumerate(questions, 1):
            parts.append(f"{index}. {item['question']}")
        parts.append("You can answer all questions in one message.")
        return "\n\n".join(parts)

    def _format_requirement_confirmation(self, session: Dict[str, Any]) -> str:
        self._derive_requirement_defaults(session)
        return (
            "Here are the pipeline values I will use:\n\n"
            f"{self._format_requirement_values(session)}\n\n"
            "Reply `proceed` to create, commit, and run the pipeline, or tell me what to change."
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
        return any(word in text for word in ("generate", "create", "add", "build", "prepare", "make", "run", "setup"))

    def _is_affirmative(self, message: str) -> bool:
        text = message.strip().lower()
        if text.startswith(("no", "not ", "don't", "do not")):
            return False
        if any(word in text for word in ("change", "instead", "modify")):
            return False
        affirmative_words = ("yes", "proceed", "continue", "go ahead", "looks good", "run it")
        return text in {"y", "ok", "okay"} or any(word in text for word in affirmative_words)

    async def _call_llm(
        self,
        messages: List[Dict],
        model: str,
        tools: Optional[List] = None
    ) -> Dict:
        """Call the chat LLM API."""
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
        arguments: Dict,
        inflight_key: Optional[str] = None,
    ) -> Dict:
        """Execute a tool and return the result"""
        ikey = inflight_key or conversation_id

        if tool_name == "run_pipeline":
            return await self._tool_run_pipeline(
                conversation_id,
                arguments.get("repo_url", ""),
                inflight_key=ikey,
            )
        # Backward compat aliases — older system prompts may still emit these.
        elif tool_name in ("generate_pipeline", "commit_pipeline", "setup_pipeline"):
            return await self._tool_run_pipeline(
                conversation_id,
                arguments.get("repo_url", ""),
                inflight_key=ikey,
            )
        elif tool_name == "check_pipeline_status":
            return await self._tool_check_status(
                arguments.get("repo_url", ""),
                arguments.get("branch", "main")
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _format_run_pipeline_result(self, result: Dict[str, Any]) -> str:
        """Render pipeline tool output without a second LLM pass.

        The branch, commit, and GitLab URL must come only from the tool result;
        this prevents the chat model from inventing success details when the
        commit or monitor step fails.
        """
        if result.get("success"):
            message = result.get("message")
            if message:
                return message

            branch = result.get("branch", "unknown branch")
            source = result.get("source", "validated pipeline")
            url = result.get("gitlab_pipelines_url")
            if url:
                return (
                    f"Pipeline committed to branch `{branch}` ({source}). "
                    f"Watch it live in GitLab: {url}"
                )
            return f"Pipeline committed to branch `{branch}` ({source})."

        if result.get("validation_failed"):
            errors = result.get("errors") or []
            top_errors = "; ".join(str(e) for e in errors[:3])
            if not top_errors:
                top_errors = result.get("error", "unknown validation error")
            return (
                "Pipeline generation stopped before commit. The LLM fixer "
                f"could not produce a valid pipeline after "
                f"{result.get('fix_attempts', 0)}/"
                f"{result.get('max_attempts', 10)} attempts. "
                f"Top errors: {top_errors}"
            )

        error = result.get("error") or result.get("detail") or "unknown error"
        if result.get("validation_passed"):
            return (
                "Pipeline generation passed dry-run validation, but the "
                f"GitLab commit/monitor step did not complete: {error}"
            )
        return f"Pipeline run failed: {error}"

    # ------------------------------------------------------------------
    # Inflight phase tracking — the frontend polls this every ~1.5s while
    # its main chat POST is in flight, so the user sees exactly which
    # phase the run is in (RAG check / LLM generating / fixer / committing).
    # ------------------------------------------------------------------

    def _set_phase(
        self,
        inflight_key: str,
        phase: str,
        message: str,
        **extra,
    ) -> None:
        """Update the inflight state for a chat request via the shared store."""
        from app.services.chat_inflight import set_phase
        set_phase(inflight_key, phase, message, **extra)

    def _clear_phase(self, inflight_key: Optional[str]) -> None:
        from app.services.chat_inflight import clear_phase
        clear_phase(inflight_key)

    async def _tool_run_pipeline(
        self,
        conversation_id: str,
        repo_url: str,
        requirements: Optional[Dict[str, Any]] = None,
        skip_requirements_gate: bool = False,
        inflight_key: Optional[str] = None,
    ) -> Dict:
        """End-to-end pipeline runner — the single tool exposed to the chat LLM.

        Flow (matches the spec):
            1. POST /api/v1/pipeline/generate
                - Backend short-circuits to RAG when a successful template
                  exists for (language, framework). Otherwise it calls the
                  configured LLM provider and runs an iterative fixer loop
                  (max 10 attempts) against gitlab_dry_run_validator.
            2. If the result reports validation_failed (fixer exhausted),
                stop here and return a clear failure to the chat LLM —
                we deliberately do NOT commit a broken pipeline.
            3. If validated, immediately POST /api/v1/pipeline/commit-and-monitor
                to push the files to a new branch (auto-triggers GitLab).
                RAG hits use a status-only monitor; non-RAG generations use
                the self-heal-on-failure monitor.
            4. Stash the generation metadata + monitoring + pipeline web URL
                so the next /chat response surfaces them to the frontend
                (badge + live progress card + clickable pipeline link).
        """
        ikey = inflight_key or conversation_id
        try:
            # ---- Phase 1: generate + dry-run + iterative fixer (≤10) ------
            self._set_phase(
                ikey, "analyzing",
                "Analyzing repository structure (language, framework, files)...",
                repo_url=repo_url,
            )
            self._set_phase(
                ikey, "checking_rag",
                "Checking RAG cache for a proven template matching this language/framework...",
                repo_url=repo_url,
            )
            async with httpx.AsyncClient(timeout=900.0) as client:
                gen_resp = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.gitlab_token,
                        "model": "pipeline-generator-v5",  # ignored by CLI providers
                        # Forward the inflight key so the generator can
                        # publish phase updates ("calling_llm",
                        # "fixer_attempt N/10", ...) the frontend renders.
                        "progress_key": ikey,
                        "additional_context": self._build_generation_context(requirements or {}),
                        "pipeline_requirements": requirements or {},
                    },
                )
                gen_result = gen_resp.json()

            if not gen_result.get("success"):
                self._set_phase(
                    ikey, "error",
                    gen_result.get("detail", "Pipeline generation failed"),
                )
                return {
                    "success": False,
                    "error": gen_result.get("detail", "Pipeline generation failed"),
                }

            analysis = gen_result.get("analysis") or {}
            language = analysis.get("language", "unknown")
            framework = analysis.get("framework", "generic")
            fix_attempts = int(gen_result.get("fix_attempts") or 0)
            validation_passed = bool(gen_result.get("validation_passed"))
            rag_hit = bool(gen_result.get("rag_hit"))
            is_direct_artifact = gen_result.get("model_used") == "direct-artifact-template"
            status_only_monitor = rag_hit or is_direct_artifact
            final_errors = gen_result.get("final_errors") or []

            # Surface the deterministic outcome of phase 1 to the portal.
            if is_direct_artifact:
                self._set_phase(
                    ikey, "direct_artifact",
                    f"Direct artifact pipeline prepared for {language}/{framework}. No Dockerfile will be committed.",
                    rag_hit=False, language=language, framework=framework,
                )
            elif rag_hit:
                self._set_phase(
                    ikey, "rag_hit",
                    f"Template found in RAG ({language}/{framework}). No LLM call.",
                    rag_hit=True, language=language, framework=framework,
                )
            elif validation_passed and fix_attempts <= 1:
                self._set_phase(
                    ikey, "llm_validated",
                    f"No RAG match — {get_active_provider_name()} generated a valid pipeline on attempt 1/10.",
                    fix_attempts=fix_attempts, language=language, framework=framework,
                )
            elif validation_passed and fix_attempts > 1:
                self._set_phase(
                    ikey, "llm_fixed",
                    f"No RAG match — LLM + auto-fixer converged after {fix_attempts}/10 attempts.",
                    fix_attempts=fix_attempts, language=language, framework=framework,
                )
            else:
                self._set_phase(
                    ikey, "validation_failed",
                    f"LLM fixer exhausted {fix_attempts}/10 attempts. NOT committing — pipeline is invalid.",
                    fix_attempts=fix_attempts, language=language, framework=framework,
                    errors=final_errors[:3],
                )

            # Stash generation metadata for the chat response badge.
            self.generations[conversation_id] = {
                "template_source": gen_result.get("template_source"),
                "source_token": gen_result.get("source_token"),
                "rag_hit": rag_hit,
                "had_rag_reference": bool(gen_result.get("had_rag_reference")),
                "fix_attempts": fix_attempts,
                "validation_passed": validation_passed,
                "persisted_to_rag": bool(gen_result.get("persisted_to_rag")),
                "model_used": gen_result.get("model_used"),
                "language": language,
                "framework": framework,
            }

            # ---- Phase 2: hard failure if fixer exhausted attempts --------
            if not validation_passed:
                # Important: we have a candidate pipeline but it didn't pass
                # validation. Don't commit — surface failure to the user.
                return {
                    "success": False,
                    "validation_failed": True,
                    "fix_attempts": fix_attempts,
                    "max_attempts": 10,
                    "rag_hit": rag_hit,
                    "language": language,
                    "framework": framework,
                    "errors": final_errors[:5],
                    "error": (
                        f"LLM fixer exhausted {fix_attempts} of 10 attempts and "
                        f"could not produce a valid pipeline for "
                        f"{language}/{framework}. Pipeline NOT committed. "
                        f"Top errors: {'; '.join(final_errors[:3]) if final_errors else 'unknown'}"
                    ),
                }

            # Build a self-describing commit message so the GitLab pipeline
            # list reads like "AI run · RAG cache hit · attempt 1" rather
            # than the opaque "Add CI/CD pipeline".
            if is_direct_artifact:
                commit_label = "direct artifact"
            elif rag_hit:
                commit_label = "RAG cache hit"
            elif fix_attempts > 1:
                commit_label = f"LLM + auto-fixer · {fix_attempts}/10 attempts"
            else:
                commit_label = "LLM-generated"
            commit_message = f"AI pipeline run · {commit_label} · attempt 1 [AI Generated]"

            # ---- Phase 3: commit + start monitor --------------------------
            self._set_phase(
                ikey, "committing",
                f"Validated. Committing to GitLab and starting the pipeline...",
                rag_hit=rag_hit, fix_attempts=fix_attempts,
            )
            async with httpx.AsyncClient(timeout=300.0) as client:
                commit_resp = await client.post(
                    f"{self.backend_url}/api/v1/pipeline/commit-and-monitor",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.gitlab_token,
                        "gitlab_ci": gen_result.get("gitlab_ci", ""),
                        "dockerfile": gen_result.get("dockerfile", ""),
                        "language": language,
                        "framework": framework,
                        "commit_message": commit_message,
                        "model_used": gen_result.get("model_used"),
                        "max_heal_attempts": 0 if status_only_monitor else 10,
                        "rag_hit": rag_hit,
                    },
                )
                commit_result = commit_resp.json()

            if not commit_result.get("success"):
                return {
                    "success": False,
                    "error": commit_result.get("detail", "Failed to commit pipeline"),
                    "validation_passed": True,
                    "fix_attempts": fix_attempts,
                }

            # ---- Phase 4: build the GitLab pipelines URL for the user ----
            project_id = commit_result.get("project_id")
            branch = commit_result.get("branch", "")
            project_path = (analysis.get("project_path")
                            or self._infer_project_path(repo_url))
            # The user-facing GitLab URL — prefer the public funneled host
            # so links work from any browser, not just localhost.
            gitlab_pipelines_url = self._build_gitlab_pipelines_url(
                project_path=project_path,
                branch=branch,
            )

            monitoring = commit_result.get("monitoring") or {}
            if not monitoring.get("project_id"):
                monitoring = {
                    "project_id": project_id,
                    "branch": branch,
                    "rl_enabled": not status_only_monitor,
                    "self_healing_enabled": not status_only_monitor,
                    "max_heal_attempts": 0 if status_only_monitor else 10,
                    "monitor_mode": (
                        "status_only" if status_only_monitor else "self_heal_on_failure"
                    ),
                }
            # Surface the URL on the monitoring object so the progress card
            # can render the click-through link.
            monitoring["gitlab_pipelines_url"] = gitlab_pipelines_url
            self.monitorings[conversation_id] = monitoring

            # Phase 4: pipeline is now running in GitLab. Frontend will pivot
            # from the inflight card to the live PipelineProgressCard.
            if is_direct_artifact:
                monitoring_message = (
                    f"Direct artifact pipeline committed to {branch}. "
                    "Status-only monitoring is active."
                )
            elif rag_hit:
                monitoring_message = (
                    f"RAG template committed to {branch}. Status-only monitoring is active."
                )
            else:
                monitoring_message = f"Pipeline committed to {branch}. Monitoring GitLab — link below."
            self._set_phase(
                ikey, "monitoring",
                monitoring_message,
                gitlab_pipelines_url=gitlab_pipelines_url, branch=branch,
                rag_hit=rag_hit, fix_attempts=fix_attempts,
            )

            source_label = (
                "Direct artifact template" if is_direct_artifact
                else "RAG cache hit" if rag_hit
                else f"LLM + auto-fixer ({fix_attempts} attempts)"
                if fix_attempts > 1 else "LLM-generated"
            )
            if is_direct_artifact:
                user_message = (
                    f"Pipeline committed to branch `{branch}` ({source_label}). "
                    f"Watch it live in GitLab: {gitlab_pipelines_url} . "
                    "Direct artifact mode was used, so only `.gitlab-ci.yml` was committed; "
                    "no Dockerfile was created or pushed. Status-only monitoring is active."
                )
            elif rag_hit:
                user_message = (
                    f"Pipeline committed to branch `{branch}` ({source_label}). "
                    f"Watch it live in GitLab: {gitlab_pipelines_url} . "
                    f"RAG template was used directly from ChromaDB; no LLM or "
                    f"self-healing path is running. Status-only monitoring will "
                    f"not write this direct RAG run back to ChromaDB."
                )
            else:
                user_message = (
                    f"Pipeline committed to branch `{branch}` ({source_label}). "
                    f"Watch it live in GitLab: {gitlab_pipelines_url} . "
                    f"Self-healing monitor is running (up to 10 attempts) "
                    f"and will save the template to RAG once all stages pass."
                )

            return {
                "success": True,
                "branch": branch,
                "commit_id": commit_result.get("commit_id", ""),
                "project_id": project_id,
                "monitoring_started": True,
                "monitoring": monitoring,
                "gitlab_pipelines_url": gitlab_pipelines_url,
                "source": source_label,
                "rag_hit": rag_hit,
                "fix_attempts": fix_attempts,
                "validation_passed": True,
                "language": language,
                "framework": framework,
                "message": user_message,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _infer_project_path(repo_url: str) -> str:
        """Best-effort host-stripped path like ``group/project`` from a repo URL."""
        try:
            from app.services.pipeline.analyzer import parse_gitlab_url
            return parse_gitlab_url(repo_url).get("path", "")
        except Exception:
            return ""

    def _build_gitlab_pipelines_url(self, project_path: str, branch: str) -> str:
        """Return a clickable URL the user can paste / open from the browser.

        Uses ``settings.public_base_url`` so links stay on the Cloudflare
        public domain. Tailscale remains only as a legacy fallback.
        """
        public_domain = getattr(self.config, "public_base_domain", None)
        if public_domain:
            base = f"https://gitlab.{public_domain.strip('/')}/gitlab"
        else:
            public_root = (
                getattr(self.config, "public_base_url", None)
                or getattr(self.config, "tailscale_base_url", None)
                or "https://deepaksharma.live"
            )
            base = f"{public_root.rstrip('/')}/gitlab"
        # Pipelines list filtered to the freshly-committed branch — gives the
        # user a deep link to "the run that just kicked off".
        from urllib.parse import quote
        return (
            f"{base.rstrip('/')}/{project_path}/-/pipelines?ref={quote(branch)}"
        )

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
