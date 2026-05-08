# Golden Rules for AI-Driven Dockerfile & GitLab CI Generation

## NON-NEGOTIABLE CONSTRAINTS

### 1. Private Registry Only
- **NEVER** use public registry base images (docker.io, ghcr.io, etc.)
- **ALL** base images MUST come from Nexus private registry
- Format: `localhost:5001/apm-repo/demo/<image>:<tag>`

### 2. No Imagination/Guessing
- Do NOT invent tags - tags MUST come from Nexus catalog
- Do NOT invent pipeline stages - use only stored templates
- If template missing: return `TEMPLATE_MISSING` error

### 3. Security & Secrets
- Secrets MUST NEVER appear in generated files
- Use GitLab CI variables and environment variables only
- No hardcoded credentials, tokens, or passwords

### 4. Required Pipeline Stages (Java)
- build
- security_scan (bandit/safety/gitleaks/semgrep)
- code_quality (sonarqube)
- docker_build
- docker_scan (trivy/grype)
- docker_push (to Nexus)

### 5. Validation Gates
- Validate YAML/Dockerfile syntax
- Block any public registry FROM statements
- Ensure required stages present
- Parse check before returning output

### 6. Audit & Observability
- Log: request_id, template_id, base_image, tag, validation_result
- Return: commit SHA, pipeline URL, MR URL (if applicable)
