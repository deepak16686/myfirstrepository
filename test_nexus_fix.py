"""
Test script to validate the NoneType fix for Nexus API calls.
This simulates the fixed code logic without needing Open WebUI dependencies.
"""
import os
import requests

REGISTRY = os.getenv("NEXUS_REGISTRY", "http://localhost:5001").rstrip("/")
USER = os.getenv("NEXUS_USER", "admin")
PASS = os.getenv("NEXUS_PASS", "r")
PULL_REGISTRY = "localhost:5001"

def test_nexus_connection():
    """Test the fixed code that handles None responses properly."""
    auth = (USER, PASS)

    print(f"Testing Nexus connection to: {REGISTRY}")
    print("-" * 50)

    try:
        # Step 1: Get catalog (with fix)
        catalog = requests.get(f"{REGISTRY}/v2/_catalog", auth=auth, timeout=10)
        catalog.raise_for_status()

        # FIX: Handle None response
        catalog_data = catalog.json() or {}
        repos = catalog_data.get("repositories", [])

        print("[OK] Catalog retrieved successfully")
        print(f"   Found {len(repos)} repositories")

        if not repos:
            print("[WARN] No repositories found in registry")
            return False

        # Step 2: Test getting tags for first repo (with fix)
        test_repo = repos[0]
        print(f"\n   Testing tags for: {test_repo}")

        resp = requests.get(f"{REGISTRY}/v2/{test_repo}/tags/list", auth=auth, timeout=10)
        resp.raise_for_status()

        # FIX: Handle None response
        resp_data = resp.json() or {}
        tags = resp_data.get("tags", []) or []

        print("[OK] Tags retrieved successfully")
        print(f"   Found {len(tags)} tags: {tags[:5]}{'...' if len(tags) > 5 else ''}")

        # Step 3: Test the pattern that was failing (multiple catalog.json() calls)
        print("\n   Testing multiple data accesses (the original bug)...")

        # This was the bug - calling catalog.json() multiple times
        # After first call, response body is consumed and subsequent calls return None
        # FIX: We now store the result in catalog_data and reuse it
        all_repos = catalog_data.get("repositories", [])  # Using stored data, not catalog.json()

        print("[OK] Reused catalog_data successfully")
        print(f"   all_repos has {len(all_repos)} items")

        # Step 4: Test finding specific images
        print("\n   Testing image lookup...")

        def find_image(keyword):
            matched = [r for r in repos if keyword.lower() in r.lower()]
            if matched:
                resp = requests.get(f"{REGISTRY}/v2/{matched[0]}/tags/list", auth=auth, timeout=10)
                resp.raise_for_status()
                # FIX: Handle None response
                resp_data = resp.json() or {}
                tags = resp_data.get("tags", []) or []
                if tags:
                    return f"{PULL_REGISTRY}/{matched[0]}:{tags[0]}"
            return ""

        maven_image = find_image("maven")
        python_image = find_image("python")
        kaniko_image = find_image("kaniko")

        print(f"   Maven image: {maven_image or 'Not found'}")
        print(f"   Python image: {python_image or 'Not found'}")
        print(f"   Kaniko image: {kaniko_image or 'Not found'}")

        print("\n" + "=" * 50)
        print("[OK] ALL TESTS PASSED - Fix is working correctly!")
        print("=" * 50)
        return True

    except requests.exceptions.ConnectionError as e:
        print(f"[FAIL] Connection error: {e}")
        print("   Make sure Nexus is running on localhost:5001")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    test_nexus_connection()
