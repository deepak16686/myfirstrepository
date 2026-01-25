import textwrap
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"
TOOL_ID = "nexus_image_versions"

content = replace_imports(textwrap.dedent('''
"""
description: Search Docker images in Nexus registry and show last 5 latest versions
"""
import os, requests, re

REGISTRY = os.getenv("NEXUS_REGISTRY", "http://ai-nexus:5001").rstrip("/")
USER = os.getenv("NEXUS_USER", "admin")
PASS = os.getenv("NEXUS_PASS", "r")
PULL_REGISTRY = "localhost:5001"

def sort_tags(tags):
    def version_key(tag):
        parts = re.findall(r"[0-9]+", tag)
        return [int(p) for p in parts] if parts else [0]
    try:
        sorted_tags = sorted(tags, key=version_key, reverse=True)
    except:
        sorted_tags = sorted(tags, reverse=True)
    return sorted_tags

class Tools:
    def search_image_versions(self, query: str = "") -> str:
        """Search Docker images in private Nexus registry and show last 5 latest versions. Pass a keyword: python, node, java, golang, ruby, gradle, nginx, alpine, etc."""
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

            if not repos:
                tech = query.strip()
                return f"{tech} image is not available in your private Nexus registry.
Please upload the required image first:

docker pull {tech}:<tag>
docker tag {tech}:<tag> {PULL_REGISTRY}/apm-repo/demo/{tech}:<tag>
docker push {PULL_REGISTRY}/apm-repo/demo/{tech}:<tag>"

            results = []
            for repo in repos:
                resp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                all_tags = data.get("tags", [])
                sorted_tags = sort_tags(all_tags)
                latest_5 = sorted_tags[:5]
                results.append({
                    "repository": data.get("name", repo),
                    "total_tags": len(all_tags),
                    "latest_5": latest_5
                })

            output = "Docker Image Versions from Private Nexus Registry:
"
            output += "=" * 50 + "

"
            for r in results:
                output += f"Image: {PULL_REGISTRY}/{r[\"repository\"]}
"
                output += f"Total versions available: {r[\"total_tags\"]}
"
                output += "Latest 5 versions:
"
                for i, tag in enumerate(r[\"latest_5\"], 1):
                    output += f"  {i}. {PULL_REGISTRY}/{r[\"repository\"]}:{tag}
"
                output += "
"
            
            output += "---
"
            output += "To update your Dockerfile, replace the FROM line with any of the above images.
"
            output += f"Example: FROM {PULL_REGISTRY}/{results[0][\"repository\"]}:{results[0][\"latest_5\"][0]}
"
            output += "IMPORTANT: Only use images from the private Nexus registry. Never use public Docker Hub."
            return output

        except Exception as e:
            return f"Error connecting to Nexus registry: {str(e)}"
'''  ).strip())

meta = ToolMeta(description="Search Docker images in Nexus registry and show last 5 latest versions")
form = ToolForm(id=TOOL_ID, name="Nexus Image Versions", content=content, meta=meta, access_control=None)

existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)

module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
