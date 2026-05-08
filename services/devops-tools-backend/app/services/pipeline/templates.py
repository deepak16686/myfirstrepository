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
) -> List[str]:
    """
    Detect whether a cached template requires files the target repo lacks.

    RAG direct reuse must be conservative: if a proven template assumes a
    build system that is absent in the target repo, it is not a valid cache hit
    for this repo and the generator must continue into LLM/self-heal.
    """
    repo_paths = _analysis_repo_paths(analysis)
    if not repo_paths:
        return []

    gitlab_ci = template_files.get('gitlab_ci') or ''
    dockerfile = template_files.get('dockerfile') or ''
    combined = f"{gitlab_ci}\n{dockerfile}"

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

    issues: List[str] = []
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
        successful = await get_successful_pipelines(language, framework, limit=10)

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

            issues = template_compatibility_issues(sections, analysis)
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
        successful = await get_successful_pipelines(language, framework, limit=10)

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

            issues = template_compatibility_issues(result, analysis)
            if issues:
                print(
                    f"[RL-Direct] Template {best.get('id')} is not usable for "
                    f"this repo; skipping RAG direct hit. Issues: {issues}"
                )
                continue

            result['template_id'] = best.get('id', '')
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
    stages_passed: Optional[List[str]] = None
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
        template_payload = (
            f"{gitlab_ci_content.strip()}\n"
            "---DOCKERFILE---\n"
            f"{dockerfile_content.strip()}"
        )
        template_hash = hashlib.sha256(template_payload.encode()).hexdigest()

        # Generate deterministic ID from the exact reusable template content.
        # Pipeline id, duration, branch, and timestamp are intentionally not
        # part of this hash; a rerun of the same template must not create or
        # update another Chroma record.
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
            "pipeline_id": str(pipeline_id),
            "duration": duration or 0,
            "stages_count": len(stages_passed) if stages_passed else 8,
            "success": "true",
            "template_hash": template_hash,
            "timestamp": datetime.now().isoformat(),
            "repo_url": repo_url,
            "branch": branch
        }

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


async def get_successful_pipelines(
    language: str,
    framework: str = "",
    limit: int = 5
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

        results = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            where=where_filter,
            limit=limit,
            include=["documents", "metadatas"]
        )

        # Fallback: if exact framework match returned nothing, try language-only
        if framework and (not results or not results.get('ids')):
            print(f"[RL] No exact match for {language}/{framework}, trying language-only...")
            results = await chromadb.get_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                where={"language": language.lower()},
                limit=limit,
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
            successful_configs.append({
                "id": doc_id,
                "document": doc,
                "language": metadata.get('language', ''),
                "framework": metadata.get('framework', ''),
                "pipeline_id": metadata.get('pipeline_id', ''),
                "duration": metadata.get('duration', 0),
                "timestamp": metadata.get('timestamp', ''),
                "stages_count": metadata.get('stages_count', 0)
            })

        print(f"[RL] Found {len(successful_configs)} successful pipelines for {language}/{framework or 'any'}")
        return successful_configs

    except Exception as e:
        print(f"[RL] Error getting successful pipelines: {e}")
        return []
