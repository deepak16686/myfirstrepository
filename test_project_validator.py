"""
Test script for Project Validator tool
Run this to verify the tool logic before deploying to Open WebUI
"""
import os
import requests
import urllib.parse

# Configuration - match the tool's defaults
SONARQUBE_URL = os.getenv("SONARQUBE_URL", "http://localhost:9002")
SONARQUBE_TOKEN = os.getenv("SONARQUBE_TOKEN", "")
GITLAB_URL = os.getenv("GITLAB_URL", "http://localhost:8929")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
NEXUS_URL = os.getenv("NEXUS_URL", "http://localhost:8081")
NEXUS_USER = os.getenv("NEXUS_USER", "admin")
NEXUS_PASS = os.getenv("NEXUS_PASS", "r")

TICKETING_PROVIDER = os.getenv("TICKETING_PROVIDER", "redmine")
TICKETING_CREATE_URL = os.getenv("TICKETING_CREATE_URL", "http://localhost:8090/issues/new")
REDMINE_PROJECT_ID = os.getenv("REDMINE_PROJECT_ID", "devops-requests")


def test_sonarqube_validation():
    """Test SonarQube project validation"""
    print("\n" + "="*60)
    print("Testing SonarQube Validation")
    print("="*60)

    # Test with existing project (if any)
    project_key = "legacy-banking-core"
    url = f"{SONARQUBE_URL}/api/projects/search"
    params = {"projects": project_key}

    try:
        resp = requests.get(url, params=params, timeout=10)
        print(f"\nEndpoint: {url}")
        print(f"Project Key: {project_key}")
        print(f"HTTP Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            components = data.get("components", [])
            if components:
                print(f"Result: PASS - Project exists")
                print(f"Project URL: {SONARQUBE_URL}/dashboard?id={project_key}")
            else:
                print(f"Result: FAIL - Project not found")
                _print_escalation("SonarQube", SONARQUBE_URL, project_key, 200, "Not in search results")
        else:
            print(f"Result: ERROR - {resp.text[:100]}")
    except Exception as e:
        print(f"Connection Error: {e}")

    # Test with non-existing project
    print("\n--- Testing with non-existing project ---")
    project_key = "non-existing-project-xyz"
    try:
        resp = requests.get(url, params={"projects": project_key}, timeout=10)
        print(f"Project Key: {project_key}")
        print(f"HTTP Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("components"):
                print("Result: FAIL - Project not found (expected)")
                _print_escalation("SonarQube", SONARQUBE_URL, project_key, 200, "Not in search results")
    except Exception as e:
        print(f"Connection Error: {e}")


def test_gitlab_validation():
    """Test GitLab project validation"""
    print("\n" + "="*60)
    print("Testing GitLab Validation")
    print("="*60)

    # Test with existing project
    project_path = "root/python-project"
    encoded_path = urllib.parse.quote(project_path, safe="")
    url = f"{GITLAB_URL}/api/v4/projects/{encoded_path}"

    try:
        resp = requests.get(url, timeout=10)
        print(f"\nEndpoint: {url}")
        print(f"Project Path: {project_path}")
        print(f"HTTP Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            print(f"Result: PASS - Project exists")
            print(f"Project URL: {data.get('web_url')}")
            print(f"Project ID: {data.get('id')}")
        elif resp.status_code == 404:
            print(f"Result: FAIL - Project not found")
            _print_escalation("GitLab", GITLAB_URL, project_path, 404, "Project not found")
        else:
            print(f"Result: ERROR - {resp.text[:100]}")
    except Exception as e:
        print(f"Connection Error: {e}")

    # Test with non-existing project
    print("\n--- Testing with non-existing project ---")
    project_path = "root/non-existing-project"
    encoded_path = urllib.parse.quote(project_path, safe="")
    url = f"{GITLAB_URL}/api/v4/projects/{encoded_path}"
    try:
        resp = requests.get(url, timeout=10)
        print(f"Project Path: {project_path}")
        print(f"HTTP Status: {resp.status_code}")
        if resp.status_code == 404:
            print("Result: FAIL - Project not found (expected)")
            _print_escalation("GitLab", GITLAB_URL, project_path, 404, "Project not found")
    except Exception as e:
        print(f"Connection Error: {e}")


def test_nexus_validation():
    """Test Nexus repository validation"""
    print("\n" + "="*60)
    print("Testing Nexus Validation")
    print("="*60)

    url = f"{NEXUS_URL}/service/rest/v1/repositories"
    auth = (NEXUS_USER, NEXUS_PASS)

    try:
        resp = requests.get(url, auth=auth, timeout=10)
        print(f"\nEndpoint: {url}")
        print(f"HTTP Status: {resp.status_code}")

        if resp.status_code == 200:
            repos = resp.json()
            print(f"Found {len(repos)} repositories")

            # Test existing repo
            repo_name = "apm-repo"
            matching = [r for r in repos if r.get("name") == repo_name]
            if matching:
                print(f"\nRepository '{repo_name}': PASS - Exists")
                print(f"Format: {matching[0].get('format')}")
            else:
                print(f"\nRepository '{repo_name}': FAIL - Not found")

            # Test non-existing repo
            repo_name = "non-existing-repo"
            matching = [r for r in repos if r.get("name") == repo_name]
            if not matching:
                print(f"\nRepository '{repo_name}': FAIL - Not found (expected)")
                _print_escalation("Nexus", NEXUS_URL, repo_name, 200, "Not in repository list")
        else:
            print(f"Result: ERROR - {resp.text[:100]}")
    except Exception as e:
        print(f"Connection Error: {e}")


def _print_escalation(platform, platform_url, project_key, http_code, error_detail):
    """Print escalation information"""
    print("\n--- ESCALATION INFO ---")

    ticket_title = f"[ProjectValidator] Create project and grant CI permissions: {project_key}"
    ticket_description = f"""## Project Creation Request

**Tool:** Project Validator
**Platform:** {platform}
**Platform URL:** {platform_url}
**Project Key/Name:** {project_key}

### Evidence
- HTTP Response Code: {http_code}
- Error Detail: {error_detail}
"""

    # Build ticket link
    if TICKETING_PROVIDER == "gitlab":
        params = urllib.parse.urlencode({
            "issue[title]": ticket_title,
            "issue[description]": ticket_description
        })
        ticket_link = f"{TICKETING_CREATE_URL}?{params}"
    else:
        ticket_link = TICKETING_CREATE_URL

    print(f"\nTicket Link: {ticket_link[:100]}...")
    print(f"\nTicket Title: {ticket_title}")
    print(f"\nNext Steps:")
    print("  1. Create project manually in the platform UI/API")
    print("  2. OR raise a ticket using the link above")


def test_ticketing_config():
    """Show current ticketing configuration"""
    print("\n" + "="*60)
    print("Ticketing Configuration")
    print("="*60)
    print(f"Provider: {TICKETING_PROVIDER}")
    print(f"Create Ticket URL: {TICKETING_CREATE_URL}")
    print(f"Redmine Project ID: {REDMINE_PROJECT_ID}")
    print(f"Supported Providers: gitlab, jira, redmine, servicenow, generic")


def test_redmine_connectivity():
    """Test Redmine connectivity"""
    print("\n" + "="*60)
    print("Testing Redmine Connectivity")
    print("="*60)

    redmine_url = TICKETING_CREATE_URL.replace("/issues/new", "")

    try:
        resp = requests.get(redmine_url, timeout=10)
        print(f"\nEndpoint: {redmine_url}")
        print(f"HTTP Status: {resp.status_code}")

        if resp.status_code == 200:
            print("Result: PASS - Redmine is accessible")
            print(f"Redmine URL: {redmine_url}")
            print("\nDefault credentials: admin / admin")
            print("First login will require password change.")
        else:
            print(f"Result: WARNING - Unexpected status code")
    except Exception as e:
        print(f"Connection Error: {e}")


if __name__ == "__main__":
    print("Project Validator Tool - Test Suite")
    print("="*60)

    test_ticketing_config()
    test_redmine_connectivity()
    test_sonarqube_validation()
    test_gitlab_validation()
    test_nexus_validation()

    print("\n" + "="*60)
    print("Tests completed!")
    print("="*60)
