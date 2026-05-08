"""
File: deep_analyzer.py
Purpose: Deep repository technology detection engine that parses build configuration files (pom.xml, build.gradle, go.mod, requirements.txt, package.json, Cargo.toml, Gemfile, .csproj, Dockerfile, Spring configs) to extract precise language versions, frameworks, build tools, dependencies, and appropriate Docker base images.
When Used: Called by all three pipeline analyzers (GitLab, Jenkins, GitHub Actions) after initial file-name-based language detection, to enrich the generation context with detailed dependency and tooling information.
Why Created: Centralizes deep repo analysis logic that was needed by multiple pipeline generators, avoiding duplication and ensuring consistent technology detection across GitLab CI, Jenkins, and GitHub Actions pipeline generation.
"""
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple


async def deep_analyze(
    language: str,
    framework: str,
    files: List[str],
    all_paths: List[str],
    read_file: Callable,
) -> Dict[str, Any]:
    """
    Perform deep content analysis on key config files.

    Args:
        language: Detected language from file-name analysis.
        framework: Detected framework from file-name analysis.
        files: Root-level file names.
        all_paths: All file paths (recursive tree).
        read_file: async callable(path) -> Optional[str] to read file content.

    Returns:
        Dict of enriched fields to merge into the analysis dict.
    """
    result: Dict[str, Any] = {}

    if language in ("java", "kotlin", "scala", "spring-boot", "quarkus"):
        if "pom.xml" in files:
            pom = await read_file("pom.xml")
            if pom:
                result.update(_parse_pom_xml(pom))
        if "build.gradle.kts" in files or "build.gradle" in files:
            fname = "build.gradle.kts" if "build.gradle.kts" in files else "build.gradle"
            gradle = await read_file(fname)
            if gradle:
                gradle_info = _parse_build_gradle(gradle)
                # pom.xml takes priority — only fill in missing fields
                for k, v in gradle_info.items():
                    if k not in result:
                        result[k] = v

    elif language == "go":
        if "go.mod" in files:
            go_mod = await read_file("go.mod")
            if go_mod:
                result.update(_parse_go_mod(go_mod))

    elif language == "python":
        if "requirements.txt" in files:
            reqs = await read_file("requirements.txt")
            if reqs:
                result.update(_parse_requirements_txt(reqs))
        if "pyproject.toml" in files:
            pyproject = await read_file("pyproject.toml")
            if pyproject:
                pyp_info = _parse_pyproject_toml(pyproject)
                for k, v in pyp_info.items():
                    if k not in result:
                        result[k] = v

    elif language in ("javascript", "typescript"):
        if "package.json" in files:
            pkg = await read_file("package.json")
            if pkg:
                result.update(_parse_package_json(pkg))

    elif language == "rust":
        if "Cargo.toml" in files:
            cargo = await read_file("Cargo.toml")
            if cargo:
                result.update(_parse_cargo_toml(cargo))

    elif language == "ruby":
        if "Gemfile" in files:
            gemfile = await read_file("Gemfile")
            if gemfile:
                result.update(_parse_gemfile(gemfile))

    elif language == "csharp":
        csproj = next((p for p in (all_paths or files) if p.endswith(".csproj")), None)
        if csproj:
            content = await read_file(csproj)
            if content:
                result.update(_parse_csproj(content))

    # Cross-language: parse existing Dockerfile
    if "Dockerfile" in files:
        df = await read_file("Dockerfile")
        if df:
            result["existing_dockerfile"] = _parse_dockerfile(df)

    # Spring config (if Spring Boot detected)
    detected_fw = result.get("framework") or framework
    if detected_fw in ("spring-boot", "spring"):
        for cfg in ("application.yml", "application.yaml", "application.properties"):
            # Check src/main/resources first, then root
            resource_path = f"src/main/resources/{cfg}"
            path = resource_path if resource_path in (all_paths or []) else (cfg if cfg in files else None)
            if path:
                content = await read_file(path)
                if content:
                    fmt = "yaml" if cfg.endswith((".yml", ".yaml")) else "properties"
                    result.update(_parse_spring_config(content, fmt))
                    break

    return result


# ---------------------------------------------------------------------------
# Java: pom.xml
# ---------------------------------------------------------------------------

def _parse_pom_xml(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"build_tool": "maven"}

    # Java version
    jv = _xml_tag(content, "java.version") or _xml_tag(content, "maven.compiler.source")
    if jv:
        result["java_version"] = jv.strip()

    # Spring Boot parent
    parent_block = re.search(r"<parent>(.*?)</parent>", content, re.DOTALL)
    if parent_block:
        parent = parent_block.group(1)
        if "spring-boot-starter-parent" in parent:
            result["framework"] = "spring-boot"
            sbv = _xml_tag(parent, "version")
            if sbv:
                result["spring_boot_version"] = sbv.strip()
                result["framework_version"] = sbv.strip()

    # Quarkus BOM
    if "quarkus-bom" in content or "quarkus-universe-bom" in content:
        result["framework"] = "quarkus"
        qv = re.search(r"quarkus[.-](?:universe-)?bom.*?<version>([^<]+)</version>", content, re.DOTALL)
        if qv:
            result["framework_version"] = qv.group(1).strip()

    # Micronaut BOM
    if "micronaut-bom" in content or "micronaut-platform" in content:
        result["framework"] = "micronaut"
        mv = re.search(r"micronaut[-.](?:bom|platform).*?<version>([^<]+)</version>", content, re.DOTALL)
        if mv:
            result["framework_version"] = mv.group(1).strip()

    # Packaging
    pkg = _xml_tag(content, "packaging")
    if pkg:
        result["packaging"] = pkg.strip().lower()

    # Spring Boot starters
    starters = re.findall(r"spring-boot-starter-(\w[\w-]*)", content)
    if starters:
        result["spring_starters"] = list(set(starters))

    # Dependency categories
    result["dependencies"] = _categorize_java_deps(content)

    return result


# ---------------------------------------------------------------------------
# Java: build.gradle / build.gradle.kts
# ---------------------------------------------------------------------------

def _parse_build_gradle(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"build_tool": "gradle"}

    # Java version
    jv = re.search(r"sourceCompatibility\s*=\s*['\"]?(\d[\d.]*)", content)
    if not jv:
        jv = re.search(r"JavaVersion\.VERSION_(\d+)", content)
    if not jv:
        jv = re.search(r"jvmToolchain\s*\(\s*(\d+)", content)
    if not jv:
        jv = re.search(r"languageVersion\.set\s*\(\s*JavaLanguageVersion\.of\s*\(\s*(\d+)", content)
    if jv:
        result["java_version"] = jv.group(1).replace("_", ".")

    # Spring Boot plugin
    if "org.springframework.boot" in content:
        result["framework"] = "spring-boot"
        sbv = re.search(r"org\.springframework\.boot['\"]?\s*version\s*['\"]([^'\"]+)", content)
        if sbv:
            result["spring_boot_version"] = sbv.group(1)
            result["framework_version"] = sbv.group(1)

    # Quarkus plugin
    if "io.quarkus" in content:
        result["framework"] = "quarkus"
        qv = re.search(r"io\.quarkus['\"]?\s*version\s*['\"]([^'\"]+)", content)
        if qv:
            result["framework_version"] = qv.group(1)

    # Kotlin
    if "org.jetbrains.kotlin" in content:
        kv = re.search(r"org\.jetbrains\.kotlin[.\w]*['\"]?\s*version\s*['\"]([^'\"]+)", content)
        if kv:
            result["kotlin_version"] = kv.group(1)

    return result


# ---------------------------------------------------------------------------
# Go: go.mod
# ---------------------------------------------------------------------------

def _parse_go_mod(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    gv = re.search(r"^go\s+(\d+\.\d+(?:\.\d+)?)", content, re.MULTILINE)
    if gv:
        result["go_version"] = gv.group(1)

    mod = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
    if mod:
        result["module_name"] = mod.group(1)

    # Detect Go web frameworks
    fw_map = {
        "github.com/gin-gonic/gin": "gin",
        "github.com/labstack/echo": "echo",
        "github.com/gofiber/fiber": "fiber",
        "github.com/gorilla/mux": "gorilla",
        "github.com/go-chi/chi": "chi",
        "github.com/beego/beego": "beego",
    }
    for dep, fw in fw_map.items():
        if dep in content:
            result["framework"] = fw
            break

    return result


# ---------------------------------------------------------------------------
# Python: requirements.txt
# ---------------------------------------------------------------------------

def _parse_requirements_txt(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    packages = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        pkg = re.split(r"[><=!~\[]", line)[0].strip().lower()
        if pkg:
            packages.append(pkg)

    result["python_deps"] = packages

    fw_map = {
        "fastapi": "fastapi",
        "flask": "flask",
        "django": "django",
        "streamlit": "streamlit",
        "celery": "celery",
        "tornado": "tornado",
        "sanic": "sanic",
        "bottle": "bottle",
    }
    for pkg_name, fw in fw_map.items():
        if pkg_name in packages:
            result["python_framework"] = fw
            result["framework"] = fw
            break

    return result


# ---------------------------------------------------------------------------
# Python: pyproject.toml (basic regex parsing, no toml lib required)
# ---------------------------------------------------------------------------

def _parse_pyproject_toml(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    # Python version requirement
    pv = re.search(r'requires-python\s*=\s*["\']([^"\']+)', content)
    if pv:
        result["python_version"] = pv.group(1)

    # Dependencies section
    deps_section = re.search(r'\[(?:project\.)?dependencies\](.*?)(?:\[|\Z)', content, re.DOTALL)
    if deps_section:
        deps_text = deps_section.group(1)
    else:
        deps_text = content

    fw_map = {"fastapi": "fastapi", "flask": "flask", "django": "django",
              "streamlit": "streamlit", "celery": "celery"}
    for pkg, fw in fw_map.items():
        if re.search(rf'["\']?{pkg}["\']?\s*[=><]', deps_text, re.IGNORECASE):
            result["python_framework"] = fw
            result["framework"] = fw
            break

    return result


# ---------------------------------------------------------------------------
# Node.js: package.json
# ---------------------------------------------------------------------------

def _parse_package_json(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    try:
        pkg = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return result

    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    # Has TypeScript?
    if "typescript" in deps:
        result["has_typescript"] = True

    # Node version from engines
    engines = pkg.get("engines", {})
    if engines.get("node"):
        result["node_version"] = engines["node"]

    # Framework detection
    fw_map = [
        ("next", "nextjs"),
        ("nuxt", "nuxt"),
        ("@nestjs/core", "nestjs"),
        ("express", "express"),
        ("fastify", "fastify"),
        ("koa", "koa"),
        ("hapi", "hapi"),
        ("@hapi/hapi", "hapi"),
    ]
    for dep, fw in fw_map:
        if dep in deps:
            result["node_framework"] = fw
            result["framework"] = fw
            break

    return result


# ---------------------------------------------------------------------------
# Rust: Cargo.toml
# ---------------------------------------------------------------------------

def _parse_cargo_toml(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    edition = re.search(r'edition\s*=\s*["\'](\d+)["\']', content)
    if edition:
        result["rust_edition"] = edition.group(1)

    fw_map = {
        "actix-web": "actix-web",
        "rocket": "rocket",
        "axum": "axum",
        "warp": "warp",
        "tide": "tide",
    }
    for dep, fw in fw_map.items():
        if re.search(rf'^{re.escape(dep)}\s*=', content, re.MULTILINE):
            result["rust_framework"] = fw
            result["framework"] = fw
            break

    return result


# ---------------------------------------------------------------------------
# Ruby: Gemfile
# ---------------------------------------------------------------------------

def _parse_gemfile(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    ruby_ver = re.search(r"ruby\s+['\"]([^'\"]+)", content)
    if ruby_ver:
        result["ruby_version"] = ruby_ver.group(1)

    if re.search(r"gem\s+['\"]rails['\"]", content):
        result["ruby_framework"] = "rails"
        result["framework"] = "rails"
    elif re.search(r"gem\s+['\"]sinatra['\"]", content):
        result["ruby_framework"] = "sinatra"
        result["framework"] = "sinatra"
    elif re.search(r"gem\s+['\"]hanami['\"]", content):
        result["ruby_framework"] = "hanami"
        result["framework"] = "hanami"

    return result


# ---------------------------------------------------------------------------
# C#: .csproj
# ---------------------------------------------------------------------------

def _parse_csproj(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    tfm = _xml_tag(content, "TargetFramework")
    if tfm:
        result["target_framework"] = tfm.strip()
        # Extract .NET version (e.g., net8.0 → 8.0)
        m = re.search(r"net(\d+\.\d+)", tfm)
        if m:
            result["dotnet_version"] = m.group(1)

    return result


# ---------------------------------------------------------------------------
# Dockerfile (existing)
# ---------------------------------------------------------------------------

def _parse_dockerfile(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    froms = re.findall(r"^FROM\s+(\S+)", content, re.MULTILINE)
    if froms:
        result["base_images"] = froms
        result["multi_stage"] = len(froms) > 1

    ports = re.findall(r"^EXPOSE\s+(\d+)", content, re.MULTILINE)
    if ports:
        result["exposed_ports"] = [int(p) for p in ports]

    cmd = re.search(r'^(?:CMD|ENTRYPOINT)\s+(.+)', content, re.MULTILINE)
    if cmd:
        result["entrypoint"] = cmd.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Spring application.yml / application.properties
# ---------------------------------------------------------------------------

def _parse_spring_config(content: str, fmt: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    if fmt == "properties":
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("server.port="):
                try:
                    result["server_port"] = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("spring.application.name="):
                result["application_name"] = line.split("=", 1)[1].strip()
            elif line.startswith("spring.profiles.active="):
                result["profiles"] = line.split("=", 1)[1].strip()
    else:
        # YAML — simple regex (no yaml lib to avoid dependency)
        port = re.search(r"server:\s*\n\s+port:\s*(\d+)", content)
        if port:
            try:
                result["server_port"] = int(port.group(1))
            except ValueError:
                pass

        app_name = re.search(r"spring:\s*\n(?:\s+.+\n)*?\s+application:\s*\n\s+name:\s*(\S+)", content)
        if not app_name:
            app_name = re.search(r"spring\.application\.name:\s*(\S+)", content)
        if app_name:
            result["application_name"] = app_name.group(1)

    return result


# ---------------------------------------------------------------------------
# Image resolution helper
# ---------------------------------------------------------------------------

def resolve_compile_image(analysis: Dict[str, Any]) -> Optional[str]:
    """Given enriched analysis, return the best compile image tag, or None to use the static map."""
    lang = analysis.get("language", "")

    if lang in ("java", "kotlin", "scala", "spring-boot", "quarkus"):
        java_ver = analysis.get("java_version", "17")
        # Normalize — "1.8" → "8", "11.0.2" → "11"
        java_ver = _normalize_java_version(java_ver)
        build_tool = analysis.get("build_tool", "maven")
        if build_tool == "gradle":
            return f"gradle:8.7-jdk{java_ver}-alpine"
        else:
            return f"maven:3.9-eclipse-temurin-{java_ver}"

    if lang in ("go", "golang"):
        go_ver = analysis.get("go_version")
        if go_ver:
            return f"golang:{go_ver}-alpine-git"

    return None


def resolve_runtime_image(analysis: Dict[str, Any]) -> Optional[str]:
    """Given enriched analysis, return the best runtime image tag, or None to use the static map."""
    lang = analysis.get("language", "")

    if lang in ("java", "kotlin", "scala", "spring-boot", "quarkus"):
        java_ver = analysis.get("java_version", "17")
        java_ver = _normalize_java_version(java_ver)
        return f"eclipse-temurin:{java_ver}-jre"

    return None


# ---------------------------------------------------------------------------
# Image resolution + Nexus pre-seeding
# ---------------------------------------------------------------------------

async def resolve_and_seed_images(analysis: Dict[str, Any]) -> None:
    """
    Resolve the best Docker images based on deep analysis, pre-seed them into
    Nexus if missing, and store the resolved tags in the analysis dict.

    This ensures that when a pipeline is generated using dynamically resolved
    images (e.g., maven:3.9-eclipse-temurin-21 for java_version=21), those
    images are already available in Nexus — never pulled from public repos
    at pipeline runtime.

    Mutates analysis dict in-place, adding:
      - resolved_compile_image: str (e.g., "maven:3.9-eclipse-temurin-21")
      - resolved_runtime_image: str (e.g., "eclipse-temurin:21-jre")
    """
    from app.services.pipeline.image_seeder import _check_image_exists, _seed_image

    images_to_seed = []

    compile_img = resolve_compile_image(analysis)
    if compile_img:
        analysis["resolved_compile_image"] = compile_img
        images_to_seed.append(compile_img)

    runtime_img = resolve_runtime_image(analysis)
    if runtime_img:
        analysis["resolved_runtime_image"] = runtime_img
        images_to_seed.append(runtime_img)

    # Pre-seed resolved images into Nexus (best-effort)
    for img in images_to_seed:
        try:
            exists = await _check_image_exists(img)
            if not exists:
                print(f"[DeepAnalyzer] Image '{img}' not in Nexus — seeding from DockerHub...")
                ok = await _seed_image(img)
                if ok:
                    print(f"[DeepAnalyzer] Seeded '{img}' to Nexus successfully")
                else:
                    print(f"[DeepAnalyzer] WARNING: Failed to seed '{img}' to Nexus")
            else:
                print(f"[DeepAnalyzer] Image '{img}' already in Nexus")
        except Exception as e:
            print(f"[DeepAnalyzer] Image seed error for '{img}': {e}")


# ---------------------------------------------------------------------------
# Prompt context builder
# ---------------------------------------------------------------------------

def build_deep_context(analysis: Dict[str, Any]) -> str:
    """Build a human-readable string of deep analysis findings for LLM prompts."""
    lines = []

    if analysis.get("java_version"):
        lines.append(f"- Java Version: {analysis['java_version']}")
    if analysis.get("spring_boot_version"):
        lines.append(f"- Spring Boot Version: {analysis['spring_boot_version']}")
    if analysis.get("framework_version") and not analysis.get("spring_boot_version"):
        lines.append(f"- Framework Version: {analysis['framework_version']}")
    if analysis.get("build_tool"):
        bt = analysis["build_tool"]
        if analysis.get("build_tool_version"):
            bt += f" {analysis['build_tool_version']}"
        lines.append(f"- Build Tool: {bt}")
    if analysis.get("packaging"):
        lines.append(f"- Packaging: {analysis['packaging']}")
    if analysis.get("spring_starters"):
        lines.append(f"- Spring Starters: {', '.join(analysis['spring_starters'])}")
    if analysis.get("go_version"):
        lines.append(f"- Go Version: {analysis['go_version']}")
    if analysis.get("module_name"):
        lines.append(f"- Go Module: {analysis['module_name']}")
    if analysis.get("python_framework"):
        lines.append(f"- Python Framework: {analysis['python_framework']}")
    if analysis.get("python_version"):
        lines.append(f"- Python Version Requirement: {analysis['python_version']}")
    if analysis.get("node_framework"):
        lines.append(f"- Node Framework: {analysis['node_framework']}")
    if analysis.get("node_version"):
        lines.append(f"- Node Version: {analysis['node_version']}")
    if analysis.get("has_typescript"):
        lines.append("- TypeScript: Yes")
    if analysis.get("rust_edition"):
        lines.append(f"- Rust Edition: {analysis['rust_edition']}")
    if analysis.get("rust_framework"):
        lines.append(f"- Rust Framework: {analysis['rust_framework']}")
    if analysis.get("ruby_version"):
        lines.append(f"- Ruby Version: {analysis['ruby_version']}")
    if analysis.get("ruby_framework"):
        lines.append(f"- Ruby Framework: {analysis['ruby_framework']}")
    if analysis.get("dotnet_version"):
        lines.append(f"- .NET Version: {analysis['dotnet_version']}")
    if analysis.get("kotlin_version"):
        lines.append(f"- Kotlin Version: {analysis['kotlin_version']}")
    if analysis.get("server_port"):
        lines.append(f"- Application Port: {analysis['server_port']}")
    if analysis.get("application_name"):
        lines.append(f"- Application Name: {analysis['application_name']}")

    deps = analysis.get("dependencies", {})
    if deps:
        for cat, val in deps.items():
            if val:
                lines.append(f"- {cat.title()}: {val if isinstance(val, str) else ', '.join(val)}")

    if analysis.get("existing_dockerfile"):
        edf = analysis["existing_dockerfile"]
        if edf.get("base_images"):
            lines.append(f"- Existing Dockerfile base: {', '.join(edf['base_images'])}")
        if edf.get("multi_stage"):
            lines.append("- Existing Dockerfile: multi-stage build")
        if edf.get("exposed_ports"):
            lines.append(f"- Existing Dockerfile EXPOSE: {edf['exposed_ports']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Template image rewriting
# ---------------------------------------------------------------------------

# All known Nexus registry prefix variants used across GitLab, GitHub, and Jenkins pipelines.
_REGISTRY_PREFIXES = [
    r'\$\{NEXUS_PULL_REGISTRY\}/apm-repo/demo/',      # GitLab CI
    r'\$\{BASE_REGISTRY\}/apm-repo/demo/',             # Dockerfile ARG
    r'\$\{\{\s*env\.NEXUS_REGISTRY\s*\}\}/apm-repo/demo/',  # GitHub Actions
    r'localhost:5001/apm-repo/demo/',                   # Hardcoded host
    r'ai-nexus:5001/apm-repo/demo/',                    # Hardcoded container
]
_PREFIX_PATTERN = '|'.join(_REGISTRY_PREFIXES)


def rewrite_template_images(
    ci_content: str,
    dockerfile: str,
    analysis: Dict[str, Any],
) -> Tuple[str, str, List[str]]:
    """
    Rewrite Docker image references in CI content and Dockerfile to match
    the project's resolved images from deep analysis.

    Does family-level matching: extracts the image name (the part before ':')
    from each resolved image and replaces ANY tag for that family with the
    resolved tag.  This handles templates from any previous version, not just
    hardcoded defaults.

    Examples:
      - maven:3.9-eclipse-temurin-17 → maven:3.9-eclipse-temurin-21
      - eclipse-temurin:17-jre → eclipse-temurin:21-jre
      - golang:1.21-alpine → golang:1.23-alpine-git

    Args:
        ci_content: CI YAML content (any format: .gitlab-ci.yml, ci.yml, Jenkinsfile)
        dockerfile: Dockerfile content
        analysis: Enriched analysis dict with resolved_compile_image / resolved_runtime_image

    Returns:
        (rewritten_ci, rewritten_dockerfile, list_of_corrections)
    """
    resolved_compile = analysis.get("resolved_compile_image")
    resolved_runtime = analysis.get("resolved_runtime_image")

    if not resolved_compile and not resolved_runtime:
        return ci_content, dockerfile, []

    # Build replacement pairs: (family_prefix, resolved_full_image)
    pairs: List[Tuple[str, str]] = []
    if resolved_compile:
        pairs.append((resolved_compile.split(":")[0], resolved_compile))
    if resolved_runtime:
        runtime_family = resolved_runtime.split(":")[0]
        # Only add runtime if it's a different family than compile
        compile_family = resolved_compile.split(":")[0] if resolved_compile else ""
        if runtime_family != compile_family:
            pairs.append((runtime_family, resolved_runtime))

    corrections: List[str] = []

    ci_content, ci_fixes = _apply_image_replacements(ci_content, pairs)
    corrections.extend(f"CI: {c}" for c in ci_fixes)

    dockerfile, df_fixes = _apply_image_replacements(dockerfile, pairs)
    corrections.extend(f"Dockerfile: {c}" for c in df_fixes)

    return ci_content, dockerfile, corrections


def _apply_image_replacements(
    content: str, pairs: List[Tuple[str, str]]
) -> Tuple[str, List[str]]:
    """
    Replace image references matching family prefixes with resolved images.

    Handles all known registry prefix variants (Nexus variable, hardcoded host,
    container name) as well as bare image references.
    """
    if not content:
        return content, []

    corrections: List[str] = []

    for family, resolved in pairs:
        # Pattern: (optional_registry_prefix)(family)(:tag)
        # Tag = everything up to whitespace, quote, or newline.
        pattern = re.compile(
            rf'((?:{_PREFIX_PATTERN})?)({re.escape(family)})(:[^\s"\'\n]+)'
        )

        def _replacer(match: re.Match, _resolved: str = resolved) -> str:
            prefix = match.group(1)
            old_image = match.group(2) + match.group(3)
            if old_image == _resolved:
                return match.group(0)  # Already correct
            # Preserve -node20 suffix: if old tag ends with -node20 but
            # the resolved image doesn't, append it.  These custom images
            # are required for Gitea Actions container jobs (actions/checkout
            # needs Node.js).
            effective = _resolved
            old_tag = match.group(3)  # e.g. ":3.9-eclipse-temurin-17-node20"
            if old_tag.endswith("-node20") and not _resolved.endswith("-node20"):
                effective = _resolved + "-node20"
            if old_image == effective:
                return match.group(0)  # Already correct after suffix
            corrections.append(f"Replaced {old_image} with {effective}")
            return prefix + effective

        content = pattern.sub(_replacer, content)

    return content, corrections


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _xml_tag(xml: str, tag: str) -> Optional[str]:
    """Extract text content of the first matching XML tag."""
    m = re.search(rf"<{re.escape(tag)}>([^<]+)</{re.escape(tag)}>", xml)
    return m.group(1) if m else None


def _normalize_java_version(ver: str) -> str:
    """Normalize Java version strings: '1.8' → '8', '11.0.2' → '11', '17' → '17'."""
    ver = ver.strip()
    if ver.startswith("1."):
        return ver[2:].split(".")[0]
    return ver.split(".")[0]


def _categorize_java_deps(pom_content: str) -> Dict[str, str]:
    """Categorize Java dependencies into functional groups."""
    cats: Dict[str, str] = {}

    dep_map = {
        "spring-boot-starter-data-jpa": ("database", "JPA"),
        "spring-boot-starter-data-mongodb": ("database", "MongoDB"),
        "spring-boot-starter-data-redis": ("cache", "Redis"),
        "spring-boot-starter-data-cassandra": ("database", "Cassandra"),
        "spring-boot-starter-security": ("security", "Spring Security"),
        "spring-boot-starter-oauth2": ("security", "OAuth2"),
        "spring-boot-starter-websocket": ("messaging", "WebSocket"),
        "spring-boot-starter-amqp": ("messaging", "RabbitMQ"),
        "spring-boot-starter-actuator": ("monitoring", "Actuator"),
        "mysql-connector": ("database", "MySQL"),
        "postgresql": ("database", "PostgreSQL"),
        "h2": ("database", "H2"),
        "flyway": ("database", "Flyway migrations"),
        "liquibase": ("database", "Liquibase migrations"),
        "kafka": ("messaging", "Kafka"),
        "elasticsearch": ("search", "Elasticsearch"),
        "lombok": ("tooling", "Lombok"),
    }

    for pattern, (cat, label) in dep_map.items():
        if pattern in pom_content:
            if cat in cats:
                cats[cat] += f", {label}"
            else:
                cats[cat] = label

    return cats
