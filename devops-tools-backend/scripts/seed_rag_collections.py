"""
Seed script — repopulates the RAG collections consumed by the three CI/CD
pipeline generators (GitLab, Jenkins, GitHub Actions).

Runs inside the devops-tools-backend container (or any venv with the same
deps) and talks to ChromaDB over its v2 HTTP API. Produces:

    GitLab   → pipeline_templates                 (4 lang × 1 doc = 4)
             → successful_pipelines               (4 lang × 2 synthetic = 8)
             → pipeline_feedback                  (empty — created for writers)
    Jenkins  → jenkins_pipeline_templates         (16 keys → ~10 unique docs)
             → jenkins_successful_pipelines       (same set × 2 = ~20)
             → jenkins_pipeline_feedback          (empty)
    GitHub   → github_actions_templates           (4 lang × 1 = 4)
             → github_actions_successful_pipelines (4 × 2 = 8)
             → github_actions_feedback            (empty)

Rerun-safe: upserts (not adds), so running it twice is a no-op on contents.

Why dummy embeddings: the three generators retrieve via metadata filter
($and on language/framework), not vector similarity. ChromaDB v2 still
demands an embedding vector on write, so we mint deterministic SHA-384
floats from the document — matches what ChromaDBIntegration.add_documents
auto-generates. Keeps the on-disk HNSW consistent with what the backend
would produce at runtime.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

# Allow running from repo root OR container /app.
_HERE = Path(__file__).resolve()
_BACKEND_ROOT = _HERE.parent.parent  # .../devops-tools-backend
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
# Inside the container `/app` IS the backend root, so this works too.
if "/app" not in sys.path and Path("/app").exists():
    sys.path.insert(0, "/app")

import httpx

# Default to the external URL (for host runs); override with CHROMADB_URL.
CHROMADB_URL = os.environ.get("CHROMADB_URL", "http://localhost:8005")
TENANT = "default_tenant"
DATABASE = "default_database"
API_BASE = f"/api/v2/tenants/{TENANT}/databases/{DATABASE}"

# 384-dim dummy embedding from SHA-384 — matches ChromaDBIntegration.add_documents
def _hash_embedding(doc: str) -> List[float]:
    h = hashlib.sha384(doc.encode("utf-8")).digest()
    return [b / 255.0 for b in h]


# ---------------------------------------------------------------------------
# Helpers for HTTP calls to ChromaDB v2 API
# ---------------------------------------------------------------------------
async def ensure_collection(
    client: httpx.AsyncClient, name: str, description: str, recreate_if_empty: bool = True
) -> str:
    """Create collection if missing; return UUID.

    If the collection exists but is empty AND `recreate_if_empty` is True, drop
    and recreate it. Needed because ChromaDB v2 fixes the embedding dimension
    at first write — the orphan collections left from a prior wipe have 384-dim
    headers (from an older code path that used real embeddings) but zero rows,
    and we seed with 48-dim SHA-384 vectors. Recreating lets the first seed
    write establish the dimension cleanly.
    """
    lst = await client.get(f"{API_BASE}/collections")
    lst.raise_for_status()
    existing = next((c for c in lst.json() if c.get("name") == name), None)

    if existing:
        uuid = existing["id"]
        cnt = await collection_count(client, uuid)
        if cnt == 0 and recreate_if_empty:
            print(f"  [ensure] {name}: exists but empty — dropping to reset dimension")
            # ChromaDB v2 DELETE endpoint keys on NAME, not UUID (verified empirically —
            # DELETE /collections/<uuid> returns NotFoundError, DELETE /collections/<name>
            # succeeds). GET /collections/<uuid> works by UUID though, so the path
            # parameter meaning differs per HTTP verb.
            d = await client.delete(f"{API_BASE}/collections/{name}")
            if d.status_code not in (200, 204):
                raise RuntimeError(
                    f"drop {name} failed: {d.status_code} {d.text[:200]}"
                )
        else:
            return uuid

    r = await client.post(
        f"{API_BASE}/collections",
        json={"name": name, "metadata": {"description": description}},
    )
    if r.status_code == 409:
        lst = await client.get(f"{API_BASE}/collections")
        for coll in lst.json():
            if coll.get("name") == name:
                return coll["id"]
    r.raise_for_status()
    return r.json()["id"]


async def upsert(
    client: httpx.AsyncClient,
    coll_uuid: str,
    ids: List[str],
    documents: List[str],
    metadatas: List[Dict[str, Any]],
) -> int:
    """Upsert a batch. Returns the number of records written."""
    embeddings = [_hash_embedding(d) for d in documents]
    payload = {
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
        "embeddings": embeddings,
    }
    r = await client.post(
        f"{API_BASE}/collections/{coll_uuid}/upsert", json=payload
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"upsert failed {r.status_code}: {r.text[:300]}")
    return len(ids)


async def collection_count(client: httpx.AsyncClient, coll_uuid: str) -> int:
    r = await client.get(f"{API_BASE}/collections/{coll_uuid}/count")
    r.raise_for_status()
    return int(r.json())


# ---------------------------------------------------------------------------
# Generator adapters — each returns (lang, framework, gitlab_ci/jenkinsfile/workflow, dockerfile)
# ---------------------------------------------------------------------------
JENKINS_LANGS = [
    ("java", "spring"),
    ("kotlin", "generic"),
    ("scala", "generic"),
    ("python", "flask"),
    ("python", "django"),
    ("python", "fastapi"),
    ("javascript", "nodejs"),
    ("typescript", "nodejs"),
    ("go", "generic"),
    ("rust", "generic"),
    ("ruby", "rails"),
    ("php", "generic"),
    ("csharp", "dotnet"),
]

GITHUB_LANGS = [
    ("java", "spring"),
    ("python", "flask"),
    ("javascript", "nodejs"),
    ("go", "generic"),
]

GITLAB_LANGS = [
    ("java", "spring"),
    ("python", "generic"),
    ("javascript", "generic"),
    ("go", "generic"),
]


def gitlab_sample(lang: str, framework: str) -> Tuple[str, str]:
    """Return (gitlab-ci.yml, Dockerfile) for a language."""
    from app.services.pipeline_generator import PipelineGeneratorService

    svc = PipelineGeneratorService()
    analysis = {"language": lang, "framework": framework}
    return svc._get_default_gitlab_ci(analysis), svc._get_default_dockerfile(analysis)


def jenkins_sample(lang: str, framework: str) -> Tuple[str, str]:
    from app.services.jenkins_pipeline.default_templates import (
        _get_default_jenkinsfile,
        _get_default_dockerfile,
    )

    analysis = {"language": lang, "framework": framework}
    return _get_default_jenkinsfile(analysis), _get_default_dockerfile(analysis)


def github_sample(lang: str, framework: str) -> Tuple[str, str]:
    from app.services.github_pipeline.default_templates import (
        _get_default_workflow,
        _get_default_dockerfile,
    )

    analysis = {"language": lang, "framework": framework}
    return _get_default_workflow(analysis), _get_default_dockerfile(analysis)


# ---------------------------------------------------------------------------
# Per-generator seeding plan — collection names match each generator's constants
# ---------------------------------------------------------------------------
PLAN: List[Dict[str, Any]] = [
    {
        "key": "gitlab",
        "templates_coll": "pipeline_templates",
        "successful_coll": "successful_pipelines",
        "feedback_coll": "pipeline_feedback",
        "langs": GITLAB_LANGS,
        "sampler": gitlab_sample,
        "ci_file_name": ".gitlab-ci.yml",
    },
    {
        "key": "jenkins",
        "templates_coll": "jenkins_pipeline_templates",
        "successful_coll": "jenkins_successful_pipelines",
        "feedback_coll": "jenkins_pipeline_feedback",
        "langs": JENKINS_LANGS,
        "sampler": jenkins_sample,
        "ci_file_name": "Jenkinsfile",
    },
    {
        "key": "github",
        "templates_coll": "github_actions_templates",
        "successful_coll": "github_actions_successful_pipelines",
        "feedback_coll": "github_actions_feedback",
        "langs": GITHUB_LANGS,
        "sampler": github_sample,
        "ci_file_name": ".github/workflows/ci.yml",
    },
]


def _wrap_document(label: str, ci: str, docker: str, ci_file_name: str) -> str:
    """Combine CI + Dockerfile into a single RAG document."""
    return (
        f"## {label}\n\n"
        f"### {ci_file_name}\n```\n{ci}\n```\n\n"
        f"### Dockerfile\n```\n{docker}\n```\n"
    )


async def seed_one_generator(client: httpx.AsyncClient, plan: Dict[str, Any]) -> Dict[str, int]:
    """Returns {collection_name: records_written}."""
    key = plan["key"]
    written: Dict[str, int] = {}

    # Ensure all 3 collections exist
    tmpl_uuid = await ensure_collection(
        client, plan["templates_coll"], f"{key} — proven pipeline templates per language"
    )
    succ_uuid = await ensure_collection(
        client, plan["successful_coll"], f"{key} — synthetic successful pipeline seeds for RL"
    )
    fb_uuid = await ensure_collection(
        client, plan["feedback_coll"], f"{key} — user correction feedback for RL"
    )
    written[plan["feedback_coll"]] = 0  # always empty at seed-time

    # Templates — one record per (lang, framework)
    t_ids, t_docs, t_meta = [], [], []
    for lang, framework in plan["langs"]:
        try:
            ci, docker = plan["sampler"](lang, framework)
        except Exception as e:
            print(f"  [{key}] skip {lang}/{framework}: {e}")
            continue
        doc_id = f"template_{lang}_{framework}"
        doc = _wrap_document(f"Proven {key} template ({lang}/{framework})", ci, docker, plan["ci_file_name"])
        t_ids.append(doc_id)
        t_docs.append(doc)
        t_meta.append(
            {
                "type": f"{key}-template",
                "language": lang,
                "framework": framework,
                "seed_source": "default_templates",
                "seeded_at": datetime.utcnow().isoformat(),
            }
        )
    if t_ids:
        written[plan["templates_coll"]] = await upsert(client, tmpl_uuid, t_ids, t_docs, t_meta)

    # Successful pipelines — 2 synthetic "successful runs" per lang to bootstrap RL retrieval
    s_ids, s_docs, s_meta = [], [], []
    for lang, framework in plan["langs"]:
        try:
            ci, docker = plan["sampler"](lang, framework)
        except Exception:
            continue
        for run_idx in (1, 2):
            doc_id = f"success_{lang}_{framework}_seed_{run_idx}"
            doc = (
                f"## Successful {key} pipeline — {lang}/{framework} (seed run {run_idx})\n\n"
                f"Duration: {180 + run_idx * 60} seconds\n"
                f"Stages passed: compile, build, test, sast, quality, security, push, notify, learn\n\n"
                f"### {plan['ci_file_name']}\n```\n{ci}\n```\n\n"
                f"### Dockerfile\n```\n{docker}\n```\n"
            )
            s_ids.append(doc_id)
            s_docs.append(doc)
            s_meta.append(
                {
                    "type": f"{key}-successful",
                    "language": lang,
                    "framework": framework,
                    "duration": 180 + run_idx * 60,
                    "stages_count": 9,
                    "success": "true",
                    "seeded_at": datetime.utcnow().isoformat(),
                    "seed_run": run_idx,
                }
            )
    if s_ids:
        written[plan["successful_coll"]] = await upsert(client, succ_uuid, s_ids, s_docs, s_meta)

    return written


async def main() -> int:
    print(f"[seed] ChromaDB URL: {CHROMADB_URL}")
    print(f"[seed] API base:    {API_BASE}")
    print()

    async with httpx.AsyncClient(base_url=CHROMADB_URL, timeout=30.0) as client:
        # Prove reachability
        h = await client.get("/api/v2/heartbeat")
        h.raise_for_status()
        print(f"[seed] heartbeat ok: {h.json()}")

        all_written: Dict[str, int] = {}
        for plan in PLAN:
            print(f"\n[seed] ---- {plan['key']} ----")
            out = await seed_one_generator(client, plan)
            all_written.update(out)
            for coll, n in out.items():
                print(f"  {coll}: +{n}")

        # Final tally via explicit /count — proves the data is persisted, not
        # just accepted by the upsert endpoint
        print("\n[seed] ==== final counts (via /count) ====")
        lst = (await client.get(f"{API_BASE}/collections")).json()
        total = 0
        for coll in sorted(lst, key=lambda c: c["name"]):
            r = await client.get(f"{API_BASE}/collections/{coll['id']}/count")
            n = int(r.json())
            total += n
            print(f"  {coll['name']:40s} {n:5d}")
        print(f"  {'TOTAL':40s} {total:5d}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
