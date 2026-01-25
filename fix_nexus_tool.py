import textwrap, os
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR
from pathlib import Path

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"
TOOL_ID = "nexus_docker_images"

content = replace_imports(textwrap.dedent('''
"""
description: List Docker images from Nexus private registry
"""
import os, requests

REGISTRY = os.getenv("NEXUS_REGISTRY", "http://ai-nexus:5001").rstrip("/")
USER = os.getenv("NEXUS_USER", "admin")
PASS = os.getenv("NEXUS_PASS", "r")

class Tools:
    def list_docker_images(self, query: str = "") -> dict:
        """List available Docker images from the private Nexus registry. Pass a simple technology keyword like: python, node, nginx, java, golang, mongodb, redis, php, maven, postgres, alpine, ruby, rust, etc."""
        auth = (USER, PASS)
        try:
            catalog = requests.get(f"{REGISTRY}/v2/_catalog", auth=auth, timeout=10)
            catalog.raise_for_status()
            repos = catalog.json().get("repositories", [])
            if query:
                query_words = [w.lower().strip() for w in query.replace(",", " ").split() if len(w.strip()) > 1]
                matched_repos = []
                for repo in repos:
                    repo_lower = repo.lower()
                    for word in query_words:
                        if word in repo_lower:
                            matched_repos.append(repo)
                            break
                repos = matched_repos
            results = []
            for repo in repos:
                resp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                results.append({
                    "repository": data.get("name", repo),
                    "tags": data.get("tags", []),
                    "pull_path": f"localhost:5001/{data.get('name', repo)}",
                    "source": "nexus-private-registry"
                })
            if not results:
                return {"images": [], "message": "No image available in the private registry. Please add it to your Nexus repository first.", "source": "nexus-private-registry"}
            return {"images": results, "source": "nexus-private-registry"}
        except Exception as e:
            return {"error": str(e), "source": "nexus-private-registry"}
''').strip())

meta = ToolMeta(description="List Docker images from Nexus private registry")
form = ToolForm(id=TOOL_ID, name="Nexus Docker Images", content=content, meta=meta, access_control=None)

existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)

module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
