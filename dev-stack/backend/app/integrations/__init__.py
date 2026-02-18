"""
File: __init__.py
Purpose: Package marker for the integrations layer, which provides async API client classes for every external tool in the DevOps platform (GitLab, Jenkins, Nexus, SonarQube, Trivy, Splunk, Jira, ChromaDB, GitHub/Gitea, Ollama, OpenAI, Claude Code, and HashiCorp Vault).
When Used: Imported transitively whenever any router, service, or the application config needs to talk to an external tool; the unified and connectivity routers instantiate most integrations at once for health-check dashboards.
Why Created: Groups all outbound API integrations into a single package so tool clients are decoupled from business logic in services and routers, making it easy to add new tools or swap implementations.
"""
