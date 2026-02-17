"""
Reinforcement Learning / Feedback Functions for Jenkins Pipelines

Standalone async functions for RL feedback loop and build result recording.
Uses Gitea API for fetching repo files (Jenkins repos hosted on Gitea).
"""
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

import httpx

from app.config import tools_manager, settings
from app.integrations.chromadb import ChromaDBIntegration

from .constants import FEEDBACK_COLLECTION, SUCCESSFUL_PIPELINES_COLLECTION
from .analyzer import parse_repo_url, analyze_repository


def _get_chromadb() -> ChromaDBIntegration:
    chromadb_config = tools_manager.get_tool("chromadb")
    return ChromaDBIntegration(chromadb_config)


async def get_relevant_feedback(language: str, framework: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieve relevant feedback from ChromaDB based on language and framework.
    Implements the reinforcement learning aspect for Jenkins pipelines.
    """
    try:
        chromadb = _get_chromadb()

        collection = await chromadb.get_collection(FEEDBACK_COLLECTION)
        if not collection:
            await chromadb.close()
            return []

        query_text = f"jenkinsfile pipeline for {language} {framework} application"
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
        print(f"[Jenkins RL] Error getting feedback: {e}")
        return []


async def store_feedback(
    original_jenkinsfile: str,
    corrected_jenkinsfile: str,
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
                metadata={"description": "Jenkins pipeline generation feedback for RL"}
            )

        content_hash = hashlib.md5(
            f"{original_jenkinsfile}{corrected_jenkinsfile}".encode()
        ).hexdigest()[:12]

        feedback_doc = f"""
## Original Jenkinsfile:
```groovy
{original_jenkinsfile[:500]}...
```

## Corrected Jenkinsfile:
```groovy
{corrected_jenkinsfile[:500]}...
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
        print(f"[Jenkins RL] Error storing feedback: {e}")
        return False


async def store_successful_pipeline(
    job_name: str,
    build_number: int,
    jenkinsfile_content: str,
    dockerfile_content: str,
    language: str,
    framework: str,
    duration: Optional[int] = None,
    stages_passed: Optional[List[str]] = None
) -> bool:
    """
    Store a successful Jenkins build configuration in ChromaDB for RL.
    """
    try:
        chromadb = _get_chromadb()

        try:
            collection = await chromadb.get_collection(SUCCESSFUL_PIPELINES_COLLECTION)
            if not collection:
                await chromadb.create_collection(
                    SUCCESSFUL_PIPELINES_COLLECTION,
                    metadata={"description": "Successful Jenkins pipeline configurations for RL"}
                )
        except Exception as coll_err:
            if "409" not in str(coll_err) and "conflict" not in str(coll_err).lower():
                print(f"[Jenkins RL] Collection check warning: {coll_err}")

        content_hash = hashlib.md5(
            f"{jenkinsfile_content}{language}{framework}".encode()
        ).hexdigest()[:12]
        doc_id = f"jenkins_success_{language}_{framework}_{content_hash}"

        success_doc = f"""## Successful Jenkins Pipeline Configuration
Language: {language}
Framework: {framework}
Job: {job_name}
Build: #{build_number}
Duration: {duration or 'N/A'} seconds
Stages Passed: {', '.join(stages_passed) if stages_passed else 'all'}

### Jenkinsfile
```groovy
{jenkinsfile_content}
```

### Dockerfile
```dockerfile
{dockerfile_content}
```
"""

        metadata = {
            "language": language.lower(),
            "framework": framework.lower(),
            "job_name": job_name,
            "build_number": build_number,
            "duration": duration or 0,
            "stages_count": len(stages_passed) if stages_passed else 9,
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
            print(f"[Jenkins RL] Updated existing successful pipeline for {language}/{framework}")
        else:
            await chromadb.add_documents(
                collection_name=SUCCESSFUL_PIPELINES_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata]
            )
            print(f"[Jenkins RL] Stored new successful pipeline for {language}/{framework}")

        await chromadb.close()
        return True

    except Exception as e:
        print(f"[Jenkins RL] Error storing successful pipeline: {e}")
        return False


async def record_build_result(
    repo_url: str,
    git_token: str,
    branch: str,
    job_name: str,
    build_number: int
) -> Dict[str, Any]:
    """
    Check Jenkins build status and record the result for RL.
    Fetches actual Jenkinsfile and Dockerfile from the Gitea repo,
    then stores them if the build succeeded.
    """
    try:
        # Get build status from Jenkins
        auth = (settings.jenkins_username, settings.jenkins_password)
        build_url = f"{settings.jenkins_url}/job/{job_name}/{build_number}/api/json"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(build_url, auth=auth)
            if resp.status_code != 200:
                return {"success": False, "error": "Could not fetch build details"}

            build_data = resp.json()
            build_status = "building" if build_data.get("building") else (build_data.get("result", "UNKNOWN")).lower()

        if build_status == "building":
            return {
                "success": True,
                "status": "building",
                "message": "Build still running",
                "recorded": False
            }

        if build_status not in ["success", "failure"]:
            return {
                "success": True,
                "status": build_status,
                "message": f"Build status: {build_status}",
                "recorded": False
            }

        # Analyze repository for language/framework
        analysis = await analyze_repository(repo_url, git_token)
        language = analysis.get('language', 'unknown')
        framework = analysis.get('framework', 'generic')

        # Get Jenkinsfile and Dockerfile from Gitea
        parsed = parse_repo_url(repo_url)
        jenkinsfile_content = ""
        dockerfile_content = ""

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"token {git_token}"}
            for filename in ['Jenkinsfile', 'Dockerfile']:
                file_url = f"{parsed['host']}/api/v1/repos/{parsed['owner']}/{parsed['repo']}/raw/{filename}"
                file_resp = await client.get(file_url, headers=headers, params={"ref": branch})
                if file_resp.status_code == 200:
                    if filename == 'Jenkinsfile':
                        jenkinsfile_content = file_resp.text
                    else:
                        dockerfile_content = file_resp.text

        result = {
            "success": True,
            "job_name": job_name,
            "build_number": build_number,
            "status": build_status,
            "language": language,
            "framework": framework,
            "duration": build_data.get("duration"),
            "recorded": False
        }

        if build_status == "success" and jenkinsfile_content:
            stored = await store_successful_pipeline(
                job_name=job_name,
                build_number=build_number,
                jenkinsfile_content=jenkinsfile_content,
                dockerfile_content=dockerfile_content,
                language=language,
                framework=framework,
                duration=build_data.get("duration"),
            )
            result["recorded"] = stored
            result["message"] = "Build succeeded! Configuration stored for RL." if stored else "Build succeeded but storage failed."
        else:
            result["message"] = f"Build failed. Status: {build_status}"

        return result

    except Exception as e:
        print(f"[Jenkins RL] Error recording build result: {e}")
        return {"success": False, "error": str(e)}


async def compare_and_learn(
    repo_url: str,
    git_token: str,
    branch: str,
    generated_files: Dict[str, str]
) -> Dict[str, Any]:
    """
    Compare current files in repo with generated files and learn from differences.
    """
    parsed = parse_repo_url(repo_url)

    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"token {git_token}"}
        differences = {}

        for filename, original_content in generated_files.items():
            file_url = f"{parsed['host']}/api/v1/repos/{parsed['owner']}/{parsed['repo']}/raw/{filename}"
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
