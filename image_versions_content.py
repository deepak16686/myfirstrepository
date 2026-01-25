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
                return tech + " image is not available in your private Nexus registry." + chr(10) + "Please upload the required image first:" + chr(10) + chr(10) + "docker pull " + tech + ":<tag>" + chr(10) + "docker tag " + tech + ":<tag> " + PULL_REGISTRY + "/apm-repo/demo/" + tech + ":<tag>" + chr(10) + "docker push " + PULL_REGISTRY + "/apm-repo/demo/" + tech + ":<tag>"

            results = []
            for repo in repos:
                resp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                all_tags = data.get("tags", [])
                sorted_tags = sort_tags(all_tags)
                latest_5 = sorted_tags[:5]
                results.append({"repository": data.get("name", repo), "total_tags": len(all_tags), "latest_5": latest_5})

            output = "Docker Image Versions from Private Nexus Registry:" + chr(10)
            output += "=" * 50 + chr(10) + chr(10)
            for r in results:
                output += "Image: " + PULL_REGISTRY + "/" + r["repository"] + chr(10)
                output += "Total versions available: " + str(r["total_tags"]) + chr(10)
                output += "Latest 5 versions:" + chr(10)
                for i, tag in enumerate(r["latest_5"], 1):
                    output += "  " + str(i) + ". " + PULL_REGISTRY + "/" + r["repository"] + ":" + tag + chr(10)
                output += chr(10)

            output += "---" + chr(10)
            output += "To update your Dockerfile, replace the FROM line with any of the above images." + chr(10)
            output += "Example: FROM " + PULL_REGISTRY + "/" + results[0]["repository"] + ":" + results[0]["latest_5"][0] + chr(10)
            output += "IMPORTANT: Only use images from the private Nexus registry. Never use public Docker Hub."
            return output

        except Exception as e:
            return "Error connecting to Nexus registry: " + str(e)