"""
Deploy Project Validator tool and model to Open WebUI
Run this inside the Open WebUI container or with access to the webui.db
"""
import subprocess
import sys

def run_script(script_path, description):
    """Run a Python script and report result"""
    print(f"\n{'='*60}")
    print(f"Deploying: {description}")
    print('='*60)

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"SUCCESS: {result.stdout}")
        else:
            print(f"FAILED: {result.stderr}")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

    return True

def main():
    print("="*60)
    print("Project Validator - Deployment Script")
    print("="*60)

    # Deploy tool first
    tool_success = run_script(
        "create_project_validator_tool.py",
        "Project Validator Tool"
    )

    if not tool_success:
        print("\nWARNING: Tool deployment may have failed. Model will still be deployed.")

    # Deploy model
    model_success = run_script(
        "create_project_validator_model.py",
        "Project Validator Model"
    )

    print("\n" + "="*60)
    print("Deployment Summary")
    print("="*60)
    print(f"Tool (project_validator):  {'SUCCESS' if tool_success else 'FAILED'}")
    print(f"Model (project-validator): {'SUCCESS' if model_success else 'FAILED'}")

    print("\n" + "="*60)
    print("Configuration")
    print("="*60)
    print("""
Environment variables to configure:

# Platform URLs
SONARQUBE_URL=http://ai-sonarqube:9000
GITLAB_URL=http://gitlab-server
NEXUS_URL=http://ai-nexus:8081

# Authentication
SONARQUBE_TOKEN=your-sonarqube-token
GITLAB_TOKEN=your-gitlab-token
NEXUS_USER=admin
NEXUS_PASS=your-password

# Ticketing Configuration
TICKETING_PROVIDER=gitlab  # Options: gitlab, jira, servicenow, generic
TICKETING_CREATE_URL=http://your-gitlab/group/project/-/issues/new
JIRA_PROJECT_KEY=DEVOPS  # Only for Jira provider
""")

    print("\n" + "="*60)
    print("Usage Examples")
    print("="*60)
    print("""
In Open WebUI chat with the "Project Validator" model:

1. Validate SonarQube project:
   "Check if legacy-banking-core exists in SonarQube"

2. Validate GitLab project:
   "Validate root/my-service in GitLab"

3. Validate Nexus repository:
   "Does apm-repo exist in Nexus?"

4. Show ticketing config:
   "Show ticketing configuration"

When a project is missing, the model will provide:
- Manual creation steps (UI + API)
- Ready-to-copy ticket payload
- Prefilled ticket link (for GitLab/Jira)
""")

if __name__ == "__main__":
    main()
