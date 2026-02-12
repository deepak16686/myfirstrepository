"""
ChromaDB template operations for Terraform configurations.

Handles retrieving reference Terraform files and best-performing templates.
"""
import httpx
from typing import Dict, Any, Optional

from app.config import settings
from app.services.terraform.constants import (
    TEMPLATES_COLLECTION,
    SUCCESSFUL_COLLECTION,
)

# Cache collection name -> UUID mappings
_collection_uuid_cache: Dict[str, str] = {}


async def _resolve_collection_uuid(client: httpx.AsyncClient, name: str) -> Optional[str]:
    """Resolve ChromaDB collection name to UUID (v2 API requires UUIDs)."""
    if name in _collection_uuid_cache:
        return _collection_uuid_cache[name]

    chromadb_url = settings.chromadb_url
    resp = await client.get(
        f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
    )
    if resp.status_code == 200:
        for coll in resp.json():
            if coll.get("name") == name:
                uuid = coll["id"]
                _collection_uuid_cache[name] = uuid
                return uuid
    return None


async def get_reference_terraform(
    provider: str,
    resource_type: str,
    sub_type: Optional[str] = None,
) -> Optional[str]:
    """Get reference Terraform config from ChromaDB templates collection."""
    chromadb_url = settings.chromadb_url
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            coll_uuid = await _resolve_collection_uuid(client, TEMPLATES_COLLECTION)
            if not coll_uuid:
                return None

            # Try exact match with provider + resource + sub_type
            where_filter = {
                "$and": [
                    {"provider": provider},
                    {"resource_type": resource_type},
                ]
            }
            if sub_type:
                where_filter["$and"].append({"sub_type": sub_type})

            response = await client.post(
                f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{coll_uuid}/get",
                json={
                    "where": where_filter,
                    "limit": 1,
                    "include": ["documents", "metadatas"],
                },
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("documents"):
                    return data["documents"][0]

            # Fallback: provider + resource only
            if sub_type:
                response = await client.post(
                    f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{coll_uuid}/get",
                    json={
                        "where": {
                            "$and": [
                                {"provider": provider},
                                {"resource_type": resource_type},
                            ]
                        },
                        "limit": 1,
                        "include": ["documents", "metadatas"],
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("documents"):
                        return data["documents"][0]

    except Exception as e:
        print(f"[Terraform ChromaDB] Error getting reference: {e}")

    return None


async def get_best_template_files(
    provider: str,
    resource_type: str,
    sub_type: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Get the best performing template from successful configs."""
    chromadb_url = settings.chromadb_url
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            coll_uuid = await _resolve_collection_uuid(client, SUCCESSFUL_COLLECTION)
            if not coll_uuid:
                return None

            where_filter = {
                "$and": [
                    {"provider": provider},
                    {"resource_type": resource_type},
                ]
            }

            response = await client.post(
                f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{coll_uuid}/get",
                json={
                    "where": where_filter,
                    "limit": 10,
                    "include": ["documents", "metadatas"],
                },
            )

            if response.status_code == 200:
                data = response.json()
                documents = data.get("documents", [])
                metadatas = data.get("metadatas", [])

                if documents:
                    # Pick the most recent successful config
                    best_idx = 0
                    best_score = 0
                    for i, meta in enumerate(metadatas):
                        score = meta.get("success_count", 1)
                        if score > best_score:
                            best_score = score
                            best_idx = i

                    doc = documents[best_idx]
                    # Parse structured document
                    files = _parse_stored_document(doc)
                    if files:
                        files["source"] = "chromadb-successful"
                        return files

    except Exception as e:
        print(f"[Terraform ChromaDB] Error getting best template: {e}")

    return None


def _parse_stored_document(doc: str) -> Optional[Dict[str, str]]:
    """Parse a stored ChromaDB document back into individual .tf files."""
    files = {}
    markers = {
        "### provider.tf": "provider.tf",
        "### main.tf": "main.tf",
        "### variables.tf": "variables.tf",
        "### outputs.tf": "outputs.tf",
        "### terraform.tfvars.example": "terraform.tfvars.example",
    }

    for marker, filename in markers.items():
        if marker in doc:
            start = doc.index(marker) + len(marker)
            # Find the next marker or end
            end = len(doc)
            for other_marker in markers:
                if other_marker != marker and other_marker in doc:
                    other_pos = doc.index(other_marker)
                    if other_pos > start and other_pos < end:
                        end = other_pos

            content = doc[start:end].strip()
            # Remove markdown code blocks
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()
            if content:
                files[filename] = content

    return files if files else None
