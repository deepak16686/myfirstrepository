"""
File: templates.py
Purpose: Manages pipeline template storage and retrieval in ChromaDB. Provides CRUD operations
    for proven pipeline templates (from successful RL runs), manually uploaded templates, and
    validated templates. Implements the priority-based template lookup (exact language match,
    cross-language fallback, built-in default).
When Used: Called during pipeline generation to find the best existing template before invoking
    the LLM, after successful pipeline runs to store proven configurations, and by the manual
    template upload API endpoint for seeding the RL database with known-good configurations.
Why Created: Extracted from the monolithic pipeline_generator.py to consolidate all ChromaDB
    template CRUD operations into a single module, separating data persistence from the
    generation orchestration and validation logic.
"""
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config import tools_manager
from app.integrations.chromadb import ChromaDBIntegration

from .constants import (
    TEMPLATES_COLLECTION,
    SUCCESSFUL_PIPELINES_COLLECTION,
)
from .validator import _ensure_learn_stage
from .default_templates import _get_default_gitlab_ci


def _get_chromadb() -> ChromaDBIntegration:
    chromadb_config = tools_manager.get_tool("chromadb")
    return ChromaDBIntegration(chromadb_config)


async def get_reference_pipeline(language: str, framework: str, build_tool: str = "") -> tuple:
    """
    Get reference pipeline from RL successful pipelines or built-in defaults.
    Returns (template_yaml, source_language) tuple.

    PRIORITY ORDER:
    1. Best successful pipeline from RL for this language+build_tool (proven)
    2. ANY successful pipeline from RL (cross-language, proven)
    3. Built-in default template for the language (hardcoded fallback)

    NOTE: We intentionally skip the pipeline_templates collection because it
    contains templates that only passed dry-run (YAML lint) but may have failed
    in actual GitLab execution. Only successful_pipelines (stored by the learn
    stage after real pipeline success) are trustworthy.
    """
    try:
        # PRIORITY 1: Check for successful pipelines for this language
        print(f"[RL] Checking for successful pipelines for {language}/{framework}...")
        best_config = await get_best_pipeline_config(language, framework, build_tool)
        if best_config:
            print(f"[RL] Using proven successful pipeline config ({len(best_config)} chars)")
            return _ensure_learn_stage(best_config), language

        # PRIORITY 2: Cross-language — get ANY successful pipeline from RL
        print(f"[RL] No proven pipeline for {language}, trying cross-language fallback...")
        cross_lang_config, cross_lang = await get_any_successful_pipeline()
        if cross_lang_config:
            print(f"[RL-CrossLang] Using proven {cross_lang} pipeline as reference for {language}")
            return _ensure_learn_stage(cross_lang_config), cross_lang

        # PRIORITY 3: Use built-in default template
        print(f"[RL] No proven pipelines in RL at all, using built-in default")
        default_template = _get_default_gitlab_ci({"language": language, "framework": framework})
        if default_template:
            print(f"[Default] Using built-in {language} template ({len(default_template)} chars)")
            return _ensure_learn_stage(default_template), language
        return None, None

    except Exception as e:
        print(f"[RL] Error getting reference pipeline: {e}")
        print(f"[Default] Falling back to built-in {language} template")
        default = _get_default_gitlab_ci({"language": language, "framework": framework})
        return (_ensure_learn_stage(default), language) if default else (None, None)


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
    build_tool: str = ""
) -> Optional[str]:
    """
    Get the best performing pipeline configuration for a language/framework.
    Considers success rate and duration to pick the optimal config.

    This is used during pipeline generation to prefer proven configurations.

    Args:
        language: Programming language
        framework: Optional framework
        build_tool: Optional build tool (maven, gradle, etc.) for more precise matching

    Returns:
        The best gitlab-ci.yml content, or None if no successful configs exist
    """
    try:
        successful = await get_successful_pipelines(language, framework, build_tool=build_tool, limit=10)

        if not successful:
            print(f"[RL] No successful pipelines found for {language}/{framework}")
            return None

        # Sort by stages count (more is better) and duration (less is better)
        # This prioritizes configs that pass all stages quickly
        sorted_configs = sorted(
            successful,
            key=lambda x: (-x.get('stages_count', 0), x.get('duration', float('inf')))
        )

        best = sorted_configs[0]
        print(f"[RL] Using best config: pipeline {best.get('pipeline_id')} with {best.get('stages_count')} stages in {best.get('duration')}s")

        # Extract gitlab-ci content from the document
        doc = best.get('document', '')
        if '### .gitlab-ci.yml' in doc and '```yaml' in doc:
            # Extract yaml content between markers
            start = doc.find('```yaml', doc.find('### .gitlab-ci.yml')) + 7
            end = doc.find('```', start)
            if start > 7 and end > start:
                return doc[start:end].strip()

        return None

    except Exception as e:
        print(f"[RL] Error getting best pipeline config: {e}")
        return None


async def get_best_template_files(
    language: str,
    framework: str = "",
    build_tool: str = ""
) -> Optional[Dict[str, str]]:
    """
    Get the best performing pipeline template with BOTH gitlab-ci and dockerfile.
    This is used for DIRECT template usage without LLM modification.

    Args:
        language: Programming language
        framework: Optional framework
        build_tool: Optional build tool (maven, gradle, etc.) for precise matching

    Returns:
        Dict with 'gitlab_ci' and 'dockerfile' keys, or None if no template exists
    """
    try:
        successful = await get_successful_pipelines(language, framework, build_tool=build_tool, limit=10)

        if not successful:
            print(f"[RL-Direct] No templates found for {language}/{framework}")
            return None

        # Sort by stages count (more is better) and duration (less is better)
        # Prioritize manual_upload source (verified working configs)
        sorted_configs = sorted(
            successful,
            key=lambda x: (
                -1 if x.get('id', '').startswith('manual_') else 0,  # Manual templates first
                -x.get('stages_count', 0),
                x.get('duration', float('inf'))
            )
        )

        best = sorted_configs[0]
        print(f"[RL-Direct] Using template: {best.get('id')} with {best.get('stages_count')} stages")

        doc = best.get('document', '')
        result = {}

        # Extract gitlab-ci content
        if '### .gitlab-ci.yml' in doc and '```yaml' in doc:
            start = doc.find('```yaml', doc.find('### .gitlab-ci.yml')) + 7
            end = doc.find('```', start)
            if start > 7 and end > start:
                gitlab_ci = doc[start:end].strip()
                # Ensure learn stage is present
                result['gitlab_ci'] = _ensure_learn_stage(gitlab_ci)
                print(f"[RL-Direct] Extracted gitlab-ci: {len(result['gitlab_ci'])} chars")

        # Extract dockerfile content
        if '### Dockerfile' in doc and '```dockerfile' in doc:
            start = doc.find('```dockerfile', doc.find('### Dockerfile')) + 13
            end = doc.find('```', start)
            if start > 13 and end > start:
                result['dockerfile'] = doc[start:end].strip()
                print(f"[RL-Direct] Extracted dockerfile: {len(result['dockerfile'])} chars")

        # Only return if we have at least gitlab-ci
        if 'gitlab_ci' in result:
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


async def store_manual_template(
    language: str,
    framework: str,
    gitlab_ci: str,
    dockerfile: Optional[str] = None,
    description: Optional[str] = None,
    build_tool: str = ""
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
        build_tool: Optional build tool (maven, gradle, pip, etc.)

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
            "build_tool": build_tool.lower() if build_tool else "",
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
    build_tool: str = ""
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
        build_tool: Build tool used (maven, gradle, pip, etc.)
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

        # Generate unique ID
        content_hash = hashlib.md5(
            f"{gitlab_ci_content}{language}{framework}".encode()
        ).hexdigest()[:12]
        doc_id = f"success_{language}_{framework}_{content_hash}"

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
            "language": language.lower(),
            "framework": framework.lower(),
            "build_tool": build_tool.lower() if build_tool else "",
            "pipeline_id": str(pipeline_id),
            "duration": duration or 0,
            "stages_count": len(stages_passed) if stages_passed else 8,
            "success": "true",
            "timestamp": datetime.now().isoformat(),
            "repo_url": repo_url,
            "branch": branch
        }

        # Check if we already have this exact configuration
        existing = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            ids=[doc_id]
        )

        if existing and existing.get('ids'):
            # Update existing with new success count
            print(f"[RL] Updating existing successful pipeline record for {language}/{framework}")
            await chromadb.update_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata]
            )
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
    build_tool: str = "",
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Retrieve successful pipeline configurations for a given language/framework/build_tool.
    Used during pipeline generation to learn from past successes.

    Args:
        language: Programming language to filter by
        framework: Optional framework to filter by
        build_tool: Optional build tool (maven, gradle, etc.) for precise matching
        limit: Maximum number of results to return

    Returns:
        List of successful pipeline configurations with metadata
    """
    try:
        chromadb = _get_chromadb()

        # Build filter — try most specific match first, then broaden
        # Priority: language + build_tool > language + framework > language only
        conditions = [{"language": language.lower()}]
        if build_tool:
            conditions.append({"build_tool": build_tool.lower()})
        elif framework:
            conditions.append({"framework": framework.lower()})

        if len(conditions) > 1:
            where_filter = {"$and": conditions}
        else:
            where_filter = conditions[0]

        results = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            where=where_filter,
            limit=limit,
            include=["documents", "metadatas"]
        )

        # Fallback 1: if build_tool match returned nothing, try language + framework
        if build_tool and (not results or not results.get('ids')) and framework:
            print(f"[RL] No match for {language}/{build_tool}, trying {language}/{framework}...")
            results = await chromadb.get_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                where={"$and": [
                    {"language": language.lower()},
                    {"framework": framework.lower()}
                ]},
                limit=limit,
                include=["documents", "metadatas"]
            )

        # Fallback 2: if still nothing, try language-only
        if (build_tool or framework) and (not results or not results.get('ids')):
            print(f"[RL] No exact match for {language}/{framework or build_tool}, trying language-only...")
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
            metadata = results.get('metadatas', [{}])[i] if i < len(results.get('metadatas', [])) else {}
            successful_configs.append({
                "id": results['ids'][i],
                "document": doc,
                "language": metadata.get('language', ''),
                "framework": metadata.get('framework', ''),
                "build_tool": metadata.get('build_tool', ''),
                "pipeline_id": metadata.get('pipeline_id', ''),
                "duration": metadata.get('duration', 0),
                "timestamp": metadata.get('timestamp', ''),
                "stages_count": metadata.get('stages_count', 0)
            })

        print(f"[RL] Found {len(successful_configs)} successful pipelines for {language}/{framework or build_tool or 'any'}")
        return successful_configs

    except Exception as e:
        print(f"[RL] Error getting successful pipelines: {e}")
        return []
