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
        """List available Docker images from the private Nexus registry. Use query to filter by image name (e.g. python, node, nginx, java, maven, redis, postgres, alpine etc). Leave empty to list all images."""
        auth = (USER, PASS)
        try:
            catalog = requests.get(f"{REGISTRY}/v2/_catalog", auth=auth, timeout=10)
            catalog.raise_for_status()
            repos = catalog.json().get("repositories", [])
            if query:
                repos = [r for r in repos if query.lower() in r.lower()]
            results = []
            for repo in repos:
                resp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                results.append({
                    "repository": data.get("name", repo),
                    "tags": data.get("tags", []),
                    "source": "nexus-private-registry"
                })
            if not results:
                return {"images": [], "note": "No matching images found in Nexus private registry", "source": "nexus-private-registry"}
            return {"images": results, "source": "nexus-private-registry"}
        except Exception as e:
            return {"error": str(e), "source": "nexus-private-registry"}
''').strip())

meta = ToolMeta(description="List Docker images from Nexus private registry")
form = ToolForm(id=TOOL_ID, name="Nexus Docker Images", content=content, meta=meta, access_control=None)

# Delete old tools
existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)
    print("Deleted existing nexus_docker_images tool")

old_tool = Tools.get_tool_by_id("nexus_python_images")
if old_tool:
    Tools.delete_tool_by_id("nexus_python_images")
    print("Deleted old nexus_python_images tool")

# Create new generic tool
module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
