"""
Reinforcement Learning / Feedback Functions for Terraform Configurations

Stores and retrieves feedback for iterative improvement of Terraform generation.
"""
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

import httpx

from app.config import tools_manager
from app.integrations.chromadb import ChromaDBIntegration

from .constants import FEEDBACK_COLLECTION, SUCCESSFUL_COLLECTION


def _get_chromadb() -> ChromaDBIntegration:
    chromadb_config = tools_manager.get_tool("chromadb")
    return ChromaDBIntegration(chromadb_config)


async def get_relevant_feedback(
    provider: str,
    resource_type: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve relevant feedback from ChromaDB based on provider and resource type."""
    try:
        chromadb = _get_chromadb()

        collection = await chromadb.get_collection(FEEDBACK_COLLECTION)
        if not collection:
            await chromadb.close()
            return []

        query_text = f"terraform {provider} {resource_type} configuration"
        results = await chromadb.query(
            collection_id=FEEDBACK_COLLECTION,
            query_texts=[query_text],
            n_results=limit,
            include=["documents", "metadatas"],
        )

        await chromadb.close()

        feedback_list = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                feedback_list.append({
                    "feedback": doc,
                    "provider": metadata.get("provider"),
                    "resource_type": metadata.get("resource_type"),
                    "error_type": metadata.get("error_type"),
                    "fix_description": metadata.get("fix_description"),
                })

        return feedback_list
    except Exception as e:
        print(f"[Terraform RL] Error getting feedback: {e}")
        return []


async def store_feedback(
    original_files: Dict[str, str],
    corrected_files: Dict[str, str],
    provider: str,
    resource_type: str,
    error_type: str,
    fix_description: str,
) -> bool:
    """Store feedback from manual corrections for reinforcement learning."""
    try:
        chromadb = _get_chromadb()

        collection = await chromadb.get_collection(FEEDBACK_COLLECTION)
        if not collection:
            await chromadb.create_collection(
                FEEDBACK_COLLECTION,
                metadata={"description": "Terraform generation feedback for RL"},
            )

        content_hash = hashlib.md5(
            f"{str(original_files)}{str(corrected_files)}".encode()
        ).hexdigest()[:12]

        feedback_doc = f"""## Terraform Feedback
Provider: {provider}
Resource Type: {resource_type}
Error Type: {error_type}
Fix Description: {fix_description}

### Original main.tf (excerpt):
```hcl
{original_files.get('main.tf', '')[:500]}
```

### Corrected main.tf (excerpt):
```hcl
{corrected_files.get('main.tf', '')[:500]}
```
"""

        await chromadb.add_documents(
            collection_name=FEEDBACK_COLLECTION,
            ids=[f"tf_feedback_{content_hash}_{datetime.now().strftime('%Y%m%d%H%M%S')}"],
            documents=[feedback_doc],
            metadatas=[{
                "provider": provider,
                "resource_type": resource_type,
                "error_type": error_type,
                "fix_description": fix_description,
                "timestamp": datetime.now().isoformat(),
            }],
        )

        await chromadb.close()
        return True
    except Exception as e:
        print(f"[Terraform RL] Error storing feedback: {e}")
        return False


async def store_successful_config(
    files: Dict[str, str],
    provider: str,
    resource_type: str,
    sub_type: Optional[str] = None,
    plan_output: Optional[str] = None,
) -> bool:
    """Store a successful Terraform configuration in ChromaDB for RL."""
    try:
        chromadb = _get_chromadb()

        try:
            collection = await chromadb.get_collection(SUCCESSFUL_COLLECTION)
            if not collection:
                await chromadb.create_collection(
                    SUCCESSFUL_COLLECTION,
                    metadata={"description": "Successful Terraform configurations for RL"},
                )
        except Exception as coll_err:
            if "409" not in str(coll_err) and "conflict" not in str(coll_err).lower():
                print(f"[Terraform RL] Collection check warning: {coll_err}")

        content_hash = hashlib.md5(
            f"{files.get('main.tf', '')}{provider}{resource_type}".encode()
        ).hexdigest()[:12]
        doc_id = f"tf_success_{provider}_{resource_type}_{content_hash}"

        # Build structured document with all files
        sections = []
        sections.append(f"## Successful Terraform Configuration")
        sections.append(f"Provider: {provider}")
        sections.append(f"Resource Type: {resource_type}")
        if sub_type:
            sections.append(f"Sub Type: {sub_type}")
        sections.append("")

        for filename, content in files.items():
            sections.append(f"### {filename}")
            sections.append(f"```hcl\n{content}\n```")
            sections.append("")

        if plan_output:
            sections.append(f"### Plan Output (excerpt)")
            sections.append(f"```\n{plan_output[:500]}\n```")

        success_doc = "\n".join(sections)

        metadata = {
            "provider": provider,
            "resource_type": resource_type,
            "sub_type": sub_type or "",
            "success": "true",
            "success_count": 1,
            "timestamp": datetime.now().isoformat(),
        }

        existing = await chromadb.get_documents(
            collection_name=SUCCESSFUL_COLLECTION,
            ids=[doc_id],
        )

        if existing and existing.get("ids"):
            # Increment success count
            old_meta = existing.get("metadatas", [{}])[0] if existing.get("metadatas") else {}
            metadata["success_count"] = old_meta.get("success_count", 0) + 1
            await chromadb.update_documents(
                collection_name=SUCCESSFUL_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata],
            )
            print(f"[Terraform RL] Updated successful config for {provider}/{resource_type}")
        else:
            await chromadb.add_documents(
                collection_name=SUCCESSFUL_COLLECTION,
                ids=[doc_id],
                documents=[success_doc],
                metadatas=[metadata],
            )
            print(f"[Terraform RL] Stored new successful config for {provider}/{resource_type}")

        await chromadb.close()
        return True

    except Exception as e:
        print(f"[Terraform RL] Error storing successful config: {e}")
        return False


async def record_plan_result(
    workspace_id: str,
    provider: str,
    resource_type: str,
    success: bool,
    plan_output: str,
) -> Dict[str, Any]:
    """Record the result of a terraform plan for RL tracking."""
    return {
        "workspace_id": workspace_id,
        "provider": provider,
        "resource_type": resource_type,
        "success": success,
        "plan_output_excerpt": plan_output[:500] if plan_output else "",
        "timestamp": datetime.now().isoformat(),
    }
