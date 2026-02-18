"""
File: learning.py
Purpose: Implements the reinforcement learning feedback loop for GitLab pipelines. Stores
    and retrieves correction feedback in ChromaDB, records pipeline execution results (success
    or failure), and compares generated files against manually corrected versions to learn
    from human fixes.
When Used: The record_pipeline_result function is called by the learn_record stage inside
    every GitLab pipeline (via a curl POST to the backend) when a pipeline completes. The
    feedback functions are called during pipeline generation to retrieve past corrections,
    and after manual edits to store new correction patterns.
Why Created: Extracted from the monolithic pipeline_generator.py to isolate all ChromaDB
    feedback and reinforcement learning logic into a dedicated module, keeping the generator
    focused on prompt construction and the templates module focused on template CRUD.
"""
import hashlib
from typing import Dict, Any, List
from datetime import datetime

import httpx

from app.config import tools_manager
from app.integrations.chromadb import ChromaDBIntegration

from .constants import FEEDBACK_COLLECTION
from .analyzer import parse_gitlab_url, analyze_repository
from .templates import store_successful_pipeline


def _get_chromadb() -> ChromaDBIntegration:
    chromadb_config = tools_manager.get_tool("chromadb")
    return ChromaDBIntegration(chromadb_config)


async def get_relevant_feedback(language: str, framework: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieve relevant feedback from ChromaDB based on language and framework.
    This implements the reinforcement learning aspect.
    """
    try:
        chromadb = _get_chromadb()

        # Check if collection exists
        collection = await chromadb.get_collection(FEEDBACK_COLLECTION)
        if not collection:
            await chromadb.close()
            return []

        # Query for similar cases
        query_text = f"pipeline for {language} {framework} application"
        results = await chromadb.query(
            collection_id=FEEDBACK_COLLECTION,
            query_texts=[query_text],
            n_results=limit,
            include=["documents", "metadatas"]
        )

        await chromadb.close()

        feedback_list = []
        if results and results.get('documents'):
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results.get('metadatas') else {}
                feedback_list.append({
                    "feedback": doc,
                    "language": metadata.get('language'),
                    "framework": metadata.get('framework'),
                    "error_type": metadata.get('error_type'),
                    "fix_description": metadata.get('fix_description')
                })

        return feedback_list
    except Exception as e:
        print(f"Error getting feedback: {e}")
        return []


async def store_feedback(
    original_gitlab_ci: str,
    corrected_gitlab_ci: str,
    original_dockerfile: str,
    corrected_dockerfile: str,
    language: str,
    framework: str,
    error_type: str,
    fix_description: str
) -> bool:
    """
    Store feedback from manual corrections for reinforcement learning.
    """
    try:
        chromadb = _get_chromadb()

        # Ensure collection exists
        collection = await chromadb.get_collection(FEEDBACK_COLLECTION)
        if not collection:
            await chromadb.create_collection(
                FEEDBACK_COLLECTION,
                metadata={"description": "Pipeline generation feedback for RL"}
            )

        # Generate unique ID based on content
        content_hash = hashlib.md5(
            f"{original_gitlab_ci}{corrected_gitlab_ci}".encode()
        ).hexdigest()[:12]

        # Create feedback document
        feedback_doc = f"""
## Original GitLab CI:
```yaml
{original_gitlab_ci[:500]}...
```

## Corrected GitLab CI:
```yaml
{corrected_gitlab_ci[:500]}...
```

## Error Type: {error_type}
## Fix Description: {fix_description}

## Key Changes:
- Language: {language}
- Framework: {framework}
"""

        # Store in ChromaDB
        await chromadb.add_documents(
            collection_name=FEEDBACK_COLLECTION,
            ids=[f"feedback_{content_hash}_{datetime.now().strftime('%Y%m%d%H%M%S')}"],
            documents=[feedback_doc],
            metadatas=[{
                "language": language,
                "framework": framework,
                "error_type": error_type,
                "fix_description": fix_description,
                "timestamp": datetime.now().isoformat()
            }]
        )

        await chromadb.close()
        return True
    except Exception as e:
        print(f"Error storing feedback: {e}")
        return False


async def record_pipeline_result(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    pipeline_id: int
) -> Dict[str, Any]:
    """
    Check pipeline status and record the result for reinforcement learning.
    If successful, stores the configuration. If failed, records failure info.

    This is the main entry point for the RL feedback loop.

    Args:
        repo_url: GitLab repository URL
        gitlab_token: GitLab access token
        branch: Branch name
        pipeline_id: Pipeline ID to check

    Returns:
        Dict with status and learning result
    """
    try:
        parsed = parse_gitlab_url(repo_url)

        async with httpx.AsyncClient() as client:
            headers = {"PRIVATE-TOKEN": gitlab_token}

            # Get pipeline details
            pipeline_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline_id}"
            pipeline_resp = await client.get(pipeline_url, headers=headers)

            if pipeline_resp.status_code != 200:
                return {"success": False, "error": "Could not fetch pipeline details"}

            pipeline = pipeline_resp.json()
            status = pipeline.get('status')

            # Get pipeline jobs to see which stages passed
            jobs_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline_id}/jobs"
            jobs_resp = await client.get(jobs_url, headers=headers)
            jobs = jobs_resp.json() if jobs_resp.status_code == 200 else []

            stages_passed = [job['name'] for job in jobs if job.get('status') == 'success']
            stages_failed = [job['name'] for job in jobs if job.get('status') == 'failed']
            stages_running = [job['name'] for job in jobs if job.get('status') == 'running']
            stages_skipped = [job['name'] for job in jobs if job.get('status') == 'skipped']

            # Handle the case when called from the learn_record job itself
            # If pipeline is "running" but only learn_record is running and all other jobs passed,
            # we can consider it as a successful pipeline
            effective_status = status
            if status == 'running':
                # Check if only learn-related jobs are still running
                non_learn_running = [j for j in stages_running if 'learn' not in j.lower()]
                if not non_learn_running and not stages_failed:
                    # All non-learn jobs have passed, treat as success
                    effective_status = 'success'
                    print(f"[RL] Pipeline {pipeline_id} is running but all non-learn stages passed - treating as success")
                else:
                    return {
                        "success": True,
                        "status": status,
                        "message": f"Pipeline still {status}, will record when complete",
                        "recorded": False
                    }
            elif status not in ['success', 'failed']:
                return {
                    "success": True,
                    "status": status,
                    "message": f"Pipeline still {status}, will record when complete",
                    "recorded": False
                }

            status = effective_status

            # Analyze repository for language/framework
            analysis = await analyze_repository(repo_url, gitlab_token)
            language = analysis.get('language', 'unknown')
            framework = analysis.get('framework', 'generic')

            # Get the .gitlab-ci.yml and Dockerfile content
            gitlab_ci_content = ""
            dockerfile_content = ""

            for filename in ['.gitlab-ci.yml', 'Dockerfile']:
                file_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/files/{filename}/raw"
                file_resp = await client.get(file_url, headers=headers, params={"ref": branch})
                if file_resp.status_code == 200:
                    if filename == '.gitlab-ci.yml':
                        gitlab_ci_content = file_resp.text
                    else:
                        dockerfile_content = file_resp.text

            result = {
                "success": True,
                "pipeline_id": pipeline_id,
                "status": status,
                "language": language,
                "framework": framework,
                "stages_passed": stages_passed,
                "stages_failed": stages_failed,
                "duration": pipeline.get('duration'),
                "recorded": False
            }

            if status == 'success':
                # QUALITY GATE: Only save to RAG DB when ALL stages pass.
                # notify_failure is expected to be skipped (it's when: on_failure).
                # learn_record may still be running (it's the caller).
                # Any other failed or skipped job means the pipeline is NOT fully proven.
                unexpected_failed = [j for j in stages_failed if j not in ('learn_record',)]
                unexpected_skipped = [j for j in stages_skipped if j not in ('notify_failure',)]

                if unexpected_failed or unexpected_skipped:
                    issue_jobs = unexpected_failed + unexpected_skipped
                    print(f"[RL] Pipeline {pipeline_id} succeeded but has non-passing jobs: {issue_jobs} — NOT saving to RAG")
                    result["message"] = (
                        f"Pipeline succeeded but not all stages passed "
                        f"(failed: {unexpected_failed}, skipped: {unexpected_skipped}). "
                        f"NOT saving to RAG DB — only fully passing pipelines are stored."
                    )
                    result["recorded"] = False
                else:
                    # All stages passed — store as proven template
                    stored = await store_successful_pipeline(
                        repo_url=repo_url,
                        gitlab_token=gitlab_token,
                        branch=branch,
                        pipeline_id=pipeline_id,
                        gitlab_ci_content=gitlab_ci_content,
                        dockerfile_content=dockerfile_content,
                        language=language,
                        framework=framework,
                        duration=pipeline.get('duration'),
                        stages_passed=stages_passed,
                        build_tool=analysis.get('build_tool', '')
                    )
                    result["recorded"] = stored
                    result["message"] = "Pipeline succeeded with ALL stages passing! Configuration stored for reinforcement learning."
            else:
                # Record failure for analysis
                result["message"] = f"Pipeline failed. Failed stages: {', '.join(stages_failed)}"
                # Optionally store failure patterns for learning what NOT to do
                # This could be implemented later for negative reinforcement

            return result

    except Exception as e:
        print(f"[RL] Error recording pipeline result: {e}")
        return {"success": False, "error": str(e)}


async def compare_and_learn(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    generated_files: Dict[str, str]
) -> Dict[str, Any]:
    """
    Compare current files in repo with generated files and learn from differences.
    Called after manual fixes to learn from corrections.
    """
    parsed = parse_gitlab_url(repo_url)

    async with httpx.AsyncClient() as client:
        headers = {"PRIVATE-TOKEN": gitlab_token}

        differences = {}

        for filename, original_content in generated_files.items():
            # Get current file content from repo
            file_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/files/{filename.replace('/', '%2F')}/raw"
            resp = await client.get(
                file_url,
                headers=headers,
                params={"ref": branch}
            )

            if resp.status_code == 200:
                current_content = resp.text

                if current_content.strip() != original_content.strip():
                    differences[filename] = {
                        "original": original_content,
                        "corrected": current_content,
                        "changed": True
                    }
                else:
                    differences[filename] = {"changed": False}

        return differences
