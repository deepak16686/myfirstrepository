import sqlite3
import json

DB_PATH = "/app/backend/data/webui.db"
conn = sqlite3.connect(DB_PATH)

# Check current models
rows = conn.execute("SELECT id, name, params, meta FROM model").fetchall()
print("Current models:")
for row in rows:
    print(f"  ID: {row[0]}, Name: {row[1]}")
    params = json.loads(row[2]) if row[2] else {}
    meta = json.loads(row[3]) if row[3] else {}
    print(f"    params keys: {list(params.keys())}")
    print(f"    meta keys: {list(meta.keys())}")
    if "toolIds" in meta:
        print(f"    current toolIds: {meta['toolIds']}")
    if "system" in params:
        print(f"    current system prompt (first 100 chars): {params.get('system', '')[:100]}")

print("\n--- Updating models ---\n")

SYSTEM_PROMPT = """You have access to a tool called 'list_docker_images' that queries the private Nexus Docker registry.

IMPORTANT RULES:
1. When the user asks about Docker images, Dockerfiles, or container images for ANY technology (python, node, java, golang, mongodb, redis, nginx, etc.), ALWAYS use the list_docker_images tool FIRST to check what is available in the private Nexus registry.
2. When generating a Dockerfile, ALWAYS use the list_docker_images tool first to find the correct base image from Nexus, then use the Nexus registry path (e.g. localhost:5001/apm-repo/demo/imagename:tag) as the FROM image.
3. NEVER use public Docker Hub images (like FROM python:3.11-slim). Always use the private registry path.
4. If no matching image is found in Nexus, inform the user that the image is not available in their private registry and suggest they add it.
5. The private registry URL format is: localhost:5001/<repository>:<tag>
"""

TOOL_ID = "nexus_docker_images"

for row in rows:
    model_id = row[0]
    model_name = row[1]
    params = json.loads(row[2]) if row[2] else {}
    meta = json.loads(row[3]) if row[3] else {}

    # Update system prompt in params
    params["system"] = SYSTEM_PROMPT

    # Attach tool in meta
    if "toolIds" not in meta:
        meta["toolIds"] = []
    if TOOL_ID not in meta["toolIds"]:
        meta["toolIds"].append(TOOL_ID)

    # Remove old tool if present
    if "nexus_python_images" in meta.get("toolIds", []):
        meta["toolIds"].remove("nexus_python_images")

    # Update DB
    conn.execute(
        "UPDATE model SET params = ?, meta = ? WHERE id = ?",
        (json.dumps(params), json.dumps(meta), model_id)
    )
    print(f"Updated {model_name}: toolIds={meta['toolIds']}, system prompt set")

conn.commit()
conn.close()
print("\nDone! Both models now have the Nexus tool attached and system prompt configured.")
