import requests
import json
from requests.auth import HTTPBasicAuth

# Nexus configuration
NEXUS_URL = "http://localhost:5001"
NEXUS_USER = "admin"
NEXUS_PASS = "r"

# Initialize catalog structure
catalog = {}

def get_repositories():
    """List all repositories in Nexus Docker registry"""
    try:
        response = requests.get(
            f"{NEXUS_URL}/v2/_catalog",
            auth=HTTPBasicAuth(NEXUS_USER, NEXUS_PASS),
            timeout=10
        )
        response.raise_for_status()
        repos = response.json().get('repositories', [])
        print(f"[OK] Found {len(repos)} repositories")
        return repos
    except Exception as e:
        print(f"[ERROR] Failed to get repositories: {e}")
        return []

def get_tags(repo_name):
    """Get all tags for a repository"""
    try:
        response = requests.get(
            f"{NEXUS_URL}/v2/{repo_name}/tags/list",
            auth=HTTPBasicAuth(NEXUS_USER, NEXUS_PASS),
            timeout=10
        )
        response.raise_for_status()
        tags = response.json().get('tags', [])
        return tags
    except Exception as e:
        print(f"[WARN] Failed to get tags for {repo_name}: {e}")
        return []

def extract_base_key(repo_name):
    """Extract base key from repository name"""
    # Example: apm-repo/demo/python -> python
    # Example: apm-repo/demo/eclipse-temurin -> temurin
    parts = repo_name.split('/')
    if len(parts) > 0:
        last_part = parts[-1]
        # Handle special cases
        if 'temurin' in last_part:
            return 'temurin'
        elif 'corretto' in last_part:
            return 'java'
        elif 'python' in last_part:
            return 'python'
        elif 'node' in last_part:
            return 'node'
        elif 'redis' in last_part:
            return 'redis'
        else:
            return last_part
    return 'unknown'

def select_preferred_tag(tags, base_key):
    """Select preferred tag based on base_key rules"""
    if not tags:
        return None
    
    # Define selection rules per base_key
    rules = {
        'python': ['3.12-slim', '3.11-slim', '3.12', '3.11'],
        'node': ['20-alpine', '18-alpine', '20', '18'],
        'java': ['17-alpine', '17', '11-alpine', '11'],
        'temurin': ['17-alpine', '17-jdk', '17'],
        'redis': ['7-alpine', '7', '6-alpine']
    }
    
    preferred = rules.get(base_key, [])
    
    # Try to match preferred tags
    for pref in preferred:
        for tag in tags:
            if pref in tag:
                return tag
    
    # Fallback to 'latest' or first tag
    if 'latest' in tags:
        return 'latest'
    return tags[0] if tags else None

# Main execution
print("=" * 60)
print("Nexus Catalog Refresh")
print("=" * 60)

repositories = get_repositories()

for repo in repositories:
    print(f"\n[INFO] Processing: {repo}")
    tags = get_tags(repo)
    
    if tags:
        base_key = extract_base_key(repo)
        selected_tag = select_preferred_tag(tags, base_key)
        
        catalog[base_key] = {
            "image_path": f"localhost:5001/{repo}",
            "tags": tags,
            "selected_tag": selected_tag,
            "selection_rule": f"preferred or latest"
        }
        print(f"  Base Key: {base_key}")
        print(f"  Tags: {len(tags)} found")
        print(f"  Selected: {selected_tag}")

# Write catalog to file
with open('catalog.json', 'w', encoding='utf-8') as f:
    json.dump(catalog, f, indent=2)

print("\n" + "=" * 60)
print(f"Catalog written to catalog.json")
print(f"Total base keys: {len(catalog)}")
print("=" * 60)

# Display summary
print("\nCatalog Summary:")
for key, info in catalog.items():
    print(f"  {key}: {info['selected_tag']} ({len(info['tags'])} tags available)")
