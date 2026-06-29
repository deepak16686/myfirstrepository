"""
ChromaDB Template CRUD Functions

Standalone async functions for managing pipeline templates in ChromaDB.
"""
import hashlib
import fnmatch
import json
import re
import shlex
from typing import Dict, Any, Optional, List
from datetime import datetime

import yaml

from app.config import tools_manager
from app.integrations.chromadb import ChromaDBIntegration

from .constants import (
    TEMPLATES_COLLECTION,
    SUCCESSFUL_PIPELINES_COLLECTION,
    GENERIC_TEMPLATE_COLLECTION,
)
from .validator import _ensure_learn_stage


def _get_chromadb() -> ChromaDBIntegration:
    chromadb_config = tools_manager.get_tool("chromadb")
    return ChromaDBIntegration(chromadb_config)


async def get_reference_pipeline(
    language: str,
    framework: str,
    analysis: Optional[Dict[str, Any]] = None,
) -> tuple:
    """
    Get reference pipeline from RL successful pipelines or built-in defaults.
    Returns (template_yaml, source_language) tuple.

    PRIORITY ORDER:
    1. Best successful pipeline from RL for this language (proven)
    2. Generic_template stage reference for LLM fallback
    3. Built-in default template for the language (hardcoded fallback)

    NOTE: We intentionally skip the pipeline_templates collection because it
    contains templates that only passed dry-run (YAML lint) but may have failed
    in actual GitLab execution. Only successful_pipelines (stored by the learn
    stage after real pipeline success) are trustworthy.
    """
    try:
        # PRIORITY 1: Check for successful pipelines for this language
        print(f"[RL] Checking for successful pipelines for {language}/{framework}...")
        best_config = await get_best_pipeline_config(language, framework, analysis=analysis)
        if best_config:
            print(f"[RL] Using proven successful pipeline config ({len(best_config)} chars)")
            return _ensure_learn_stage(best_config), language

        # PRIORITY 2: Use the generic stage reference. Do not reuse a
        # different language's successful template here; when the exact
        # language template is deleted, the intended flow is:
        # RAG miss -> Generic_template reference -> LLM generates/fixes ->
        # successful pipeline stores back into gitlab_successful_template.
        print(f"[RL] No proven pipeline for {language}, using Generic_template reference...")
        generic_config = await get_generic_template_pipeline()
        if generic_config:
            print(f"[GenericTemplate] Using generic reference ({len(generic_config)} chars)")
            return _ensure_learn_stage(generic_config), "generic"

        # PRIORITY 3: No reusable RAG/reference template.
        # Do not pass built-in defaults as a "reference" because that makes the
        # generation metadata look RAG-influenced. The LLM will generate from
        # guardrails; defaults are still used later only as extraction fallback.
        print(f"[RL] No compatible RAG or Generic_template reference for {language}/{framework}")
        return None, None

    except Exception as e:
        print(f"[RL] Error getting reference pipeline: {e}")
        return None, None


def _analysis_repo_paths(analysis: Optional[Dict[str, Any]]) -> set:
    """Return normalized repo paths from analyzer output."""
    if not analysis:
        return set()

    paths = set()
    for value in analysis.get("all_files") or []:
        if value:
            paths.add(str(value).replace("\\", "/").strip("/").lower())
    for value in analysis.get("files") or []:
        if value:
            paths.add(str(value).replace("\\", "/").strip("/").lower())
    return paths


def _repo_has_path(repo_paths: set, required_path: str) -> bool:
    required = required_path.replace("\\", "/").strip().strip("'\"").strip("/").lower()
    if not required:
        return True
    if required in {".", "./"}:
        return True
    if required.endswith("/"):
        return any(path.startswith(required) for path in repo_paths)
    if any(char in required for char in "*?[]"):
        return any(fnmatch.fnmatch(path, required) for path in repo_paths)
    if required in repo_paths:
        return True
    # Docker COPY commonly references a directory as "src" rather than "src/".
    return any(path.startswith(required + "/") for path in repo_paths)


def _extract_template_sections(doc: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}

    if '### .gitlab-ci.yml' in doc and '```yaml' in doc:
        start = doc.find('```yaml', doc.find('### .gitlab-ci.yml')) + 7
        end = doc.find('```', start)
        if start > 7 and end > start:
            sections['gitlab_ci'] = doc[start:end].strip()

    if '### Dockerfile' in doc and '```dockerfile' in doc:
        start = doc.find('```dockerfile', doc.find('### Dockerfile')) + 13
        end = doc.find('```', start)
        if start > 13 and end > start:
            sections['dockerfile'] = doc[start:end].strip()

    return sections


def _normalize_major_version(value: Any) -> str:
    """Return a Java major version string such as 8, 11, 17, or 21."""
    if value is None:
        return ""
    match = re.search(r"\d{1,2}", str(value))
    return match.group(0) if match else ""


def _normalize_language_version(value: Any, language: str = "") -> str:
    """Return a language version suitable for framework aliases."""
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    if not normalized:
        return ""

    language_key = _normalize_stack_value(language)
    prefixes = [
        language_key,
        "jdk" if language_key == "java" else "",
        "py" if language_key == "python" else "",
        "python" if language_key == "python" else "",
        "node" if language_key in {"javascript", "typescript", "node"} else "",
    ]
    for prefix in [prefix for prefix in prefixes if prefix]:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].lstrip("-_ ")
            break

    match = re.search(r"\d+(?:\.\d+)*", normalized)
    if not match:
        return ""
    version = match.group(0)
    if language_key == "java":
        return _normalize_major_version(version)
    return version


def _analysis_java_version(analysis: Optional[Dict[str, Any]]) -> str:
    if not analysis:
        return ""
    return _normalize_major_version(
        analysis.get("java_version") or analysis.get("language_version")
    )


def _analysis_language_version(
    analysis: Optional[Dict[str, Any]],
    language: str = "",
) -> str:
    if not analysis:
        return ""
    language_key = _normalize_stack_value(language or analysis.get("language"))
    return _normalize_language_version(
        analysis.get(f"{language_key}_version")
        or analysis.get("language_version")
        or analysis.get("runtime_version"),
        language_key,
    )


def _normalize_stack_value(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _analysis_framework(analysis: Optional[Dict[str, Any]]) -> str:
    if not analysis:
        return ""
    return _normalize_stack_value(analysis.get("framework"))


def _normalize_output_mode(value: Any) -> str:
    normalized = _normalize_stack_value(value)
    if normalized in {"direct-artifact", "artifact", "artifact-only"}:
        return "direct-artifact"
    if normalized in {"docker-image", "docker", "image", "container", "container-image"}:
        return "docker-image"
    return ""


def _analysis_output_mode(analysis: Optional[Dict[str, Any]]) -> str:
    analysis = analysis or {}
    requirements = analysis.get("pipeline_requirements") or {}
    return _normalize_output_mode(
        analysis.get("output_mode") or requirements.get("output_mode")
    )


def _template_framework(metadata: Optional[Dict[str, Any]]) -> str:
    metadata = metadata or {}
    return _normalize_stack_value(metadata.get("framework"))


def _template_java_versions(text: str, metadata: Optional[Dict[str, Any]] = None) -> set:
    """Infer Java major versions referenced by a stored pipeline template."""
    versions = set()
    metadata = metadata or {}
    for key in ("java_version", "language_version"):
        version = _normalize_major_version(metadata.get(key))
        if version:
            versions.add(version)

    if not text:
        return versions

    patterns = [
        r"jdk-?(\d{1,2})",
        r"jre-?(\d{1,2})",
        r"temurin[-:]?(\d{1,2})",
        r"corretto[-:]?(\d{1,2})",
        r"JavaLanguageVersion\.of\(\s*(\d{1,2})\s*\)",
        r"<(?:java\.version|maven\.compiler\.release|maven\.compiler\.source|maven\.compiler\.target)>\s*(\d{1,2})\s*</",
    ]
    for pattern in patterns:
        versions.update(re.findall(pattern, text, flags=re.IGNORECASE))
    return versions


def _template_build_tool(text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = metadata or {}
    build_tool = _normalize_stack_value(metadata.get("build_tool"))
    if build_tool:
        return build_tool
    if re.search(r"\bgradle\b|build\.gradle|gradlew", text, flags=re.IGNORECASE):
        return "gradle"
    if re.search(r"\bmvn\b|pom\.xml|maven", text, flags=re.IGNORECASE):
        return "maven"
    return ""


def _candidate_template_frameworks(
    language: str,
    framework: str = "",
    analysis: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Return safe framework lookup keys for reusable templates.

    Some stored Java templates are keyed by build tool (``gradle``/``maven``)
    because the CI implementation is build-tool-specific, while the chat UI may
    describe the application framework as ``generic`` or ``spring-boot``. Exact
    matches are still tried first; build-tool fallback is allowed only when the
    analyzer explicitly identified that build tool and the compatibility gate
    will still validate the chosen template.
    """
    analysis = analysis or {}
    candidates: List[str] = []

    def add(value: Any) -> None:
        normalized = str(value or "").strip().lower()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    add(framework)
    build_tool = analysis.get("build_tool") or analysis.get("package_manager")
    if str(language or "").lower() == "java" and str(build_tool or "").lower() in {"gradle", "maven"}:
        add(build_tool)
    return candidates or [""]


def _framework_matches_stack(
    language: str,
    requested_framework: str,
    template_framework: str,
    requested_build_tool: str,
    requested_language_version: str = "",
) -> bool:
    if not requested_framework or not template_framework:
        return True
    if requested_framework == template_framework:
        return True

    version = _normalize_language_version(requested_language_version, language)
    if version:
        requested_alias = f"{requested_framework}-{language}{version}"
        if template_framework == requested_alias:
            return True

    if language == "java":
        # Older proven Java templates are keyed by build tool. Treat that as
        # the same stack only when the target repo is a generic Java app using
        # that exact build tool; do not let Spring/other framework requests
        # fall through to a plain Gradle/Maven template.
        if (
            requested_framework in {"generic", "java"}
            and requested_build_tool in {"gradle", "maven"}
            and template_framework in {
                requested_build_tool,
                f"{requested_build_tool}-{language}{version}" if version else "",
            }
        ):
            return True
    return False


def _normalize_template_for_fingerprint(gitlab_ci: str, dockerfile: str) -> str:
    """Normalize volatile source banners before generating a uniqueness hash."""

    def clean(text: str) -> str:
        lines: List[str] = []
        for raw_line in (text or "").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith(("# ╔", "# ║", "# ╚")):
                continue
            if re.match(r"^#\s*(Pipeline Source|Generator|Generated):", stripped):
                continue
            lines.append(raw_line.rstrip())
        return "\n".join(lines).strip()

    return f"{clean(gitlab_ci)}\n---DOCKERFILE---\n{clean(dockerfile)}"


def _template_fingerprint(gitlab_ci: str, dockerfile: str) -> str:
    return hashlib.sha256(
        _normalize_template_for_fingerprint(gitlab_ci, dockerfile).encode()
    ).hexdigest()


_GITLAB_RESERVED_TOP_KEYS = {
    "stages",
    "types",
    "variables",
    "workflow",
    "default",
    "include",
    "image",
    "services",
    "before_script",
    "after_script",
    "cache",
    "pages",
    "schedules",
}


def _parse_gitlab_ci_jobs(gitlab_ci: str) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Parse top-level GitLab CI jobs from a template."""
    if not gitlab_ci or not gitlab_ci.strip():
        return {}, ["template is missing .gitlab-ci.yml content"]

    try:
        parsed = yaml.safe_load(gitlab_ci) or {}
    except yaml.YAMLError as exc:
        return {}, [f"template .gitlab-ci.yml is not parseable YAML: {exc}"]

    if not isinstance(parsed, dict):
        return {}, ["template .gitlab-ci.yml must be a YAML mapping"]

    jobs: Dict[str, Dict[str, Any]] = {}
    for name, config in parsed.items():
        normalized = str(name)
        if normalized in _GITLAB_RESERVED_TOP_KEYS or normalized.startswith("."):
            continue
        if isinstance(config, dict) and ("script" in config or "stage" in config):
            jobs[normalized] = config

    if not jobs:
        return {}, ["template .gitlab-ci.yml has no executable jobs"]
    return jobs, []


def _script_lines(job: Dict[str, Any]) -> List[str]:
    script = job.get("script", [])
    entries = script if isinstance(script, list) else [script]
    lines: List[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            entry = " ".join(f"{key}: {value}" for key, value in entry.items())
        for line in str(entry or "").splitlines():
            line = line.strip()
            if line:
                lines.append(line)
    return lines


def _is_noop_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return True
    lowered = stripped.lower()
    if lowered in {"true", ":", "exit 0"}:
        return True
    if re.match(r"^(echo|printf)\b", lowered):
        # Even echo-with-redirection is not proof of useful CI work; it is
        # usually only config/report scaffolding and must be paired with a real
        # build/test/scan command in reusable templates.
        return True
    return False


def _job_has_real_command(job: Dict[str, Any]) -> bool:
    return any(not _is_noop_line(line) for line in _script_lines(job))


def _job_has_command(job: Dict[str, Any], patterns: List[str]) -> bool:
    text = "\n".join(_script_lines(job))
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _jobs_for(
    jobs: Dict[str, Dict[str, Any]],
    stages: set,
    name_hints: set,
) -> List[tuple[str, Dict[str, Any]]]:
    matched: List[tuple[str, Dict[str, Any]]] = []
    for name, job in jobs.items():
        stage = str(job.get("stage") or "").lower()
        normalized_name = name.lower()
        if stage in stages or any(hint in normalized_name for hint in name_hints):
            matched.append((name, job))
    return matched


def _any_job_has_command(
    matched_jobs: List[tuple[str, Dict[str, Any]]],
    patterns: List[str],
) -> bool:
    return any(_job_has_command(job, patterns) for _, job in matched_jobs)


def _compile_command_patterns(analysis: Optional[Dict[str, Any]]) -> List[str]:
    analysis = analysis or {}
    language = str(analysis.get("language") or "").lower()
    build_tool = str(
        analysis.get("build_tool") or analysis.get("package_manager") or ""
    ).lower()

    if language == "java":
        if build_tool == "maven":
            return [r"(^|\s)(\./mvnw|mvn)\b.*\b(clean|package|verify|install|test)\b"]
        if build_tool == "gradle":
            return [r"(^|\s)(\./gradlew|gradle)\b.*\b(clean|build|assemble|bootjar|jar|test|check)\b"]
        return [
            r"(^|\s)(\./mvnw|mvn)\b.*\b(clean|package|verify|install|test)\b",
            r"(^|\s)(\./gradlew|gradle)\b.*\b(clean|build|assemble|bootjar|jar|test|check)\b",
            r"(^|\s)javac\b",
        ]
    if language in {"javascript", "typescript", "node"}:
        return [r"\b(npm|yarn|pnpm)\b.*\b(build|test|lint)\b"]
    if language == "python":
        return [r"\b(pytest|python\s+-m\s+pytest|pip\s+install|python\s+-m\s+build)\b"]
    if language == "go":
        return [r"\bgo\s+(build|test|mod\s+download)\b"]
    if language == "rust":
        return [r"\bcargo\s+(build|test|clippy)\b"]
    if language == "ruby":
        return [r"\b(bundle\s+exec|bundle\s+install|rake|rspec)\b"]
    if language == "php":
        return [r"\b(composer\s+(install|test)|php\s+-l|phpunit)\b"]
    if language in {"dotnet", "csharp"}:
        return [r"\bdotnet\s+(restore|build|publish|test)\b"]
    if language == "kotlin":
        return [r"\b(gradle|./gradlew)\b.*\b(build|test|check)\b"]
    if language == "scala":
        return [r"\b(sbt|scala-cli)\b.*\b(compile|test|package)\b"]
    return [r"\b(make|gradle|mvn|npm|yarn|pnpm|pytest|go|cargo|bundle|composer)\b"]


def _template_output_mode(
    template_files: Dict[str, str],
    analysis: Optional[Dict[str, Any]],
) -> str:
    requested = _analysis_output_mode(analysis)
    if requested:
        return requested
    if (template_files.get("dockerfile") or "").strip():
        return "docker-image"
    return "direct-artifact"


def _actual_template_output_mode(
    template_files: Dict[str, str],
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    metadata = metadata or {}
    for key in ("output_mode", "artifact_mode", "pipeline_output_mode"):
        normalized = _normalize_output_mode(metadata.get(key))
        if normalized:
            return normalized
    if (template_files.get("dockerfile") or "").strip():
        return "docker-image"
    gitlab_ci = template_files.get("gitlab_ci") or ""
    if re.search(r"(?im)^\s*artifacts\s*:", gitlab_ci):
        return "direct-artifact"
    return ""


def template_quality_issues(
    template_files: Dict[str, str],
    analysis: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Detect reusable-template no-ops.

    A GitLab pipeline can be green while doing no useful work, for example a
    stage that only runs ``echo``. Such templates must not be reused directly
    or written as proven RAG records.
    """
    metadata = metadata or {}
    gitlab_ci = template_files.get("gitlab_ci") or ""
    dockerfile = template_files.get("dockerfile") or ""
    jobs, issues = _parse_gitlab_ci_jobs(gitlab_ci)
    if issues:
        return issues

    core_jobs = _jobs_for(
        jobs,
        {"compile", "build", "test", "sast", "quality", "security", "scan"},
        {"compile", "build", "test", "sast", "quality", "trivy", "scan"},
    )
    for name, job in core_jobs:
        if not _job_has_real_command(job):
            issues.append(f"job {name} is a no-op; reusable templates must run real commands")

    compile_jobs = _jobs_for(jobs, {"compile"}, {"compile"})
    if not compile_jobs:
        issues.append("template is missing a compile job")
    elif not _any_job_has_command(compile_jobs, _compile_command_patterns(analysis)):
        issues.append("compile job does not run a real language build/test command")

    output_mode = _template_output_mode(template_files, analysis)
    if output_mode == "docker-image":
        if not dockerfile.strip():
            issues.append("docker-image template is missing a Dockerfile")
        elif not re.search(r"(?im)^\s*FROM\s+\S+", dockerfile):
            issues.append("Dockerfile has no FROM instruction")

        build_jobs = _jobs_for(jobs, {"build"}, {"build_image", "docker", "kaniko", "build"})
        if not _any_job_has_command(
            build_jobs,
            [r"/kaniko/executor\b", r"\bdocker\s+build\b", r"\bpodman\s+build\b", r"\bbuildah\s+bud\b"],
        ):
            issues.append("build job does not build a container image")

        test_jobs = _jobs_for(jobs, {"test"}, {"test_image", "smoke", "integration", "test"})
        if not test_jobs:
            issues.append("docker-image template is missing an image/test job")
        elif not _any_job_has_command(
            test_jobs,
            [
                r"\bcurl\b",
                r"\bwget\b",
                r"\bdocker\s+(run|pull)\b",
                r"\b(kubectl|helm)\b",
                r"\b(pytest|npm|yarn|pnpm|gradle|mvn|go|cargo)\b.*\btest\b",
            ],
        ):
            issues.append("test job does not verify the built artifact or image")

        scan_jobs = _jobs_for(jobs, {"security", "scan", "sast"}, {"trivy", "sast", "scan", "security"})
        if not _any_job_has_command(
            scan_jobs,
            [r"\btrivy\b", r"\bsemgrep\b", r"\bdependencycheck", r"\bgrype\b", r"\bsonar-scanner\b"],
        ):
            issues.append("security/scan jobs do not run a real scanner")

        quality_jobs = _jobs_for(jobs, {"quality"}, {"quality", "sonar", "lint"})
        if quality_jobs and not _any_job_has_command(
            quality_jobs,
            [r"\bsonar-scanner\b", r"\b(eslint|ruff|pylint|golangci-lint|cargo\s+clippy|mvn|gradle)\b"],
        ):
            issues.append("quality job is present but does not run a real quality tool")
    else:
        if not re.search(r"(?im)^\s*artifacts\s*:", gitlab_ci) and not _any_job_has_command(
            list(jobs.items()),
            [r"\b(mvn\s+deploy|gradle\s+publish|curl\b.*(packages|nexus|repository))\b"],
        ):
            issues.append("direct-artifact template does not expose or publish build artifacts")

    return list(dict.fromkeys(issues))


def validate_reusable_template(
    template_files: Dict[str, str],
    analysis: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Run all RAG reuse/storage gates for a candidate template."""
    return list(dict.fromkeys(
        template_compatibility_issues(template_files, analysis, metadata=metadata)
        + template_quality_issues(template_files, analysis, metadata=metadata)
    ))


def _iter_docker_copy_sources(dockerfile: str) -> List[str]:
    """Extract host-context COPY/ADD sources from a Dockerfile."""
    if not dockerfile:
        return []

    logical_lines: List[str] = []
    current = ""
    for raw_line in dockerfile.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.endswith("\\"):
            current += line[:-1] + " "
            continue
        logical_lines.append((current + line).strip())
        current = ""
    if current:
        logical_lines.append(current.strip())

    sources: List[str] = []
    for line in logical_lines:
        if not re.match(r'^(COPY|ADD)\s+', line, flags=re.IGNORECASE):
            continue

        instruction, remainder = line.split(None, 1)
        if "--from=" in remainder:
            # This copies from another build stage, not from the target repo.
            continue

        remainder = remainder.strip()
        if remainder.startswith("["):
            try:
                values = json.loads(remainder)
                if isinstance(values, list) and len(values) >= 2:
                    sources.extend(str(value) for value in values[:-1])
            except Exception:
                pass
            continue

        try:
            tokens = shlex.split(remainder)
        except ValueError:
            tokens = remainder.split()

        tokens = [token for token in tokens if not token.startswith("--")]
        if len(tokens) >= 2:
            sources.extend(tokens[:-1])

    return sources


def template_compatibility_issues(
    template_files: Dict[str, str],
    analysis: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Detect whether a cached template matches the target repo stack.

    RAG direct reuse must be conservative: if a proven template assumes a
    different framework, build tool, language version, output mode, or repo
    file layout, it is not a valid cache hit and the generator must continue
    into LLM/new-template generation.
    """
    repo_paths = _analysis_repo_paths(analysis)
    gitlab_ci = template_files.get('gitlab_ci') or ''
    dockerfile = template_files.get('dockerfile') or ''
    combined = f"{gitlab_ci}\n{dockerfile}"
    metadata = metadata or {}
    issues: List[str] = []

    language = _normalize_stack_value((analysis or {}).get("language"))
    requested_framework = _analysis_framework(analysis)
    template_framework = _template_framework(metadata)
    requested_build_tool = _normalize_stack_value(
        (analysis or {}).get("build_tool")
        or (analysis or {}).get("package_manager")
    )
    if not _framework_matches_stack(
        language,
        requested_framework,
        template_framework,
        requested_build_tool,
        _analysis_language_version(analysis, language),
    ):
        issues.append(
            "template framework mismatch: "
            f"repo uses {requested_framework}, template uses {template_framework}"
        )

    requested_output_mode = _analysis_output_mode(analysis)
    template_output_mode = _actual_template_output_mode(template_files, metadata)
    if (
        requested_output_mode
        and template_output_mode
        and requested_output_mode != template_output_mode
    ):
        issues.append(
            "template output mode mismatch: "
            f"repo requires {requested_output_mode}, template provides {template_output_mode}"
        )

    if language == "java":
        requested_version = _analysis_java_version(analysis)
        template_versions = _template_java_versions(combined, metadata)
        if requested_version and template_versions and requested_version not in template_versions:
            issues.append(
                "template Java version mismatch: "
                f"repo requires {requested_version}, template uses {', '.join(sorted(template_versions))}"
            )

        template_build_tool = _template_build_tool(combined, metadata)
        if (
            requested_build_tool in {"gradle", "maven"}
            and template_build_tool in {"gradle", "maven"}
            and requested_build_tool != template_build_tool
        ):
            issues.append(
                "template build tool mismatch: "
                f"repo uses {requested_build_tool}, template uses {template_build_tool}"
            )

    if not repo_paths:
        return list(dict.fromkeys(issues))

    required_files = {
        "Makefile.PL": r'\bMakefile\.PL\b',
        "Build.PL": r'\bBuild\.PL\b',
        "cpanfile": r'\bcpanfile\b',
        "dist.ini": r'\bdist\.ini\b',
        "package.json": r'\bpackage\.json\b|package\*\.json',
        "requirements.txt": r'\brequirements\.txt\b',
        "pyproject.toml": r'\bpyproject\.toml\b',
        "setup.py": r'\bsetup\.py\b',
        "pom.xml": r'\bpom\.xml\b',
        "build.gradle": r'\bbuild\.gradle\b',
        "build.gradle.kts": r'\bbuild\.gradle\.kts\b',
        "Cargo.toml": r'\bCargo\.toml\b',
        "go.mod": r'\bgo\.mod\b',
        "Gemfile": r'\bGemfile\b',
        "composer.json": r'\bcomposer\.json\b',
        "mix.exs": r'\bmix\.exs\b',
        "build.sbt": r'\bbuild\.sbt\b',
        "Package.swift": r'\bPackage\.swift\b',
    }

    for required_file, pattern in required_files.items():
        if re.search(pattern, combined) and not _repo_has_path(repo_paths, required_file):
            issues.append(f"template requires missing repo file: {required_file}")

    if re.search(r'\*\.csproj\b|\.csproj\b', combined) and not any(
        path.endswith('.csproj') for path in repo_paths
    ):
        issues.append("template requires missing repo file: *.csproj")

    for source in _iter_docker_copy_sources(dockerfile):
        source = source.strip().strip("'\"")
        if not source or source in {".", "./"}:
            continue
        if source.startswith(("/", "http://", "https://", "$")) or "${" in source:
            continue
        if not _repo_has_path(repo_paths, source):
            issues.append(f"Dockerfile COPY/ADD source is missing: {source}")

    # De-duplicate while preserving order for readable logs.
    return list(dict.fromkeys(issues))


async def get_generic_template_pipeline() -> Optional[str]:
    """Return the generic GitLab stage reference from ChromaDB."""
    try:
        chromadb = _get_chromadb()
        results = await chromadb.get_documents(
            collection_name=GENERIC_TEMPLATE_COLLECTION,
            limit=1,
            include=["documents", "metadatas"],
        )
        await chromadb.close()

        if not results or not results.get('documents'):
            return None

        doc = results['documents'][0] or ""
        if '### .gitlab-ci.yml' in doc and '```yaml' in doc:
            start = doc.find('```yaml', doc.find('### .gitlab-ci.yml')) + 7
            end = doc.find('```', start)
            if start > 7 and end > start:
                return doc[start:end].strip()

        if doc.strip().startswith('stages:'):
            return doc.strip()

        return None
    except Exception as e:
        print(f"[GenericTemplate] Error getting generic template: {e}")
        return None


async def get_any_successful_pipeline() -> tuple:
    """
    Get ANY successful pipeline from ChromaDB regardless of language.
    Picks the one with the most stages (best coverage).
    Returns (yaml_content, source_language) or (None, None).
    """
    try:
        chromadb = _get_chromadb()
        results = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            limit=20,
            include=["documents", "metadatas"]
        )
        await chromadb.close()

        if not results or not results.get('ids'):
            return None, None

        # Pick the template with the most stages
        best_doc = None
        best_lang = None
        best_stages = 0
        for i, doc in enumerate(results.get('documents', [])):
            meta = results.get('metadatas', [{}])[i] if i < len(results.get('metadatas', [])) else {}
            stages = meta.get('stages_count', 0)
            if stages > best_stages:
                best_stages = stages
                best_doc = doc
                best_lang = meta.get('language', 'unknown')

        if not best_doc:
            return None, None

        # Extract yaml content
        if '### .gitlab-ci.yml' in best_doc and '```yaml' in best_doc:
            start = best_doc.find('```yaml', best_doc.find('### .gitlab-ci.yml')) + 7
            end = best_doc.find('```', start)
            if start > 7 and end > start:
                return best_doc[start:end].strip(), best_lang

        return None, None

    except Exception as e:
        print(f"[RL-CrossLang] Error getting cross-language pipeline: {e}")
        return None, None


async def get_best_pipeline_config(
    language: str,
    framework: str = "",
    analysis: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Get the best performing pipeline configuration for a language/framework.
    Considers success rate and duration to pick the optimal config.

    This is used during pipeline generation to prefer proven configurations.

    Args:
        language: Programming language
        framework: Optional framework

    Returns:
        The best gitlab-ci.yml content, or None if no successful configs exist
    """
    try:
        successful: List[Dict[str, Any]] = []
        for lookup_framework in _candidate_template_frameworks(language, framework, analysis):
            successful = await get_successful_pipelines(
                language,
                lookup_framework,
                limit=10,
            )
            if successful:
                if lookup_framework != str(framework or "").lower():
                    print(
                        f"[RL] No exact {language}/{framework} reference; "
                        f"using build-tool compatible {language}/{lookup_framework}"
                    )
                break

        if not successful:
            print(f"[RL] No successful pipelines found for {language}/{framework}")
            return None

        # Sort by stages count (more is better) and duration (less is better)
        # This prioritizes configs that pass all stages quickly
        sorted_configs = sorted(
            successful,
            key=lambda x: (-x.get('stages_count', 0), x.get('duration', float('inf')))
        )

        for best in sorted_configs:
            sections = _extract_template_sections(best.get('document', ''))
            if 'gitlab_ci' not in sections:
                continue

            issues = validate_reusable_template(
                sections,
                analysis,
                metadata=best,
            )
            if issues:
                print(
                    f"[RL] Skipping incompatible reference {best.get('id')} "
                    f"for {language}/{framework or 'any'}: {issues}"
                )
                continue

            print(f"[RL] Using best config: pipeline {best.get('pipeline_id')} with {best.get('stages_count')} stages in {best.get('duration')}s")
            return sections['gitlab_ci']

        return None

    except Exception as e:
        print(f"[RL] Error getting best pipeline config: {e}")
        return None


def _template_priority(doc_id: str) -> int:
    """Ranking key for retrieval. Lower = better.

    Order:
      0 - success_*       (passed a real GitLab pipeline run)
      1 - manual_*        (operator-uploaded, fallback only)
      2 - dry_validated_* (passed dry-run + LLM-fixer loop, never run for real)
      3 - everything else
    """
    if doc_id.startswith('success_'):
        return 0
    if doc_id.startswith('manual_'):
        return 1
    if doc_id.startswith('dry_validated_'):
        return 2
    return 3


async def get_best_template_files(
    language: str,
    framework: str = "",
    analysis: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, str]]:
    """
    Get the best performing pipeline template with BOTH gitlab-ci and dockerfile.
    This is used for DIRECT template usage without LLM modification.

    Args:
        language: Programming language
        framework: Optional framework

    Returns:
        Dict with 'gitlab_ci' and 'dockerfile' keys, or None if no template exists
    """
    try:
        successful: List[Dict[str, Any]] = []
        selected_lookup_framework = str(framework or "").lower()
        for lookup_framework in _candidate_template_frameworks(language, framework, analysis):
            successful = await get_successful_pipelines(
                language,
                lookup_framework,
                limit=10,
                allow_language_fallback=False,
            )
            if successful:
                selected_lookup_framework = lookup_framework
                if lookup_framework != str(framework or "").lower():
                    print(
                        f"[RL-Direct] No exact {language}/{framework} template; "
                        f"checking build-tool compatible {language}/{lookup_framework}"
                    )
                break

        if not successful:
            print(f"[RL-Direct] No templates found for {language}/{framework}")
            return None

        # Rank: manual_ > success_ > dry_validated_ > other; then by
        # stages_count desc; then by duration asc. dry_validated_* are
        # written by the LLM-fixer loop after a successful dry-run pass,
        # so they're trusted enough for direct reuse but rank below
        # templates proven by an actual GitLab run.
        sorted_configs = sorted(
            successful,
            key=lambda x: (
                _template_priority(x.get('id', '')),
                -x.get('stages_count', 0),
                x.get('duration', float('inf'))
            )
        )

        for best in sorted_configs:
            print(f"[RL-Direct] Evaluating template: {best.get('id')} with {best.get('stages_count')} stages")

            result = _extract_template_sections(best.get('document', ''))
            if 'gitlab_ci' in result:
                result['gitlab_ci'] = _ensure_learn_stage(result['gitlab_ci'])
                print(f"[RL-Direct] Extracted gitlab-ci: {len(result['gitlab_ci'])} chars")
            if 'dockerfile' in result:
                print(f"[RL-Direct] Extracted dockerfile: {len(result['dockerfile'])} chars")

            if 'gitlab_ci' not in result:
                continue

            issues = validate_reusable_template(
                result,
                analysis,
                metadata=best,
            )
            if issues:
                print(
                    f"[RL-Direct] Template {best.get('id')} is not usable for "
                    f"this repo; skipping RAG direct hit. Issues: {issues}"
                )
                continue

            result['template_id'] = best.get('id', '')
            result['template_framework'] = selected_lookup_framework
            return result

        return None

    except Exception as e:
        print(f"[RL-Direct] Error getting template files: {e}")
        return None


async def _store_validated_template(
    gitlab_ci: str,
    dockerfile: str,
    language: str,
    framework: str
) -> bool:
    """Store a validated template in ChromaDB for future use."""
    try:
        chromadb = _get_chromadb()

        # Ensure collection exists
        try:
            collection = await chromadb.get_collection(TEMPLATES_COLLECTION)
            if not collection:
                await chromadb.create_collection(
                    TEMPLATES_COLLECTION,
                    metadata={"description": "Validated pipeline templates"}
                )
        except Exception:
            pass  # Collection might already exist

        # Generate unique ID
        content_hash = hashlib.md5(
            f"{gitlab_ci}{language}{framework}".encode()
        ).hexdigest()[:12]
        doc_id = f"validated_{language}_{framework}_{content_hash}"

        # Create combined document
        template_doc = f"""## Validated Pipeline Template
Language: {language}
Framework: {framework}
Type: gitlab-ci
Validated: true

### .gitlab-ci.yml
```yaml
{gitlab_ci}
```

### Dockerfile
```dockerfile
{dockerfile}
```
"""

        metadata = {
            "language": language.lower(),
            "framework": framework.lower(),
            "type": "gitlab-ci",
            "validated": "true",
            "timestamp": datetime.now().isoformat()
        }

        # Check if exists
        existing = await chromadb.get_documents(
            collection_name=TEMPLATES_COLLECTION,
            ids=[doc_id]
        )

        if existing and existing.get('ids'):
            # Update existing
            await chromadb.update_documents(
                collection_name=TEMPLATES_COLLECTION,
                ids=[doc_id],
                documents=[template_doc],
                metadatas=[metadata]
            )
            print(f"[ChromaDB] Updated validated template for {language}/{framework}")
        else:
            # Add new
            await chromadb.add_documents(
                collection_name=TEMPLATES_COLLECTION,
                ids=[doc_id],
                documents=[template_doc],
                metadatas=[metadata]
            )
            print(f"[ChromaDB] Stored new validated template for {language}/{framework}")

        await chromadb.close()
        return True

    except Exception as e:
        print(f"[ChromaDB] Error storing validated template: {e}")
        return False


async def _store_dry_validated_template(
    gitlab_ci: str,
    dockerfile: str,
    language: str,
    framework: str,
    fix_attempts: int = 1,
    fixer_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a pipeline that passed the dry-run + LLM-fixer loop into the
    SUCCESSFUL_PIPELINES_COLLECTION so subsequent requests hit it via the
    Priority-1 RAG short-circuit (``get_best_template_files``).

    The id prefix ``dry_validated_`` distinguishes it from
    ``manual_`` (operator upload) and ``success_`` (real GitLab run) for
    ranking purposes (see ``_template_priority``).

    Returns ``{ok, doc_id, action: 'created'|'updated'}`` (or ``{ok: False, error}``).
    """
    try:
        chromadb = _get_chromadb()
        try:
            await chromadb.create_collection(SUCCESSFUL_PIPELINES_COLLECTION)
        except Exception:
            # Collection likely already exists — fine.
            pass

        stages_count = gitlab_ci.count("stage:") if gitlab_ci else 0
        content_hash = hashlib.md5(
            f"{gitlab_ci}{language}{framework}".encode()
        ).hexdigest()[:12]
        doc_id = f"dry_validated_{language.lower()}_{framework.lower()}_{content_hash}"

        doc = f"""## Dry-Run Validated Pipeline (RAG-cached)
Language: {language}
Framework: {framework}
Source: dry_validated_llm_fixer
Fix attempts: {fix_attempts}
Fixer model: {fixer_model or 'unknown'}

### .gitlab-ci.yml
```yaml
{gitlab_ci}
```

### Dockerfile
```dockerfile
{dockerfile}
```
"""
        metadata = {
            "language": language.lower(),
            "framework": framework.lower(),
            "source": "dry_validated",
            "stages_count": stages_count,
            "duration": 0,  # Never executed in GitLab; only dry-run validated
            "pipeline_id": "dry_validated",
            "fix_attempts": fix_attempts,
            "fixer_model": fixer_model or "unknown",
            "validated": "true",
            "timestamp": datetime.now().isoformat(),
        }

        existing = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            ids=[doc_id],
        )

        if existing and existing.get('ids'):
            await chromadb.update_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[doc],
                metadatas=[metadata],
            )
            action = "updated"
            print(f"[RAG-Persist] Updated dry-validated template {doc_id}")
        else:
            await chromadb.add_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[doc],
                metadatas=[metadata],
            )
            action = "created"
            print(f"[RAG-Persist] Stored dry-validated template {doc_id}")

        await chromadb.close()
        return {"ok": True, "doc_id": doc_id, "action": action}

    except Exception as e:
        print(f"[RAG-Persist] Error storing dry-validated template: {e}")
        return {"ok": False, "error": str(e)}


async def store_manual_template(
    language: str,
    framework: str,
    gitlab_ci: str,
    dockerfile: Optional[str] = None,
    description: Optional[str] = None
) -> bool:
    """
    Manually store a pipeline configuration as a proven template.
    Used to seed the RL database with known working configurations.

    Args:
        language: Programming language (e.g., 'java', 'go', 'python')
        framework: Framework name (e.g., 'maven', 'spring', 'generic')
        gitlab_ci: The .gitlab-ci.yml content
        dockerfile: Optional Dockerfile content
        description: Optional description of the template

    Returns:
        True if stored successfully, False otherwise
    """
    try:
        chromadb = _get_chromadb()
        await chromadb.create_collection(SUCCESSFUL_PIPELINES_COLLECTION)

        # Count stages in the pipeline
        stages_count = gitlab_ci.count("stage:") if gitlab_ci else 0

        # Build document
        dockerfile_section = f"\n### Dockerfile\n```dockerfile\n{dockerfile}\n```" if dockerfile else ""
        desc_section = f"\nDescription: {description}" if description else ""

        success_doc = f"""## Manual Pipeline Template
Language: {language}
Framework: {framework}{desc_section}
Source: manual_upload

### .gitlab-ci.yml
```yaml
{gitlab_ci}
```{dockerfile_section}
"""

        # Generate unique ID
        from datetime import datetime
        import hashlib
        content_hash = hashlib.md5(gitlab_ci.encode()).hexdigest()[:12]
        doc_id = f"manual_{language.lower()}_{framework.lower()}_{content_hash}"

        metadata = {
            "language": language.lower(),
            "framework": framework.lower(),
            "source": "manual_upload",
            "stages_count": stages_count,
            "duration": 0,  # Unknown for manual templates
            "pipeline_id": "manual",
            "timestamp": datetime.now().isoformat()
        }

        # Check if already exists
        existing = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            ids=[doc_id]
        )

        if existing and existing.get('ids'):
            print(f"[RL] Updating existing manual template for {language}/{framework}")
            await chromadb.update_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata]
            )
        else:
            print(f"[RL] Storing new manual template for {language}/{framework}")
            await chromadb.add_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata]
            )

        await chromadb.close()
        print(f"[RL] Successfully stored manual template for {language}/{framework}")
        return True

    except Exception as e:
        print(f"[RL] Error storing manual template: {e}")
        import traceback
        traceback.print_exc()
        return False


async def store_successful_pipeline(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    pipeline_id: int,
    gitlab_ci_content: str,
    dockerfile_content: str,
    language: str,
    framework: str,
    duration: Optional[int] = None,
    stages_passed: Optional[List[str]] = None,
    build_tool: str = "",
    language_version: str = "",
) -> bool:
    """
    Store a successful pipeline configuration in ChromaDB for reinforcement learning.
    This data is used to improve future pipeline generation decisions.

    Args:
        repo_url: GitLab repository URL
        gitlab_token: GitLab access token
        branch: Branch name where pipeline ran
        pipeline_id: GitLab pipeline ID
        gitlab_ci_content: The .gitlab-ci.yml content that succeeded
        dockerfile_content: The Dockerfile content that succeeded
        language: Programming language
        framework: Framework used
        duration: Pipeline duration in seconds
        stages_passed: List of stage names that passed
    """
    try:
        chromadb = _get_chromadb()

        # Ensure collection exists (handle race conditions gracefully)
        try:
            collection = await chromadb.get_collection(SUCCESSFUL_PIPELINES_COLLECTION)
            if not collection:
                await chromadb.create_collection(
                    SUCCESSFUL_PIPELINES_COLLECTION,
                    metadata={"description": "Successful pipeline configurations for reinforcement learning"}
                )
        except Exception as coll_err:
            # Collection might already exist (409) - that's fine
            if "409" not in str(coll_err) and "conflict" not in str(coll_err).lower():
                print(f"[RL] Collection check warning: {coll_err}")

        language_key = language.lower()
        framework_key = framework.lower()
        template_hash = _template_fingerprint(gitlab_ci_content, dockerfile_content)

        # Generate deterministic ID from the exact reusable template content.
        # Pipeline id, duration, branch, and timestamp are intentionally not
        # part of this normalized hash; a rerun of the same logical template
        # must not create or update another Chroma record.
        content_hash = template_hash[:12]
        doc_id = f"success_{language_key}_{framework_key}_{content_hash}"

        # Create document combining gitlab-ci and dockerfile
        success_doc = f"""## Successful Pipeline Configuration
Language: {language}
Framework: {framework}
Pipeline ID: {pipeline_id}
Duration: {duration or 'N/A'} seconds
Stages Passed: {', '.join(stages_passed) if stages_passed else 'all'}

### .gitlab-ci.yml
```yaml
{gitlab_ci_content}
```

### Dockerfile
```dockerfile
{dockerfile_content}
```
"""

        # Metadata for filtering
        metadata = {
            "language": language_key,
            "framework": framework_key,
            "build_tool": build_tool.lower() if build_tool else "",
            "language_version": _normalize_language_version(language_version, language_key),
            "java_version": _normalize_major_version(language_version) if language_key == "java" else "",
            "output_mode": "docker-image" if dockerfile_content.strip() else "direct-artifact",
            "pipeline_id": str(pipeline_id),
            "duration": duration or 0,
            "stages_count": len(stages_passed) if stages_passed else 8,
            "success": "true",
            "template_hash": template_hash,
            "timestamp": datetime.now().isoformat(),
            "repo_url": repo_url,
            "branch": branch
        }

        storage_analysis = {
            "language": language_key,
            "framework": framework_key,
            "build_tool": build_tool.lower() if build_tool else "",
            "package_manager": build_tool.lower() if build_tool else "",
            "language_version": _normalize_language_version(language_version, language_key),
            "java_version": _normalize_major_version(language_version) if language_key == "java" else "",
            "output_mode": "docker-image" if dockerfile_content.strip() else "direct-artifact",
        }
        reusable_issues = validate_reusable_template(
            {
                "gitlab_ci": gitlab_ci_content,
                "dockerfile": dockerfile_content,
            },
            storage_analysis,
            metadata=metadata,
        )
        if reusable_issues:
            print(
                f"[RL] Pipeline {pipeline_id} passed GitLab but is not reusable: "
                f"{reusable_issues}. NOT saving to RAG."
            )
            await chromadb.close()
            return False

        existing_for_stack = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            where={
                "$and": [
                    {"language": language_key},
                    {"framework": framework_key},
                ]
            },
            limit=100,
        )
        existing_ids = existing_for_stack.get("ids") or []
        existing_docs = existing_for_stack.get("documents") or []
        existing_metadatas = existing_for_stack.get("metadatas") or []
        for index, existing_doc in enumerate(existing_docs):
            existing_id = existing_ids[index] if index < len(existing_ids) else "unknown"
            existing_metadata = existing_metadatas[index] if index < len(existing_metadatas) else {}
            if existing_metadata.get("template_hash") == template_hash:
                print(f"[RL] Exact successful template already exists as {existing_id}; skipping duplicate save")
                await chromadb.close()
                return False

            sections = _extract_template_sections(existing_doc or "")
            if (
                sections.get("gitlab_ci", "").strip() == gitlab_ci_content.strip()
                and sections.get("dockerfile", "").strip() == dockerfile_content.strip()
            ):
                print(f"[RL] Exact successful template already exists as {existing_id}; skipping duplicate save")
                await chromadb.close()
                return False

        # Check if we already have this exact configuration
        existing = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            ids=[doc_id]
        )

        if existing and existing.get('ids'):
            print(f"[RL] Exact successful template already exists as {doc_id}; skipping duplicate save")
            await chromadb.close()
            return False
        else:
            # Add new record
            print(f"[RL] Storing new successful pipeline for {language}/{framework}")
            await chromadb.add_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata]
            )

        await chromadb.close()
        print(f"[RL] Successfully stored pipeline {pipeline_id} for {language}/{framework}")
        return True

    except Exception as e:
        print(f"[RL] Error storing successful pipeline: {e}")
        return False


async def mark_successful_template_failed(
    template_id: str,
    reason: str,
    pipeline_id: Optional[int] = None,
) -> bool:
    """Mark a previously successful template unusable after a direct-RAG miss.

    The document is kept for auditability, but future retrieval skips it. This
    prevents the same stale cached template from being selected again while a
    self-healed successor is being learned.
    """
    if not template_id:
        return False

    try:
        chromadb = _get_chromadb()
        existing = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            ids=[template_id],
            include=["documents", "metadatas"],
        )

        ids = existing.get("ids") or []
        documents = existing.get("documents") or []
        metadatas = existing.get("metadatas") or []
        if not ids or not documents:
            await chromadb.close()
            return False

        metadata = dict(metadatas[0] if metadatas else {})
        metadata.update({
            "success": "false",
            "invalidated": "true",
            "invalidated_reason": (reason or "direct RAG run failed")[:500],
            "invalidated_at": datetime.now().isoformat(),
        })
        if pipeline_id:
            metadata["failed_pipeline_id"] = str(pipeline_id)

        updated = await chromadb.update_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            ids=[template_id],
            documents=[documents[0]],
            metadatas=[metadata],
        )
        await chromadb.close()
        if updated:
            print(f"[RL] Marked template {template_id} unusable: {reason}")
        return updated
    except Exception as e:
        print(f"[RL] Error marking template {template_id} unusable: {e}")
        return False


async def get_successful_pipelines(
    language: str,
    framework: str = "",
    limit: int = 5,
    allow_language_fallback: bool = True,
) -> List[Dict[str, Any]]:
    """
    Retrieve successful pipeline configurations for a given language/framework.
    Used during pipeline generation to learn from past successes.

    Args:
        language: Programming language to filter by
        framework: Optional framework to filter by
        limit: Maximum number of results to return

    Returns:
        List of successful pipeline configurations with metadata
    """
    try:
        chromadb = _get_chromadb()

        # Build filter - try exact language+framework first
        if framework:
            where_filter = {
                "$and": [
                    {"language": language.lower()},
                    {"framework": framework.lower()}
                ]
            }
        else:
            where_filter = {"language": language.lower()}

        fetch_limit = max(limit, 50)
        results = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            where=where_filter,
            limit=fetch_limit,
            include=["documents", "metadatas"]
        )

        # Fallback: if exact framework match returned nothing, try language-only.
        # Direct RAG reuse disables this because a language-only template can be
        # useful as LLM reference material while still being unsafe to run as-is.
        if allow_language_fallback and framework and (not results or not results.get('ids')):
            print(f"[RL] No exact match for {language}/{framework}, trying language-only...")
            results = await chromadb.get_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                where={"language": language.lower()},
                limit=fetch_limit,
                include=["documents", "metadatas"]
            )

        await chromadb.close()

        if not results or not results.get('ids'):
            return []

        # Format results
        successful_configs = []
        for i, doc in enumerate(results.get('documents', [])):
            doc_id = results['ids'][i]
            if not doc_id.startswith("success_"):
                print(f"[RL] Skipping unproven template record {doc_id}; only real GitLab success_* records are reusable")
                continue

            metadata = results.get('metadatas', [{}])[i] if i < len(results.get('metadatas', [])) else {}
            if (
                str(metadata.get("invalidated", "")).lower() == "true"
                or str(metadata.get("success", "true")).lower() == "false"
            ):
                print(f"[RL] Skipping invalidated successful template record {doc_id}")
                continue
            successful_configs.append({
                "id": doc_id,
                "document": doc,
                "language": metadata.get('language', ''),
                "framework": metadata.get('framework', ''),
                "build_tool": metadata.get('build_tool', ''),
                "language_version": metadata.get('language_version', ''),
                "java_version": metadata.get('java_version', ''),
                "template_hash": metadata.get('template_hash', ''),
                "pipeline_id": metadata.get('pipeline_id', ''),
                "duration": metadata.get('duration', 0),
                "timestamp": metadata.get('timestamp', ''),
                "stages_count": metadata.get('stages_count', 0)
            })
            if len(successful_configs) >= limit:
                break

        print(f"[RL] Found {len(successful_configs)} successful pipelines for {language}/{framework or 'any'}")
        return successful_configs

    except Exception as e:
        print(f"[RL] Error getting successful pipelines: {e}")
        return []
