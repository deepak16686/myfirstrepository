"""
File: learning.py
Purpose: Implements the reinforcement learning feedback loop for GitHub Actions pipelines. Stores
    and retrieves RL feedback (manual corrections) and successful pipeline configurations in
    ChromaDB, and records build results by checking Gitea Actions run/job status and persisting
    the actual workflow YAML and Dockerfile from the repository.
When Used: The record_build_result() function is called by the /learn/record endpoint, which is
    triggered by the learn-record job at the end of every successful pipeline run. store_feedback()
    is called when users manually correct a generated workflow. get_relevant_feedback() is used
    during generation to inform the LLM with past corrections.
Why Created: Separated from the generator to isolate all ChromaDB read/write operations and the
    complex build-result recording logic (Gitea Actions API status checking, file fetching,
    job-level success evaluation) into a dedicated module.
"""
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

import httpx

from app.config import tools_manager, settings
from app.integrations.chromadb import ChromaDBIntegration

from .constants import FEEDBACK_COLLECTION, SUCCESSFUL_PIPELINES_COLLECTION
from .analyzer import parse_github_url, analyze_repository


def _get_chromadb() -> ChromaDBIntegration:
    chromadb_config = tools_manager.get_tool("chromadb")
    return ChromaDBIntegration(chromadb_config)


async def get_relevant_feedback(language: str, framework: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieve relevant feedback from ChromaDB based on language and framework.
    Implements the reinforcement learning aspect for GitHub Actions workflows.
    """
    try:
        chromadb = _get_chromadb()

        collection = await chromadb.get_collection(FEEDBACK_COLLECTION)
        if not collection:
            await chromadb.close()
            return []

        query_text = f"github actions workflow for {language} {framework} application"
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
        print(f"[GitHub RL] Error getting feedback: {e}")
        return []


async def store_feedback(
    original_workflow: str,
    corrected_workflow: str,
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

        collection = await chromadb.get_collection(FEEDBACK_COLLECTION)
        if not collection:
            await chromadb.create_collection(
                FEEDBACK_COLLECTION,
                metadata={"description": "GitHub Actions workflow generation feedback for RL"}
            )

        content_hash = hashlib.md5(
            f"{original_workflow}{corrected_workflow}".encode()
        ).hexdigest()[:12]

        feedback_doc = f"""
## Original Workflow:
```yaml
{original_workflow[:500]}...
```

## Corrected Workflow:
```yaml
{corrected_workflow[:500]}...
```

## Error Type: {error_type}
## Fix Description: {fix_description}

## Key Changes:
- Language: {language}
- Framework: {framework}
"""

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
        print(f"[GitHub RL] Error storing feedback: {e}")
        return False


async def store_successful_pipeline(
    repo_url: str,
    run_id: int,
    workflow_content: str,
    dockerfile_content: str,
    language: str,
    framework: str,
    duration: Optional[int] = None,
    jobs_passed: Optional[List[str]] = None
) -> bool:
    """
    Store a successful GitHub Actions workflow configuration in ChromaDB for RL.
    """
    try:
        chromadb = _get_chromadb()

        try:
            collection = await chromadb.get_collection(SUCCESSFUL_PIPELINES_COLLECTION)
            if not collection:
                await chromadb.create_collection(
                    SUCCESSFUL_PIPELINES_COLLECTION,
                    metadata={"description": "Successful GitHub Actions workflow configurations for RL"}
                )
        except Exception as coll_err:
            if "409" not in str(coll_err) and "conflict" not in str(coll_err).lower():
                print(f"[GitHub RL] Collection check warning: {coll_err}")

        content_hash = hashlib.md5(
            f"{workflow_content}{language}{framework}".encode()
        ).hexdigest()[:12]
        doc_id = f"github_success_{language}_{framework}_{content_hash}"

        success_doc = f"""## Successful GitHub Actions Workflow Configuration
Language: {language}
Framework: {framework}
Repository: {repo_url}
Run ID: #{run_id}
Duration: {duration or 'N/A'} seconds
Jobs Passed: {', '.join(jobs_passed) if jobs_passed else 'all'}

### Workflow (.github/workflows/ci.yml)
```yaml
{workflow_content}
```

### Dockerfile
```dockerfile
{dockerfile_content}
```
"""

        metadata = {
            "language": language.lower(),
            "framework": framework.lower(),
            "repo_url": repo_url,
            "run_id": run_id,
            "duration": duration or 0,
            "jobs_count": len(jobs_passed) if jobs_passed else 9,
            "success": "true",
            "timestamp": datetime.now().isoformat(),
        }

        existing = await chromadb.get_documents(
            collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
            ids=[doc_id]
        )

        if existing and existing.get('ids'):
            await chromadb.update_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata]
            )
            print(f"[GitHub RL] Updated existing successful workflow for {language}/{framework}")
        else:
            await chromadb.add_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata]
            )
            print(f"[GitHub RL] Stored new successful workflow for {language}/{framework}")

        await chromadb.close()
        return True

    except Exception as e:
        print(f"[GitHub RL] Error storing successful workflow: {e}")
        return False


async def record_build_result(
    repo_url: str,
    github_token: str,
    branch: str,
    run_id: int
) -> Dict[str, Any]:
    """
    Check Gitea Actions workflow run status and record the result for RL.
    Fetches actual workflow YAML and Dockerfile from the Gitea repo,
    then stores them if the workflow succeeded.
    """
    try:
        parsed = parse_github_url(repo_url)
        api_base = f"{parsed['host']}/api/v1/repos/{parsed['owner']}/{parsed['repo']}"
        headers = {"Authorization": f"token {github_token}"}

        # Get workflow run status from Gitea Actions API
        # NOTE: When called from learn-record job (if: success()), the overall run
        # is still "in_progress" because learn-record itself hasn't finished.
        # So we check individual job conclusions instead of the overall run status.
        async with httpx.AsyncClient(timeout=30.0) as client:
            run_status = "unknown"
            run_duration = None

            # Check individual job conclusions for this run
            jobs_resp = await client.get(
                f"{api_base}/actions/runs/{run_id}/jobs",
                headers=headers
            )
            if jobs_resp.status_code == 200:
                jobs_data = jobs_resp.json()
                jobs_list = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else jobs_data
                # Exclude learn-record and notify-failure from success check.
                # notify-failure has if:failure() so it's always skipped on success.
                skip_names = {"learn-record", "notify-failure"}
                non_learn_jobs = [j for j in jobs_list if j.get("name") not in skip_names]
                if non_learn_jobs:
                    all_success = all(
                        j.get("conclusion") in ("success", "skipped") for j in non_learn_jobs
                    )
                    if all_success:
                        run_status = "success"
                        print(f"[GitHub RL] All {len(non_learn_jobs)} non-learn jobs succeeded for run #{run_id}")
                    else:
                        failed = [j["name"] for j in non_learn_jobs if j.get("conclusion") != "success"]
                        run_status = "failure"
                        print(f"[GitHub RL] Some jobs failed: {failed}")

            # Fallback: check overall run conclusion (for external callers)
            if run_status == "unknown":
                runs_resp = await client.get(
                    f"{api_base}/actions/runs",
                    headers=headers,
                    params={"branch": branch, "limit": 5}
                )
                if runs_resp.status_code == 200:
                    runs_data = runs_resp.json()
                    workflow_runs = runs_data.get("workflow_runs", [])
                    for run in workflow_runs:
                        if run.get("id") == run_id:
                            run_status = run.get("conclusion", run.get("status", "unknown"))
                            break

        # Analyze repository for language/framework
        analysis = await analyze_repository(repo_url, github_token)
        language = analysis.get('language', 'unknown')
        framework = analysis.get('framework', 'generic')

        # Get workflow YAML and Dockerfile from Gitea
        workflow_content = ""
        dockerfile_content = ""

        async with httpx.AsyncClient(timeout=30.0) as client:
            for filepath in ['.github/workflows/ci.yml', 'Dockerfile']:
                file_url = f"{api_base}/raw/{filepath}"
                file_resp = await client.get(file_url, headers=headers, params={"ref": branch})
                if file_resp.status_code == 200:
                    if 'ci.yml' in filepath:
                        workflow_content = file_resp.text
                    else:
                        dockerfile_content = file_resp.text

        result = {
            "success": True,
            "repo_url": repo_url,
            "run_id": run_id,
            "status": run_status,
            "language": language,
            "framework": framework,
            "duration": run_duration,
            "recorded": False
        }

        if run_status == "success" and workflow_content:
            stored = await store_successful_pipeline(
                repo_url=repo_url,
                run_id=run_id,
                workflow_content=workflow_content,
                dockerfile_content=dockerfile_content,
                language=language,
                framework=framework,
                duration=run_duration,
            )
            result["recorded"] = stored
            result["message"] = "Workflow succeeded! Configuration stored for RL." if stored else "Workflow succeeded but storage failed."
        else:
            result["message"] = f"Workflow status: {run_status}"

        return result

    except Exception as e:
        print(f"[GitHub RL] Error recording build result: {e}")
        return {"success": False, "error": str(e)}


async def compare_and_learn(
    repo_url: str,
    github_token: str,
    branch: str,
    generated_files: Dict[str, str]
) -> Dict[str, Any]:
    """
    Compare current files in repo with generated files and learn from differences.
    """
    parsed = parse_github_url(repo_url)
    api_base = f"{parsed['host']}/api/v1/repos/{parsed['owner']}/{parsed['repo']}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"token {github_token}"}
        differences = {}

        for filename, original_content in generated_files.items():
            file_url = f"{api_base}/raw/{filename}"
            resp = await client.get(file_url, headers=headers, params={"ref": branch})

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
