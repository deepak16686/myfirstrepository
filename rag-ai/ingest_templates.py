import chromadb
import json
import os
from pathlib import Path

# Connect to ChromaDB
client = chromadb.HttpClient(host='localhost', port=8000)

# Get collections
dockerfile_collection = client.get_collection("templates_dockerfile")
gitlab_collection = client.get_collection("templates_gitlab")
golden_rules_collection = client.get_collection("golden_rules")

# Counters
counts = {"dockerfiles": 0, "gitlab": 0, "golden_rules": 0}

def prepare_metadata(metadata):
    """Convert lists to comma-separated strings for ChromaDB compatibility"""
    prepared = {}
    for key, value in metadata.items():
        if isinstance(value, list):
            prepared[key] = ",".join(value)
        else:
            prepared[key] = value
    return prepared

# Ingest Dockerfiles
dockerfile_dir = Path("rag-ai/rag_corpus/dockerfiles")
for dockerfile in dockerfile_dir.glob("*.dockerfile"):
    meta_file = dockerfile.with_suffix(".meta.json")
    
    if meta_file.exists():
        with open(dockerfile, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(meta_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Upsert into ChromaDB
        dockerfile_collection.upsert(
            ids=[dockerfile.stem],
            documents=[content],
            metadatas=[prepare_metadata(metadata)]
        )
        counts["dockerfiles"] += 1
        print(f"[OK] Ingested Dockerfile: {dockerfile.name}")
    else:
        print(f"[SKIP] No metadata for: {dockerfile.name}")

# Ingest GitLab CI files
gitlab_dir = Path("rag-ai/rag_corpus/gitlab")
for gitlab_file in gitlab_dir.glob("*.yml"):
    meta_file = gitlab_file.with_suffix(".meta.json")
    
    if meta_file.exists():
        with open(gitlab_file, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(meta_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Upsert into ChromaDB
        gitlab_collection.upsert(
            ids=[gitlab_file.stem],
            documents=[content],
            metadatas=[prepare_metadata(metadata)]
        )
        counts["gitlab"] += 1
        print(f"[OK] Ingested GitLab CI: {gitlab_file.name}")
    else:
        print(f"[SKIP] No metadata for: {gitlab_file.name}")

# Ingest Golden Rules
golden_rules_file = Path("rag-ai/rag_corpus/rag_specs/golden_rules.md")
if golden_rules_file.exists():
    with open(golden_rules_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    golden_rules_collection.upsert(
        ids=["golden_rules_v1"],
        documents=[content],
        metadatas=[{"type": "constraints", "priority": "critical"}]
    )
    counts["golden_rules"] += 1
    print(f"[OK] Ingested: {golden_rules_file.name}")

# Summary
print(f"\nIngestion Summary:")
print(f"  Dockerfiles: {counts['dockerfiles']}")
print(f"  GitLab CI: {counts['gitlab']}")
print(f"  Golden Rules: {counts['golden_rules']}")
print(f"  Total: {sum(counts.values())}")
