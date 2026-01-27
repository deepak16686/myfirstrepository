import textwrap, os
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR
from pathlib import Path

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"
TOOL_ID = "project_validator"

content = replace_imports(textwrap.dedent('''
"""
description: Validate projects in SonarQube, GitLab, and Nexus. Provides escalation guidance with ticket payloads when projects are missing.
"""
import os, requests, json, urllib.parse
from typing import Optional

# Configuration
SONARQUBE_URL = os.getenv("SONARQUBE_URL", "http://ai-sonarqube:9000")
SONARQUBE_TOKEN = os.getenv("SONARQUBE_TOKEN", "")
GITLAB_URL = os.getenv("GITLAB_URL", "http://gitlab-server")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
NEXUS_URL = os.getenv("NEXUS_URL", "http://ai-nexus:8081")
NEXUS_USER = os.getenv("NEXUS_USER", "admin")
NEXUS_PASS = os.getenv("NEXUS_PASS", "r")

# Ticketing Configuration
TICKETING_PROVIDER = os.getenv("TICKETING_PROVIDER", "redmine")  # jira | servicenow | gitlab | redmine | generic
TICKETING_CREATE_URL = os.getenv("TICKETING_CREATE_URL", "http://localhost:8090/issues/new")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "DEVOPS")
REDMINE_PROJECT_ID = os.getenv("REDMINE_PROJECT_ID", "devops-requests")
REDMINE_API_KEY = os.getenv("REDMINE_API_KEY", "701b636febd66b8335cc485b671c27984d31a10b")

class Tools:
    def validate_project(
        self,
        project_key: str,
        platform: str = "sonarqube",
        organization: str = "",
        branch: str = "main"
    ) -> dict:
        """
        Validate if a project exists in the specified platform.

        Args:
            project_key: The project key/name/path to validate
            platform: Platform to check - sonarqube, gitlab, or nexus
            organization: Organization/group (optional, for GitLab)
            branch: Branch name (optional, default: main)

        Returns:
            Validation result with status and escalation info if project missing
        """
        platform = platform.lower().strip()

        if platform == "sonarqube":
            return self._validate_sonarqube(project_key)
        elif platform == "gitlab":
            return self._validate_gitlab(project_key, organization)
        elif platform == "nexus":
            return self._validate_nexus(project_key)
        else:
            return {
                "status": "ERROR",
                "message": f"Unknown platform: {platform}. Supported: sonarqube, gitlab, nexus"
            }

    def _validate_sonarqube(self, project_key: str) -> dict:
        """Validate project exists in SonarQube"""
        url = f"{SONARQUBE_URL}/api/projects/search"
        params = {"projects": project_key}
        headers = {}

        if SONARQUBE_TOKEN:
            headers["Authorization"] = f"Bearer {SONARQUBE_TOKEN}"

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                components = data.get("components", [])

                if components and any(c.get("key") == project_key for c in components):
                    return {
                        "status": "PASS",
                        "platform": "SonarQube",
                        "project_key": project_key,
                        "message": f"Project '{project_key}' exists in SonarQube",
                        "project_url": f"{SONARQUBE_URL}/dashboard?id={project_key}"
                    }
                else:
                    return self._generate_escalation(
                        platform="SonarQube",
                        platform_url=SONARQUBE_URL,
                        project_key=project_key,
                        http_code=200,
                        error_detail="Project not found in search results"
                    )

            elif resp.status_code == 401:
                return {
                    "status": "ERROR",
                    "message": "Authentication failed. Check SONARQUBE_TOKEN.",
                    "http_code": 401
                }

            elif resp.status_code == 404:
                return self._generate_escalation(
                    platform="SonarQube",
                    platform_url=SONARQUBE_URL,
                    project_key=project_key,
                    http_code=404,
                    error_detail="API endpoint returned 404"
                )

            else:
                return self._generate_escalation(
                    platform="SonarQube",
                    platform_url=SONARQUBE_URL,
                    project_key=project_key,
                    http_code=resp.status_code,
                    error_detail=resp.text[:200]
                )

        except requests.exceptions.RequestException as e:
            return {
                "status": "ERROR",
                "message": f"Connection failed to SonarQube: {str(e)}"
            }

    def validate_sonarqube_config(self, project_key: str) -> dict:
        """
        Validate full SonarQube project configuration including quality gate, quality profile, and metrics.

        Args:
            project_key: The SonarQube project key to validate

        Returns:
            Complete configuration validation report with status and recommendations
        """
        headers = {}
        if SONARQUBE_TOKEN:
            headers["Authorization"] = f"Bearer {SONARQUBE_TOKEN}"

        result = {
            "project_key": project_key,
            "platform": "SonarQube",
            "platform_url": SONARQUBE_URL,
            "validation_results": [],
            "overall_status": "PASS",
            "recommendations": []
        }

        # 1. Check if project exists
        project_check = self._validate_sonarqube(project_key)
        if project_check.get("status") != "PASS":
            return project_check

        result["project_url"] = f"{SONARQUBE_URL}/dashboard?id={project_key}"

        # 2. Get Quality Gate status
        qg_result = self._get_sonarqube_quality_gate(project_key, headers)
        result["validation_results"].append(qg_result)
        if qg_result.get("status") == "FAIL":
            result["overall_status"] = "FAIL"
            result["recommendations"].append("Fix quality gate issues before deployment")

        # 3. Get Quality Profile
        qp_result = self._get_sonarqube_quality_profile(project_key, headers)
        result["validation_results"].append(qp_result)

        # 4. Get Project Metrics
        metrics_result = self._get_sonarqube_metrics(project_key, headers)
        result["validation_results"].append(metrics_result)

        # 5. Get Issues Summary
        issues_result = self._get_sonarqube_issues(project_key, headers)
        result["validation_results"].append(issues_result)
        if issues_result.get("blockers", 0) > 0 or issues_result.get("critical", 0) > 0:
            result["overall_status"] = "WARNING"
            result["recommendations"].append(f"Fix {issues_result.get('blockers', 0)} blocker and {issues_result.get('critical', 0)} critical issues")

        # 6. Check last analysis date
        analysis_result = self._get_sonarqube_last_analysis(project_key, headers)
        result["validation_results"].append(analysis_result)

        return result

    def _get_sonarqube_quality_gate(self, project_key: str, headers: dict) -> dict:
        """Get SonarQube quality gate status for a project"""
        url = f"{SONARQUBE_URL}/api/qualitygates/project_status"
        params = {"projectKey": project_key}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                qg_status = data.get("projectStatus", {})
                status = qg_status.get("status", "UNKNOWN")
                conditions = qg_status.get("conditions", [])

                failed_conditions = [c for c in conditions if c.get("status") == "ERROR"]

                return {
                    "check": "Quality Gate",
                    "status": "PASS" if status == "OK" else "FAIL",
                    "quality_gate_status": status,
                    "total_conditions": len(conditions),
                    "failed_conditions": len(failed_conditions),
                    "failed_details": failed_conditions[:5] if failed_conditions else []
                }
            else:
                return {
                    "check": "Quality Gate",
                    "status": "ERROR",
                    "message": f"Failed to get quality gate: HTTP {resp.status_code}"
                }
        except Exception as e:
            return {"check": "Quality Gate", "status": "ERROR", "message": str(e)}

    def _get_sonarqube_quality_profile(self, project_key: str, headers: dict) -> dict:
        """Get SonarQube quality profile assigned to a project"""
        url = f"{SONARQUBE_URL}/api/qualityprofiles/search"
        params = {"project": project_key}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                profiles = data.get("profiles", [])

                return {
                    "check": "Quality Profile",
                    "status": "PASS" if profiles else "WARNING",
                    "profiles": [
                        {
                            "name": p.get("name"),
                            "language": p.get("language"),
                            "is_default": p.get("isDefault", False),
                            "active_rules": p.get("activeRuleCount", 0)
                        }
                        for p in profiles
                    ]
                }
            else:
                return {
                    "check": "Quality Profile",
                    "status": "ERROR",
                    "message": f"Failed to get quality profile: HTTP {resp.status_code}"
                }
        except Exception as e:
            return {"check": "Quality Profile", "status": "ERROR", "message": str(e)}

    def _get_sonarqube_metrics(self, project_key: str, headers: dict) -> dict:
        """Get key SonarQube metrics for a project"""
        url = f"{SONARQUBE_URL}/api/measures/component"
        metrics = "coverage,duplicated_lines_density,code_smells,bugs,vulnerabilities,security_hotspots,ncloc,sqale_rating,reliability_rating,security_rating"
        params = {"component": project_key, "metricKeys": metrics}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                measures = data.get("component", {}).get("measures", [])

                metrics_dict = {m.get("metric"): m.get("value") for m in measures}

                return {
                    "check": "Project Metrics",
                    "status": "PASS",
                    "coverage": metrics_dict.get("coverage", "N/A"),
                    "duplicated_lines": metrics_dict.get("duplicated_lines_density", "N/A"),
                    "code_smells": metrics_dict.get("code_smells", "0"),
                    "bugs": metrics_dict.get("bugs", "0"),
                    "vulnerabilities": metrics_dict.get("vulnerabilities", "0"),
                    "security_hotspots": metrics_dict.get("security_hotspots", "0"),
                    "lines_of_code": metrics_dict.get("ncloc", "0"),
                    "maintainability_rating": metrics_dict.get("sqale_rating", "N/A"),
                    "reliability_rating": metrics_dict.get("reliability_rating", "N/A"),
                    "security_rating": metrics_dict.get("security_rating", "N/A")
                }
            else:
                return {
                    "check": "Project Metrics",
                    "status": "ERROR",
                    "message": f"Failed to get metrics: HTTP {resp.status_code}"
                }
        except Exception as e:
            return {"check": "Project Metrics", "status": "ERROR", "message": str(e)}

    def _get_sonarqube_issues(self, project_key: str, headers: dict) -> dict:
        """Get SonarQube issues summary for a project"""
        url = f"{SONARQUBE_URL}/api/issues/search"
        params = {"componentKeys": project_key, "resolved": "false", "ps": 1, "facets": "severities"}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("total", 0)
                facets = data.get("facets", [])

                severity_counts = {}
                for facet in facets:
                    if facet.get("property") == "severities":
                        for value in facet.get("values", []):
                            severity_counts[value.get("val", "").lower()] = value.get("count", 0)

                return {
                    "check": "Open Issues",
                    "status": "PASS" if severity_counts.get("blocker", 0) == 0 else "WARNING",
                    "total_open": total,
                    "blockers": severity_counts.get("blocker", 0),
                    "critical": severity_counts.get("critical", 0),
                    "major": severity_counts.get("major", 0),
                    "minor": severity_counts.get("minor", 0),
                    "info": severity_counts.get("info", 0)
                }
            else:
                return {
                    "check": "Open Issues",
                    "status": "ERROR",
                    "message": f"Failed to get issues: HTTP {resp.status_code}"
                }
        except Exception as e:
            return {"check": "Open Issues", "status": "ERROR", "message": str(e)}

    def _get_sonarqube_last_analysis(self, project_key: str, headers: dict) -> dict:
        """Get last analysis date for a SonarQube project"""
        url = f"{SONARQUBE_URL}/api/project_analyses/search"
        params = {"project": project_key, "ps": 1}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                analyses = data.get("analyses", [])

                if analyses:
                    last_analysis = analyses[0]
                    return {
                        "check": "Last Analysis",
                        "status": "PASS",
                        "date": last_analysis.get("date", "Unknown"),
                        "events": [e.get("name") for e in last_analysis.get("events", [])]
                    }
                else:
                    return {
                        "check": "Last Analysis",
                        "status": "WARNING",
                        "message": "No analysis found - project may not have been scanned yet"
                    }
            else:
                return {
                    "check": "Last Analysis",
                    "status": "ERROR",
                    "message": f"Failed to get analysis history: HTTP {resp.status_code}"
                }
        except Exception as e:
            return {"check": "Last Analysis", "status": "ERROR", "message": str(e)}

    def list_sonarqube_projects(self) -> dict:
        """List all projects in SonarQube"""
        url = f"{SONARQUBE_URL}/api/projects/search"
        headers = {}
        if SONARQUBE_TOKEN:
            headers["Authorization"] = f"Bearer {SONARQUBE_TOKEN}"

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                projects = data.get("components", [])
                return {
                    "status": "PASS",
                    "total": len(projects),
                    "projects": [
                        {
                            "key": p.get("key"),
                            "name": p.get("name"),
                            "qualifier": p.get("qualifier"),
                            "last_analysis": p.get("lastAnalysisDate", "Never")
                        }
                        for p in projects
                    ]
                }
            elif resp.status_code == 401:
                return {"status": "ERROR", "message": "Authentication required. Set SONARQUBE_TOKEN."}
            else:
                return {"status": "ERROR", "message": f"Failed to list projects: HTTP {resp.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def _validate_gitlab(self, project_path: str, organization: str = "") -> dict:
        """Validate project exists in GitLab"""
        full_path = f"{organization}/{project_path}" if organization else project_path
        encoded_path = urllib.parse.quote(full_path, safe="")
        url = f"{GITLAB_URL}/api/v4/projects/{encoded_path}"
        headers = {}

        if GITLAB_TOKEN:
            headers["PRIVATE-TOKEN"] = GITLAB_TOKEN

        try:
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "PASS",
                    "platform": "GitLab",
                    "project_key": full_path,
                    "message": f"Project '{full_path}' exists in GitLab",
                    "project_url": data.get("web_url", f"{GITLAB_URL}/{full_path}"),
                    "project_id": data.get("id"),
                    "default_branch": data.get("default_branch", "main")
                }

            elif resp.status_code == 404:
                return self._generate_escalation(
                    platform="GitLab",
                    platform_url=GITLAB_URL,
                    project_key=full_path,
                    http_code=404,
                    error_detail="Project not found"
                )

            elif resp.status_code == 401:
                return {
                    "status": "ERROR",
                    "message": "Authentication failed. Check GITLAB_TOKEN.",
                    "http_code": 401
                }

            else:
                return self._generate_escalation(
                    platform="GitLab",
                    platform_url=GITLAB_URL,
                    project_key=full_path,
                    http_code=resp.status_code,
                    error_detail=resp.text[:200]
                )

        except requests.exceptions.RequestException as e:
            return {
                "status": "ERROR",
                "message": f"Connection failed to GitLab: {str(e)}"
            }

    def _validate_nexus(self, repository_name: str) -> dict:
        """Validate repository exists in Nexus"""
        url = f"{NEXUS_URL}/service/rest/v1/repositories"
        auth = (NEXUS_USER, NEXUS_PASS) if NEXUS_USER else None

        try:
            resp = requests.get(url, auth=auth, timeout=10)

            if resp.status_code == 200:
                repos = resp.json()
                matching = [r for r in repos if r.get("name") == repository_name]

                if matching:
                    return {
                        "status": "PASS",
                        "platform": "Nexus",
                        "project_key": repository_name,
                        "message": f"Repository '{repository_name}' exists in Nexus",
                        "repository_url": f"{NEXUS_URL}/#browse/browse:{repository_name}",
                        "format": matching[0].get("format"),
                        "type": matching[0].get("type")
                    }
                else:
                    return self._generate_escalation(
                        platform="Nexus",
                        platform_url=NEXUS_URL,
                        project_key=repository_name,
                        http_code=200,
                        error_detail="Repository not found in list"
                    )

            elif resp.status_code == 401:
                return {
                    "status": "ERROR",
                    "message": "Authentication failed. Check NEXUS_USER/NEXUS_PASS.",
                    "http_code": 401
                }

            else:
                return self._generate_escalation(
                    platform="Nexus",
                    platform_url=NEXUS_URL,
                    project_key=repository_name,
                    http_code=resp.status_code,
                    error_detail=resp.text[:200]
                )

        except requests.exceptions.RequestException as e:
            return {
                "status": "ERROR",
                "message": f"Connection failed to Nexus: {str(e)}"
            }

    def _generate_escalation(
        self,
        platform: str,
        platform_url: str,
        project_key: str,
        http_code: int,
        error_detail: str
    ) -> dict:
        """Generate escalation response with ticket payload when project is missing"""

        # Build ticket payload
        ticket_title = f"[ProjectValidator] Create project and grant CI permissions: {project_key}"

        ticket_description = f"""## Project Creation Request

**Tool:** Project Validator
**Platform:** {platform}
**Platform URL:** {platform_url}
**Project Key/Name:** {project_key}

### Evidence
- **Endpoint Called:** {platform_url}/api/...
- **HTTP Response Code:** {http_code}
- **Error Detail:** {error_detail}
- **Validation Time:** Auto-generated by Project Validator tool

### Requested Actions
1. Create the project/repository '{project_key}' in {platform}
2. Configure appropriate permissions for CI/CD service accounts
3. Enable required integrations (webhooks, API access)

### Business Justification
This project is required for CI/CD pipeline execution. The automated validation detected that the project does not exist and requires manual creation.
"""

        acceptance_criteria = """### Acceptance Criteria
- [ ] Project '{project_key}' is created in {platform}
- [ ] CI/CD service account has read/write permissions
- [ ] Project is accessible via API (validation passes)
- [ ] Webhooks configured (if applicable)
- [ ] Project settings match organization standards
""".format(project_key=project_key, platform=platform)

        # Build ticket link based on provider
        ticket_link = self._build_ticket_link(ticket_title, ticket_description, acceptance_criteria)

        # Build create project guidance
        create_project_guide = self._get_create_project_guide(platform, project_key, platform_url)

        return {
            "status": "FAIL",
            "verdict": "Project missing",
            "platform": platform,
            "platform_url": platform_url,
            "project_key": project_key,
            "http_code": http_code,
            "error_detail": error_detail,
            "next_steps": "Create project manually OR raise a ticket",
            "create_project_guide": create_project_guide,
            "ticket": {
                "provider": TICKETING_PROVIDER,
                "create_ticket_url": ticket_link,
                "payload": {
                    "title": ticket_title,
                    "description": ticket_description,
                    "acceptance_criteria": acceptance_criteria
                }
            }
        }

    def _build_ticket_link(self, title: str, description: str, acceptance_criteria: str) -> str:
        """Build ticket creation link based on provider"""

        if not TICKETING_CREATE_URL:
            return "Ticket link not configured. Set TICKETING_CREATE_URL environment variable."

        full_description = description + "\\n\\n" + acceptance_criteria

        if TICKETING_PROVIDER == "gitlab":
            # GitLab issue prefill
            params = urllib.parse.urlencode({
                "issue[title]": title,
                "issue[description]": full_description
            })
            return f"{TICKETING_CREATE_URL}?{params}"

        elif TICKETING_PROVIDER == "jira":
            # Jira create issue prefill (if supported)
            params = urllib.parse.urlencode({
                "summary": title,
                "description": full_description,
                "pid": JIRA_PROJECT_KEY
            })
            return f"{TICKETING_CREATE_URL}?{params}"

        elif TICKETING_PROVIDER == "redmine":
            # Redmine issue prefill
            params = urllib.parse.urlencode({
                "issue[subject]": title,
                "issue[description]": full_description,
                "issue[project_id]": REDMINE_PROJECT_ID
            })
            return f"{TICKETING_CREATE_URL}?{params}"

        elif TICKETING_PROVIDER == "servicenow":
            # ServiceNow - typically no prefill, return base URL
            return TICKETING_CREATE_URL

        else:
            # Generic - return base URL
            return TICKETING_CREATE_URL

    def _get_create_project_guide(self, platform: str, project_key: str, platform_url: str) -> dict:
        """Get platform-specific project creation guidance"""

        if platform == "SonarQube":
            return {
                "ui_steps": [
                    f"1. Navigate to {platform_url}",
                    "2. Click 'Create Project' or go to Administration > Projects",
                    f"3. Enter Project Key: {project_key}",
                    "4. Enter Display Name (can match project key)",
                    "5. Set visibility (Private recommended)",
                    "6. Click 'Set Up' and configure analysis method"
                ],
                "api_command": "curl -X POST " + platform_url + "/api/projects/create -H 'Authorization: Bearer $SONARQUBE_TOKEN' -d 'project=" + project_key + "&name=" + project_key + "'",
                "permissions_needed": [
                    "Execute Analysis",
                    "Browse Project",
                    "See Source Code (optional)"
                ]
            }

        elif platform == "GitLab":
            return {
                "ui_steps": [
                    f"1. Navigate to {platform_url}",
                    "2. Click 'New Project' (+ icon in top navbar)",
                    "3. Select 'Create blank project'",
                    f"4. Enter Project name: {project_key}",
                    "5. Select namespace/group",
                    "6. Set visibility level",
                    "7. Click 'Create project'"
                ],
                "api_command": "curl -X POST " + platform_url + "/api/v4/projects -H 'PRIVATE-TOKEN: $GITLAB_TOKEN' -d 'name=" + project_key + "&visibility=private'",
                "permissions_needed": [
                    "Developer or Maintainer role for CI/CD",
                    "Push access to repository",
                    "Pipeline trigger permissions"
                ]
            }

        elif platform == "Nexus":
            return {
                "ui_steps": [
                    f"1. Navigate to {platform_url}",
                    "2. Go to Administration (gear icon) > Repository > Repositories",
                    "3. Click 'Create repository'",
                    "4. Select repository format (docker, maven, npm, etc.)",
                    f"5. Enter Repository name: {project_key}",
                    "6. Configure storage and policies",
                    "7. Click 'Create repository'"
                ],
                "api_command": "See Nexus documentation for repository creation API",
                "permissions_needed": [
                    "nx-repository-view-*-*-read",
                    "nx-repository-view-*-*-browse",
                    "nx-repository-view-*-*-add (for push)"
                ]
            }

        return {"message": "No specific guidance available for this platform"}

    def get_ticketing_config(self) -> dict:
        """Return current ticketing configuration"""
        return {
            "provider": TICKETING_PROVIDER,
            "create_ticket_url": TICKETING_CREATE_URL if TICKETING_CREATE_URL else "NOT CONFIGURED",
            "jira_project_key": JIRA_PROJECT_KEY if TICKETING_PROVIDER == "jira" else "N/A",
            "redmine_project_id": REDMINE_PROJECT_ID if TICKETING_PROVIDER == "redmine" else "N/A",
            "supported_providers": ["gitlab", "jira", "redmine", "servicenow", "generic"]
        }

    def create_ticket_in_redmine(
        self,
        subject: str,
        description: str,
        project_id: str = "",
        tracker_id: int = 1,
        priority_id: int = 2
    ) -> dict:
        """
        Create a ticket directly in Redmine via API.

        Args:
            subject: Ticket subject/title
            description: Ticket description
            project_id: Redmine project identifier (default from config)
            tracker_id: Tracker ID (1=Bug, 2=Feature, 3=Support)
            priority_id: Priority ID (1=Low, 2=Normal, 3=High, 4=Urgent, 5=Immediate)

        Returns:
            Created ticket info or error
        """
        if not REDMINE_API_KEY:
            return {
                "status": "ERROR",
                "message": "REDMINE_API_KEY not configured. Set the environment variable or use manual ticket creation."
            }

        project = project_id if project_id else REDMINE_PROJECT_ID
        redmine_url = TICKETING_CREATE_URL.replace("/issues/new", "")

        url = f"{redmine_url}/issues.json"
        headers = {
            "Content-Type": "application/json",
            "X-Redmine-API-Key": REDMINE_API_KEY
        }

        payload = {
            "issue": {
                "project_id": project,
                "subject": subject,
                "description": description,
                "tracker_id": tracker_id,
                "priority_id": priority_id
            }
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)

            if resp.status_code == 201:
                data = resp.json()
                issue = data.get("issue", {})
                return {
                    "status": "SUCCESS",
                    "message": "Ticket created successfully in Redmine",
                    "ticket_id": issue.get("id"),
                    "ticket_url": f"{redmine_url}/issues/{issue.get('id')}",
                    "subject": issue.get("subject")
                }

            elif resp.status_code == 401:
                return {
                    "status": "ERROR",
                    "message": "Authentication failed. Check REDMINE_API_KEY.",
                    "http_code": 401
                }

            elif resp.status_code == 404:
                return {
                    "status": "ERROR",
                    "message": f"Project '{project}' not found in Redmine. Create it first.",
                    "http_code": 404
                }

            else:
                return {
                    "status": "ERROR",
                    "message": f"Failed to create ticket: {resp.text[:200]}",
                    "http_code": resp.status_code
                }

        except requests.exceptions.RequestException as e:
            return {
                "status": "ERROR",
                "message": f"Connection failed to Redmine: {str(e)}"
            }
''').strip())

meta = ToolMeta(description="Validate projects in SonarQube, GitLab, and Nexus. Provides escalation guidance with ticket payloads when projects are missing.")
form = ToolForm(id=TOOL_ID, name="Project Validator", content=content, meta=meta, access_control=None)

existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)

module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
