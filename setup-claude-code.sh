#!/usr/bin/env bash
###############################################################################
# setup-claude-code.sh
# One-shot setup for Claude Code enterprise configuration
# Sets up: settings.json, CLAUDE.md (17+ sections), SQLite task DB,
#          directory structures, global logs, and reports
#
# Usage:  chmod +x setup-claude-code.sh && ./setup-claude-code.sh
# Works:  Git Bash on Windows, WSL2, native Linux/macOS
###############################################################################

set -euo pipefail

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

print_step()    { echo -e "${BLUE}[STEP]${NC} $1"; }
print_success() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
print_header()  { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ─── Paths ───────────────────────────────────────────────────────────────────
CLAUDE_DIR="$HOME/.claude"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
TASK_LOG_DIR="$CLAUDE_DIR/task-log"
TASK_DB="$TASK_LOG_DIR/claude-tasks.db"
REPORTS_DIR="$CLAUDE_DIR/reports"

print_header "Claude Code Enterprise Setup"
echo -e "  Target: ${YELLOW}$CLAUDE_DIR${NC}"
echo -e "  Date:   $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ─── 1. Create Directory Structure ──────────────────────────────────────────
print_step "Creating directory structure..."
mkdir -p "$CLAUDE_DIR"
mkdir -p "$TASK_LOG_DIR"
mkdir -p "$REPORTS_DIR/sessions"
mkdir -p "$REPORTS_DIR/weekly"
mkdir -p "$REPORTS_DIR/combined"
print_success "Directories created"

# ─── 2. Create settings.json ────────────────────────────────────────────────
print_step "Creating settings.json..."

cat > "$SETTINGS_FILE" << 'SETTINGS_EOF'
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(*)",
      "Write(*)",
      "Edit(*)",
      "MultiEdit(*)",
      "Glob(*)",
      "Grep(*)",
      "LS(*)",
      "WebFetch(*)",
      "WebSearch(*)",
      "Task(*)"
    ],
    "deny": [],
    "defaultMode": "autoApprove",
    "disableBypassPermissionsMode": false,
    "additionalDirectories": [
      "/mnt/c",
      "/mnt/d",
      "/mnt/e",
      "/mnt/f",
      "/mnt/g",
      "/mnt/h",
      "/home",
      "/opt",
      "/etc",
      "/var",
      "/tmp"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "name": "track-file-changes",
        "description": "Log file operations for task tracking",
        "match_tools": ["Write", "Edit", "MultiEdit"],
        "command": "mkdir -p .claude/task-log && echo \"$(date '+%Y-%m-%d %H:%M:%S') | FILE | $CLAUDE_TOOL_NAME | $CLAUDE_FILE_PATH\" >> .claude/task-log/.file-changes.log 2>/dev/null || true"
      },
      {
        "name": "track-bash-commands",
        "description": "Log bash commands for task tracking",
        "match_tools": ["Bash"],
        "command": "mkdir -p .claude/task-log && echo \"$(date '+%Y-%m-%d %H:%M:%S') | BASH | executed\" >> .claude/task-log/.bash-history.log 2>/dev/null || true"
      }
    ]
  },
  "env": {
    "CLAUDE_CODE_MAX_CONTEXT_PERCENTAGE": "95",
    "GITLAB_URL": "https://your-gitlab-instance.com",
    "GITLAB_TOKEN": "your-gitlab-api-token",
    "CONTAINER_REGISTRY": "your-registry.com",
    "K8S_CLUSTER_DEV": "dev-cluster-context",
    "K8S_CLUSTER_PROD": "prod-cluster-context",
    "PROMETHEUS_URL": "http://prometheus.monitoring.svc:9090",
    "GRAFANA_URL": "http://grafana.monitoring.svc:3000",
    "GRAFANA_API_KEY": "your-grafana-api-key",
    "ELASTICSEARCH_URL": "http://elasticsearch.logging.svc:9200"
  }
}
SETTINGS_EOF

print_success "settings.json created"

# ─── 3. Create CLAUDE.md ────────────────────────────────────────────────────
print_step "Creating CLAUDE.md (enterprise standards)..."

cat > "$CLAUDE_MD" << 'CLAUDEMD_EOF'
# Claude Code — Enterprise Engineering Standards
# This file auto-configures Claude Code to follow production-grade patterns.
# Every project scaffolded by Claude Code MUST comply with these standards.

---

## RULE ZERO — Requirements-First Workflow (MANDATORY)

**BEFORE writing a single line of code, planning architecture, or creating any files — ASK QUESTIONS FIRST.**

### The Process (Non-Negotiable)

```
┌──────────────────────────────────────────────────────────────────┐
│  Step 1: DISCOVER — Ask questions until requirements are 100%    │
│  Step 2: CONFIRM  — Summarize understanding, get user approval   │
│  Step 3: PLAN     — Present architecture/tech decisions           │
│  Step 4: BUILD    — Only now start writing code                   │
└──────────────────────────────────────────────────────────────────┘
```

### Step 1: DISCOVER — Questions to Ask

For EVERY new project or major feature, gather answers for ALL of these:

**Business & Scope**
- What is the core problem this solves? Who are the end users?
- What are the must-have features for v1? What can wait for v2?
- Are there existing systems this must integrate with?
- What is the expected scale? (users, requests/sec, data volume)

**Technical Requirements**
- Any preferred languages, frameworks, or libraries?
- Database preference? (PostgreSQL, MongoDB, Redis, etc.)
- Authentication method? (JWT, OAuth2, SSO, API keys)
- Real-time requirements? (WebSocket, SSE, polling)
- File upload/storage needs? (local, S3, Azure Blob)
- Third-party APIs or services to integrate?

**Infrastructure & Deployment**
- Cloud provider preference? (Azure, AWS, GCP, on-prem)
- Domain/DNS setup available?
- CI/CD beyond GitLab? (GitHub Actions, Jenkins, etc.)
- SSL/TLS certificate handling?
- Environment-specific requirements? (dev vs prod differences)

**Design & UX**
- Any design mockups, wireframes, or Figma links?
- Branding requirements? (colors, fonts, logos)
- Mobile-responsive required?
- Accessibility requirements beyond WCAG 2.1 AA?
- Dark mode support?

**Data & Compliance**
- Sensitive data handling? (PII, PCI, HIPAA)
- Data retention policies?
- Audit logging requirements?
- Multi-tenancy needed?
- Backup and disaster recovery expectations?

### Step 2: CONFIRM — Before Proceeding

After gathering answers, present a summary:

```
═══════════════════════════════════════════════════════════
  PROJECT UNDERSTANDING — Please Confirm
═══════════════════════════════════════════════════════════
  Project:      [Name]
  Type:         [Web App / API / CLI / Full-Stack / etc.]
  Services:     [List of microservices identified]
  Tech Stack:   [Languages + frameworks per service]
  Database:     [DB choices per service]
  Auth:         [Auth strategy]
  Deployment:   [K8s on Azure AKS / etc.]
  Scale Target: [Expected load]

  Key Decisions:
  1. [Decision 1 — e.g., "Go for API Gateway due to high throughput"]
  2. [Decision 2 — e.g., "PostgreSQL for relational data, Redis for cache"]
  3. [Decision 3 — e.g., "Kafka for async event processing"]
═══════════════════════════════════════════════════════════
  Shall I proceed with this plan? (or adjust anything?)
═══════════════════════════════════════════════════════════
```

### Step 3: PLAN — Architecture Before Code

Only after user confirms, present:
- Service decomposition diagram (text-based)
- Database schema outline per service
- API endpoint inventory
- Infrastructure components (K8s resources, Terraform modules)
- Estimated file count and project structure preview

### Step 4: BUILD — Now Execute

Only after plan approval, begin scaffolding following all standards below.

### What Triggers This Workflow

| User Says                                    | Action                          |
|----------------------------------------------|---------------------------------|
| "Build me an app that..."                    | Full discovery (all questions)  |
| "Add a new service for..."                   | Scoped discovery (tech + infra) |
| "Create a feature that..."                   | Feature-scoped questions        |
| "Fix this bug" / "Refactor this"             | Skip — go straight to code      |
| "Add a button" / small UI change             | Skip — go straight to code      |

**Small fixes and trivial changes do NOT need this workflow.**
**New projects, new services, and major features ALWAYS need it.**

### If Requirements Are Incomplete

Never assume. Never guess. If the user says "build me a task manager":
- Do NOT assume it's a web app (could be CLI, mobile, API-only)
- Do NOT assume PostgreSQL (could need MongoDB, SQLite)
- Do NOT assume it needs auth (could be a personal tool)
- Do NOT assume any feature set — ASK

**The golden rule: 10 minutes of questions saves 10 hours of rework.**

---

## Architecture Standard — Microservices ALWAYS

**RULE: Never create monoliths. Every application = microservices architecture.**

When I describe ANY application idea, automatically decompose it into:
- **API Gateway** — single entry point, rate limiting, auth routing
- **Auth Service** — JWT/OAuth2, user management, RBAC
- **Core Service(s)** — domain-specific business logic (1 service per bounded context)
- **Notification Service** — email, SMS, push, Slack webhooks
- **Shared Libraries** — common utilities, error handling, logging

### Service Communication
- Synchronous: REST (OpenAPI 3.0) or gRPC for internal high-throughput
- Asynchronous: Kafka/RabbitMQ for event-driven workflows
- Service mesh: Istio sidecar for mTLS, traffic management

### Project Structure Standard

Every project MUST follow this directory structure:
```
project-root/
├── services/
│   ├── api-gateway/
│   │   ├── src/
│   │   ├── Dockerfile
│   │   ├── .env.example
│   │   └── README.md
│   ├── auth-service/
│   ├── core-service/
│   └── notification-service/
├── shared/
│   ├── proto/              # gRPC definitions
│   ├── openapi/            # OpenAPI specs
│   └── libraries/          # Shared packages
├── infrastructure/
│   ├── terraform/
│   │   ├── modules/
│   │   ├── environments/
│   │   │   ├── dev/
│   │   │   └── prod/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── backend.tf
│   ├── kubernetes/
│   │   ├── base/
│   │   │   ├── namespace.yaml
│   │   │   ├── network-policies.yaml
│   │   │   └── resource-quotas.yaml
│   │   └── overlays/
│   │       ├── dev/
│   │       └── prod/
│   └── helm/
│       └── charts/
├── monitoring/
│   ├── prometheus/
│   │   ├── rules/
│   │   └── alerts/
│   ├── grafana/
│   │   └── dashboards/
│   ├── alertmanager/
│   └── fluentd/
├── dashboards/
│   ├── debug-dashboard/        # port 9000
│   ├── credentials-dashboard/  # port 9001
│   ├── task-history/           # port 9002
│   └── journey-walkthrough/    # port 9003
├── scripts/
│   ├── setup.sh
│   ├── deploy.sh
│   └── seed-data.sh
├── docker-compose.yml
├── docker-compose.dev.yml
├── Makefile
├── .gitlab-ci.yml
├── .gitignore
└── README.md
```

---

## Kubernetes Standards

### Kustomize Structure (NOT raw YAML, NOT Helm for app manifests)
```
kubernetes/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── hpa.yaml
│   ├── network-policy.yaml
│   └── service-monitor.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   ├── patches/
    │   │   ├── replicas.yaml
    │   │   └── resources.yaml
    │   └── configmap.yaml
    └── prod/
        ├── kustomization.yaml
        ├── patches/
        │   ├── replicas.yaml
        │   └── resources.yaml
        └── configmap.yaml
```

### Every Deployment MUST have:
```yaml
# Resource Limits — MANDATORY
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"

# Health Probes — MANDATORY
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5

# Security Context — MANDATORY
securityContext:
  runAsNonRoot: true
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
```

### HPA (Horizontal Pod Autoscaler)
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: SERVICE_NAME-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: SERVICE_NAME
  minReplicas: 2         # dev: 1, prod: 2
  maxReplicas: 10        # dev: 3, prod: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### NetworkPolicy — MANDATORY per service
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: SERVICE_NAME-netpol
spec:
  podSelector:
    matchLabels:
      app: SERVICE_NAME
  policyTypes: ["Ingress", "Egress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-gateway
  egress:
    - to:
        - podSelector: {}
```

---

## GitLab CI/CD Standard

### Auto-create GitLab repo for EVERY new project
When scaffolding a project, automatically create a GitLab repo using the API:
```bash
curl -X POST "https://$GITLAB_URL/api/v4/projects" \
  -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  -d "name=$PROJECT_NAME" \
  -d "namespace_id=$GROUP_ID" \
  -d "visibility=private" \
  -d "initialize_with_readme=true"
```

### .gitlab-ci.yml — MANDATORY Pipeline
```yaml
stages:
  - validate
  - build
  - test
  - security-scan
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: ""

.docker-build: &docker-build
  image: docker:24-dind
  services:
    - docker:24-dind

validate:lint:
  stage: validate
  script:
    - make lint

validate:schema:
  stage: validate
  script:
    - make validate-k8s

build:docker:
  stage: build
  <<: *docker-build
  script:
    - docker build -t $CONTAINER_REGISTRY/$CI_PROJECT_NAME:$CI_COMMIT_SHA .
    - docker push $CONTAINER_REGISTRY/$CI_PROJECT_NAME:$CI_COMMIT_SHA

test:unit:
  stage: test
  script:
    - make test-unit

test:integration:
  stage: test
  script:
    - make test-integration
  allow_failure: false

security:sast:
  stage: security-scan
  script:
    - make security-scan
  artifacts:
    reports:
      sast: gl-sast-report.json

security:container:
  stage: security-scan
  script:
    - trivy image $CONTAINER_REGISTRY/$CI_PROJECT_NAME:$CI_COMMIT_SHA

deploy:dev:
  stage: deploy
  environment:
    name: dev
  script:
    - kubectl config use-context $K8S_CLUSTER_DEV
    - kustomize build infrastructure/kubernetes/overlays/dev | kubectl apply -f -
  only:
    - develop

deploy:prod:
  stage: deploy
  environment:
    name: prod
  script:
    - kubectl config use-context $K8S_CLUSTER_PROD
    - kustomize build infrastructure/kubernetes/overlays/prod | kubectl apply -f -
  only:
    - main
  when: manual
```
CLAUDEMD_EOF

print_success "CLAUDE.md created (sections 1-4)"

# ─── CLAUDE.md sections 5-8 ────────────────────────────────────────────────
print_step "Appending monitoring, EFK, Dockerfile, code standards..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD5_EOF'

---

## Monitoring Standards — Prometheus + Grafana

### Every service MUST have a ServiceMonitor
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: SERVICE_NAME-monitor
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app: SERVICE_NAME
  endpoints:
    - port: metrics
      interval: 15s
      path: /metrics
```

### Grafana Dashboards — Auto-generated per service
Create 4 dashboard types for every project:
1. **Application Dashboard** — request rate, error rate, latency (RED metrics)
2. **Infrastructure Dashboard** — CPU, memory, disk, network per pod
3. **Business Dashboard** — domain-specific KPIs
4. **SLA Dashboard** — uptime, availability, response time percentiles

### Prometheus AlertRules — MANDATORY
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: SERVICE_NAME-alerts
spec:
  groups:
    - name: SERVICE_NAME.rules
      rules:
        - alert: HighErrorRate
          expr: rate(http_requests_total{status=~"5..",service="SERVICE_NAME"}[5m]) > 0.05
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "High error rate on SERVICE_NAME"
        - alert: HighLatency
          expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{service="SERVICE_NAME"}[5m])) > 1
          for: 5m
          labels:
            severity: warning
        - alert: PodCrashLooping
          expr: rate(kube_pod_container_status_restarts_total{namespace="PROJECT_NS"}[15m]) > 0
          for: 15m
          labels:
            severity: critical
```

---

## EFK Stack Standards — Structured Logging

### Fluentd DaemonSet — Collect from ALL pods
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd
  namespace: logging
spec:
  selector:
    matchLabels:
      app: fluentd
  template:
    spec:
      containers:
        - name: fluentd
          image: fluent/fluentd-kubernetes-daemonset:v1.16
          env:
            - name: FLUENT_ELASTICSEARCH_HOST
              value: "elasticsearch.logging.svc"
            - name: FLUENT_ELASTICSEARCH_PORT
              value: "9200"
          volumeMounts:
            - name: varlog
              mountPath: /var/log
            - name: containers
              mountPath: /var/lib/docker/containers
              readOnly: true
      volumes:
        - name: varlog
          hostPath:
            path: /var/log
        - name: containers
          hostPath:
            path: /var/lib/docker/containers
```

### Log Format — ALL services MUST use structured JSON
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "auth-service",
  "trace_id": "abc-123-def",
  "span_id": "span-456",
  "message": "User login successful",
  "metadata": {
    "user_id": "usr_789",
    "method": "POST",
    "path": "/api/v1/auth/login",
    "duration_ms": 145,
    "status_code": 200
  }
}
```

### Elasticsearch Index per Service
- Pattern: `logs-{service-name}-{date}`
- Retention: dev=7 days, prod=90 days
- Index lifecycle management (ILM) policy applied automatically

### Kibana Dashboards — Auto-created
1. Error log aggregation per service
2. Request/response timeline
3. Distributed trace view (correlate with Jaeger)

---

## Dockerfile Standards — Multi-Stage Builds

### Template (adapt per language)
```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

# Stage 2: Production
FROM node:20-alpine AS production
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8080/health || exit 1
CMD ["node", "dist/main.js"]
```

### Dockerfile Rules:
- ALWAYS multi-stage builds
- ALWAYS run as non-root user
- ALWAYS include HEALTHCHECK
- ALWAYS use specific version tags (no :latest)
- ALWAYS use alpine/slim base images
- ALWAYS .dockerignore alongside every Dockerfile

---

## Code Standards — Every Service

### Mandatory Endpoints
Every service MUST expose:
- `GET /health` — liveness check (returns 200 if alive)
- `GET /ready` — readiness check (returns 200 if dependencies ok)
- `GET /metrics` — Prometheus metrics endpoint
- `GET /info` — service version, build time, git sha

### Error Handling
- Use structured error responses everywhere:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Email format is invalid",
    "details": [{"field": "email", "constraint": "Must be valid email"}],
    "trace_id": "abc-123"
  }
}
```

### Observability
- OpenTelemetry SDK in every service for distributed tracing
- Trace context propagation (W3C TraceContext) across all service calls
- Custom metrics for business KPIs exported to Prometheus

### Security
- Input validation on ALL endpoints
- Rate limiting at API gateway level
- CORS configured explicitly (never wildcard in prod)
- Secrets via Kubernetes Secrets or external vault, never in code/env files

### 12-Factor App Compliance
All services MUST follow 12-factor methodology:
1. Codebase — one repo per service
2. Dependencies — explicitly declared
3. Config — environment variables
4. Backing services — attached resources via URLs
5. Build/release/run — strict separation
6. Processes — stateless
7. Port binding — self-contained
8. Concurrency — scale via process model
9. Disposability — fast startup, graceful shutdown
10. Dev/prod parity — minimize gaps
11. Logs — write to stdout
12. Admin processes — run as one-off tasks
CLAUDEMD5_EOF

print_success "Sections 5-8 appended"

# ─── CLAUDE.md sections 9-10 ───────────────────────────────────────────────
print_step "Appending IaC and environment standards..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD9_EOF'

---

## Infrastructure as Code (IaC) Standards — Terraform

### Terraform Project Structure
```
infrastructure/terraform/
├── modules/
│   ├── networking/         # VNet, subnets, NSGs
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── compute/            # AKS, VMs
│   ├── database/           # PostgreSQL, Redis, MongoDB
│   ├── security/           # Key Vault, managed identities
│   ├── monitoring/         # Log Analytics, Prometheus
│   └── gitlab-repo/        # Auto-create GitLab repos
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   └── prod/
│       ├── main.tf
│       ├── terraform.tfvars
│       └── backend.tf
├── main.tf
├── variables.tf
├── outputs.tf
└── versions.tf
```

### Module Standards
- Every module has: main.tf, variables.tf, outputs.tf, README.md
- Use semantic versioning for module sources
- Pin provider versions explicitly
- Use `terraform fmt` and `terraform validate` in CI

### Remote State — MANDATORY
```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstate"
    container_name       = "tfstate"
    key                  = "PROJECT_NAME/ENV/terraform.tfstate"
  }
}
```

### AKS Cluster Provisioning
```hcl
module "aks" {
  source              = "./modules/compute"
  cluster_name        = "${var.project_name}-${var.environment}"
  kubernetes_version  = "1.28"
  node_count          = var.environment == "prod" ? 3 : 1
  node_vm_size        = var.environment == "prod" ? "Standard_D4s_v3" : "Standard_B2s"
  enable_auto_scaling = true
  min_count           = var.environment == "prod" ? 3 : 1
  max_count           = var.environment == "prod" ? 10 : 3
}
```

### Platform Layer via Helm (Terraform-managed)
```hcl
resource "helm_release" "prometheus" {
  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  namespace  = "monitoring"
  create_namespace = true
  values = [file("${path.module}/values/prometheus.yaml")]
}

resource "helm_release" "efk" {
  name       = "elasticsearch"
  repository = "https://helm.elastic.co"
  chart      = "elasticsearch"
  namespace  = "logging"
  create_namespace = true
}
```

### Database Provisioning
```hcl
module "database" {
  source      = "./modules/database"
  db_name     = "${var.project_name}-db"
  db_type     = "postgresql"    # postgresql, mongodb, redis
  environment = var.environment
  sku         = var.environment == "prod" ? "GP_Gen5_4" : "B_Gen5_1"
  storage_mb  = var.environment == "prod" ? 102400 : 5120
}
```

### GitLab Repo Auto-Creation via Terraform
```hcl
resource "gitlab_project" "service" {
  for_each         = toset(var.service_names)
  name             = each.value
  namespace_id     = var.gitlab_group_id
  visibility_level = "private"
  default_branch   = "main"

  push_rules {
    prevent_secrets = true
  }
}
```

### Deployment Execution Order
When I ask to deploy, execute in this order:
1. **Phase 1**: Terraform networking (VNet, subnets, NSGs)
2. **Phase 2**: Terraform compute (AKS cluster)
3. **Phase 3**: Terraform platform (Prometheus, EFK, Ingress via Helm)
4. **Phase 4**: Terraform databases (PostgreSQL, Redis, etc.)
5. **Phase 5**: Application deployment (Kustomize overlays to K8s)

### Naming Convention
```
Resource Type  | Pattern                    | Example
---------------|----------------------------|---------------------------
Resource Group | rg-{project}-{env}         | rg-ecommerce-dev
AKS Cluster    | aks-{project}-{env}        | aks-ecommerce-prod
Database       | db-{project}-{service}-{env}| db-ecommerce-auth-dev
Key Vault      | kv-{project}-{env}         | kv-ecommerce-prod
Storage        | st{project}{env}           | stecommercedev
```

### Cost Management
- Always use `prevent_destroy = true` on production databases
- Tag ALL resources: `project`, `environment`, `managed_by=terraform`
- Use spot instances for dev, reserved instances for prod

---

## Environment Standards — Dev and Prod ONLY

**RULE: Only TWO environments. Never create qa, staging, dr, uat, etc.**

### Dev Environment
- Full debug tooling enabled (all dashboards, swagger, pgAdmin)
- Relaxed resource limits
- Single replica per service
- Seed data loaded automatically
- All credentials visible in Credentials Dashboard (port 9001)
- Hot-reload enabled for all services
- Verbose logging (DEBUG level)

### Prod Environment
- No debug dashboards
- No swagger UI
- No seed data
- Strict resource limits
- Minimum 2 replicas per service
- Secrets managed via Kubernetes Secrets / external vault
- Structured JSON logging only (INFO level)
- Network policies enforced
- Pod security policies applied
CLAUDEMD9_EOF

print_success "Sections 9-10 appended"

# ─── CLAUDE.md sections 11-12 ──────────────────────────────────────────────
print_step "Appending credentials dashboard and visualization standards..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD11_EOF'

---

## Credentials & Service Discovery Dashboard (DEV ONLY)

**Port: 9001** — Auto-generated React dashboard showing all service credentials.
**NEVER create this in prod.**

### Dashboard Sections
1. **Service Registry** — all running services with URLs and ports
2. **Database Credentials** — host, port, username, password, database name
3. **API Keys** — all internal API keys with copy buttons
4. **Tool URLs** — Grafana, Kibana, Jaeger, pgAdmin, Redis Commander, etc.
5. **Environment Variables** — all env vars per service
6. **Connection Strings** — ready-to-paste connection strings for every DB
7. **Sample API Calls** — curl commands for every endpoint with auth headers

### Auto-Generation
Parse `docker-compose.yml` and Kubernetes manifests to extract:
- All `ports:` mappings → Service URLs table
- All `environment:` variables → Credentials table
- All database connection details → Connection strings

### Template
```typescript
interface ServiceInfo {
  name: string;
  url: string;
  port: number;
  credentials?: { username: string; password: string };
  healthEndpoint: string;
  docsEndpoint?: string;
  status: 'running' | 'stopped' | 'error';
}
```

---

## Visualization Standards — Learning Mode

**RULE: Every project MUST include a Debug Dashboard for learning and debugging.**

### Debug Dashboard — Port 9000
A React-based SPA with these tabs:

1. **DB Explorer** — browse tables, run queries, see data in real-time
2. **API Flow** — visualize request/response flow between services (sequence diagrams)
3. **Architecture** — auto-generated system architecture diagram (Mermaid)
4. **Queue Monitor** — Kafka/RabbitMQ topic viewer, message inspector
5. **Cache Inspector** — Redis key browser, TTL viewer
6. **Logs** — real-time log aggregation from all services (tail -f style)
7. **Metrics** — embedded Grafana panels or custom charts (Recharts)
8. **Event Timeline** — chronological event stream across all services
9. **Data Flow** — visualize data as it moves through the pipeline
10. **Diagrams** — auto-generated Mermaid diagrams (ERD, sequence, architecture)

### Backend Instrumentation
Every service MUST expose debug endpoints (dev only):
```
GET /debug/db/tables          — list all tables
GET /debug/db/query?sql=...   — run read-only SQL
GET /debug/events             — SSE stream of all events
GET /debug/cache/keys         — list Redis keys
GET /debug/config             — show runtime config
```

### Database Change Tracking
Implement change triggers or event sourcing so the Debug Dashboard shows:
- What changed (before/after)
- When it changed
- Which API call triggered it
- Which user initiated it

### Docker Compose Visual Stack
```yaml
# Add to docker-compose.dev.yml
services:
  debug-dashboard:
    build: ./dashboards/debug-dashboard
    ports:
      - "9000:3000"
    environment:
      - SERVICES_CONFIG=/app/services.json
    depends_on:
      - api-gateway

  pgadmin:
    image: dpage/pgadmin4
    ports:
      - "5050:80"
    environment:
      - PGADMIN_DEFAULT_EMAIL=${PGADMIN_DEFAULT_EMAIL:-admin@dev.local}
      - PGADMIN_DEFAULT_PASSWORD=${PGADMIN_DEFAULT_PASSWORD:?PGADMIN_DEFAULT_PASSWORD is required}

  redis-commander:
    image: rediscommander/redis-commander
    ports:
      - "8081:8081"
    environment:
      - REDIS_HOSTS=local:redis:6379

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "9411:16686"

  mailhog:
    image: mailhog/mailhog
    ports:
      - "8025:8025"
```

### Standard Port Map (memorize this):
```
Port  | Service                  | Port  | Service
------|--------------------------|-------|---------------------------
3000  | Grafana                  | 9000  | Debug Dashboard
3001  | Frontend App             | 9001  | Credentials Dashboard
5050  | pgAdmin                  | 9002  | Task History Dashboard
5432  | PostgreSQL               | 9003  | Project Journey Tour
5601  | Kibana                   | 9090  | Prometheus
6379  | Redis                    | 9411  | Jaeger
8080  | API Gateway / Swagger    | 8081  | Redis Commander
8025  | MailHog                  | 8082  | Mongo Express
```
CLAUDEMD11_EOF

print_success "Sections 11-12 appended"

# ─── CLAUDE.md section 13 ──────────────────────────────────────────────────
print_step "Appending frontend standards..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD13_EOF'

---

## Frontend Standards — Production-Grade, Never Basic

**RULE: When I say "create a frontend", I mean the MOST advanced, polished UI possible.**

### Tech Stack (MANDATORY)
- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript (strict mode)
- **Styling**: TailwindCSS + custom design tokens
- **Components**: shadcn/ui (customized, not default)
- **State**: Zustand (global) + TanStack Query (server state)
- **Data Tables**: TanStack Table with sorting, filtering, pagination, column resize
- **Charts**: Recharts or Tremor for dashboards
- **Animations**: Framer Motion for page transitions, micro-interactions
- **Forms**: React Hook Form + Zod validation
- **Icons**: Lucide React
- **Date/Time**: date-fns
- **HTTP**: Axios with interceptors

### Custom Design System
```typescript
// design-tokens.ts — ALWAYS create project-specific tokens
export const tokens = {
  colors: {
    primary: { 50: '#eff6ff', 500: '#3b82f6', 900: '#1e3a8a' },
    success: { 50: '#f0fdf4', 500: '#22c55e' },
    warning: { 50: '#fffbeb', 500: '#f59e0b' },
    error:   { 50: '#fef2f2', 500: '#ef4444' },
    neutral: { 50: '#f9fafb', 500: '#6b7280', 900: '#111827' },
  },
  spacing: { xs: '0.25rem', sm: '0.5rem', md: '1rem', lg: '1.5rem', xl: '2rem' },
  borderRadius: { sm: '0.375rem', md: '0.5rem', lg: '0.75rem', full: '9999px' },
  shadows: {
    sm: '0 1px 2px rgba(0,0,0,0.05)',
    md: '0 4px 6px -1px rgba(0,0,0,0.1)',
    lg: '0 10px 15px -3px rgba(0,0,0,0.1)',
  },
};
```

### UI Requirements — Every Page MUST Have:
1. **Loading States** — skeleton loaders (not spinners), shimmer effects
2. **Empty States** — illustrated empty states with call-to-action
3. **Error States** — friendly error messages with retry buttons
4. **Data Tables** — sortable, filterable, searchable, paginated, column resize
5. **Toast Notifications** — success/error/warning/info with auto-dismiss
6. **Breadcrumbs** — on every nested page
7. **Keyboard Shortcuts** — Cmd+K search, Escape to close, etc.
8. **Responsive** — mobile-first, works on all screen sizes
9. **Dark Mode** — toggle with system preference detection
10. **Transitions** — page transitions, element animations

### Component Architecture
```
src/
├── app/                    # Next.js App Router
│   ├── (auth)/             # Auth layout group
│   ├── (dashboard)/        # Dashboard layout group
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   ├── ui/                 # shadcn/ui components (customized)
│   ├── layout/             # Header, Sidebar, Footer
│   ├── features/           # Feature-specific components
│   ├── charts/             # Chart components
│   └── shared/             # Reusable across features
├── hooks/                  # Custom hooks
├── lib/                    # Utilities, API client
├── stores/                 # Zustand stores
├── types/                  # TypeScript interfaces
└── styles/
    ├── globals.css
    └── design-tokens.ts
```

### Dashboard Patterns
Every dashboard page MUST include:
- **Stats Cards** — key metrics with trend indicators (up/down arrows, percentages)
- **Charts** — at least 2 chart types (line, bar, pie, area)
- **Recent Activity** — timeline of latest events
- **Quick Actions** — buttons for common operations
- **Filters** — date range picker, category filters
- **Export** — CSV/PDF export buttons

### Animations & Micro-interactions
```typescript
// MANDATORY animation patterns
const pageTransition = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.3 }
};

// Staggered list animations
const containerVariants = {
  animate: { transition: { staggerChildren: 0.05 } }
};
```

### Performance
- Lighthouse score > 90 on ALL metrics
- Code splitting per route
- Image optimization via next/image
- Font optimization via next/font
- ISR/SSG where data is static

### Accessibility
- WCAG 2.1 AA compliance
- aria-labels on all interactive elements
- Focus management and keyboard navigation
- Screen reader compatible

### What "Basic" Looks Like — NEVER DO THIS:
- Plain HTML tables without sorting/filtering
- Browser default form elements
- No loading states (just blank screen)
- No animations or transitions
- Default shadcn/ui without customization
- No dark mode
- No mobile responsiveness
- alert() instead of toast notifications
CLAUDEMD13_EOF

print_success "Section 13 appended"

# ─── CLAUDE.md sections 14-15 ──────────────────────────────────────────────
print_step "Appending task tracking standards..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD14_EOF'

---

## Task Tracking — Auto-Record ALL Claude Code Activities

**RULE: Every action Claude Code takes MUST be recorded. No exceptions.**

### Local Project Tracking
Every project gets:
- `.claude/task-log/CURRENT.md` — active session tasks
- `.claude/task-log/archive/` — completed session logs
- `.claude/task-log/SUMMARY.md` — running totals

### Global Tracking
- `~/.claude/task-log/GLOBAL_LOG.md` — cross-project activity log
- `~/.claude/task-log/SUMMARY.md` — all-time statistics

### Task Granularity Rules
- File created → 1 task
- File modified → 1 task (with what changed)
- Command executed → 1 task (with command and outcome)
- Test run → 1 task (with pass/fail count)
- Error encountered → 1 task (with error and resolution)
- Decision made → 1 task (architectural/design decisions)

### Session Behavior
**On session start:**
1. Create/update CURRENT.md with session header
2. Record session goal
3. Register in SQLite database

**During session:**
1. Record every task as completed
2. Update progress counts
3. Log file changes, commands, errors

**On session end:**
1. Generate session summary
2. Archive CURRENT.md
3. Update SUMMARY.md
4. Generate output report
5. Update SQLite database

---

## Task Tracking Database — Persistent History

**SQLite database at: `~/.claude/task-log/claude-tasks.db`**

### Schema
```sql
-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    session_uuid TEXT NOT NULL UNIQUE,
    goal TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    failed_tasks INTEGER DEFAULT 0,
    files_created INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    summary TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    metadata TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- File changes table
CREATE TABLE IF NOT EXISTS file_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_id INTEGER,
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Commands executed
CREATE TABLE IF NOT EXISTS commands_executed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_id INTEGER,
    command TEXT NOT NULL,
    exit_code INTEGER,
    output_summary TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Resources created (K8s, Docker, Terraform)
CREATE TABLE IF NOT EXISTS resources_created (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    resource_type TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Errors encountered
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_id INTEGER,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    resolution TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Daily summaries
CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    total_sessions INTEGER DEFAULT 0,
    total_tasks INTEGER DEFAULT 0,
    total_files_changed INTEGER DEFAULT 0,
    total_commands INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    highlights TEXT
);

-- Session reports
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    report_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

### Useful Views
```sql
CREATE VIEW IF NOT EXISTS v_session_summary AS
SELECT
    s.session_uuid,
    p.name as project_name,
    s.goal,
    s.started_at,
    s.ended_at,
    s.total_tasks,
    s.completed_tasks,
    s.files_created + s.files_modified as total_file_changes,
    (SELECT COUNT(*) FROM errors e WHERE e.session_id = s.id) as error_count
FROM sessions s
JOIN projects p ON s.project_id = p.id
ORDER BY s.started_at DESC;

CREATE VIEW IF NOT EXISTS v_daily_activity AS
SELECT
    DATE(s.started_at) as date,
    COUNT(DISTINCT s.id) as sessions,
    SUM(s.total_tasks) as tasks,
    SUM(s.files_created) as files_created,
    SUM(s.files_modified) as files_modified
FROM sessions s
GROUP BY DATE(s.started_at)
ORDER BY date DESC;
```

### Task History Dashboard — Port 9002
Auto-generated dashboard showing:
- Session timeline with drill-down
- Files changed heat map
- Error trend chart
- Productivity metrics
- Project comparison
CLAUDEMD14_EOF

print_success "Sections 14-15 appended"

# ─── CLAUDE.md section 16 ──────────────────────────────────────────────────
print_step "Appending session output report standards..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD16_EOF'

---

## Session Output Report — MANDATORY Final Deliverable

**RULE: Every Claude Code session MUST produce an output report. No exceptions.**

### Report Formats (generate ALL three)
1. `.md` — Markdown for reading
2. `.html` — Styled HTML for browser viewing
3. `.json` — Structured data for programmatic access

### Report Location
- Project: `.claude/reports/session-{UUID}-{DATE}.{md|html|json}`
- Global archive: `~/.claude/reports/sessions/`
- Weekly digest: `~/.claude/reports/weekly/week-{YYYY-WW}.md`

### Report Template (Markdown)
```markdown
# Session Report
**Date**: {DATE}
**Duration**: {DURATION}
**Project**: {PROJECT_NAME}
**Goal**: {SESSION_GOAL}

## Summary
{2-3 sentence summary of what was accomplished}

## Tasks Completed ({COUNT})
| # | Task | Type | Duration |
|---|------|------|----------|
| 1 | {description} | {file/command/config} | {time} |

## Files Changed ({COUNT})
| File | Action | Lines +/- |
|------|--------|-----------|
| {path} | {created/modified/deleted} | {+X/-Y} |

## Commands Executed ({COUNT})
| Command | Exit Code | Purpose |
|---------|-----------|---------|
| {cmd} | {code} | {why} |

## Infrastructure Created
| Resource | Type | Details |
|----------|------|---------|
| {name} | {K8s/Docker/Terraform} | {details} |

## Errors & Resolutions ({COUNT})
| Error | Resolution | Impact |
|-------|------------|--------|
| {error} | {fix} | {impact} |

## Architectural Decisions
| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| {decision} | {why} | {alternatives} |

## Next Steps
- [ ] {recommended next action 1}
- [ ] {recommended next action 2}

## Statistics
- Total tasks: {N}
- Files created: {N}
- Files modified: {N}
- Commands run: {N}
- Errors encountered: {N}
- Errors resolved: {N}
```

### Terminal Summary (always print at session end)
```
╔══════════════════════════════════════════════════════════════╗
║                    SESSION COMPLETE                          ║
╠══════════════════════════════════════════════════════════════╣
║  Project:  {name}                                           ║
║  Duration: {time}                                           ║
║  Tasks:    {completed}/{total}                              ║
║  Files:    +{created} ~{modified} -{deleted}                ║
║  Errors:   {count} ({resolved} resolved)                    ║
║  Report:   .claude/reports/session-{uuid}.md                ║
╚══════════════════════════════════════════════════════════════╝
```
CLAUDEMD16_EOF

print_success "Section 16 appended"

# ─── CLAUDE.md section 17 ──────────────────────────────────────────────────
print_step "Appending language selection standards..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD17_EOF'

---

## Language Selection — Best Tool for the Job

**RULE: Do NOT default to a single language. Choose the BEST language per service.**

### Decision Matrix
| Use Case                    | Best Language    | Why                                      |
|-----------------------------|------------------|------------------------------------------|
| API Gateway                 | Go               | Fast, low memory, excellent HTTP perf    |
| Auth Service                | Go               | Security-focused, strong crypto stdlib   |
| CRUD APIs                   | Python (FastAPI) | Rapid development, great ORM ecosystem   |
| Real-time / WebSocket       | Node.js (TS)     | Event loop, native WebSocket support     |
| ML/AI Services              | Python           | PyTorch, TensorFlow, scikit-learn        |
| Data Processing / ETL       | Python           | Pandas, Spark bindings, rich ecosystem   |
| Financial / Complex Domain  | Java (Spring)    | Type safety, enterprise patterns, BigDecimal |
| CLI Tools                   | Go               | Single binary, cross-platform, fast      |
| High-perf Microservices     | Rust             | Zero-cost abstractions, memory safety    |
| Frontend                    | TypeScript       | Type safety, React/Next.js ecosystem     |
| Infrastructure Automation   | Go               | K8s client-go, Terraform providers       |
| Notification Service        | Node.js (TS)     | Async I/O, template engines, email libs  |
| File Processing             | Python           | PIL, PyPDF, openpyxl, rich file libs     |
| Search Service              | Java             | Elasticsearch client, Lucene heritage    |
| Scheduling / Cron           | Go               | Lightweight, reliable, single binary     |
| Message Queue Consumer      | Go or Java       | Reliable processing, good Kafka clients  |
| Report Generation           | Python           | Jinja2, ReportLab, matplotlib            |
| GraphQL API                 | Node.js (TS)     | Apollo Server, excellent DX, type-gen    |
| gRPC Services               | Go               | Native protobuf, excellent performance   |
| Background Workers          | Python (Celery)  | Task queues, retry logic, monitoring     |

### Multi-Language Project Example
```
services/
├── api-gateway/         → Go (Gin/Chi)
├── auth-service/        → Go (stdlib + jwt-go)
├── user-service/        → Python (FastAPI + SQLAlchemy)
├── product-service/     → Python (FastAPI + SQLAlchemy)
├── order-service/       → Java (Spring Boot)
├── payment-service/     → Java (Spring Boot + BigDecimal)
├── notification-service/→ Node.js (TypeScript + Nodemailer)
├── search-service/      → Java (Spring + Elasticsearch)
├── analytics-service/   → Python (FastAPI + Pandas)
├── realtime-service/    → Node.js (TypeScript + Socket.io)
└── ml-recommendation/   → Python (FastAPI + PyTorch)
```

### Language-Specific Dockerfiles

**Go:**
```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /app/server ./cmd/server

FROM scratch
COPY --from=builder /app/server /server
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
USER 65534
EXPOSE 8080
ENTRYPOINT ["/server"]
```

**Python:**
```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN useradd -m -r appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
USER appuser
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Java:**
```dockerfile
FROM eclipse-temurin:21-jdk-alpine AS builder
WORKDIR /app
COPY . .
RUN ./mvnw clean package -DskipTests

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

### Inter-Service Communication
- REST (OpenAPI 3.0) for synchronous calls between different-language services
- gRPC for high-throughput internal calls (Go ↔ Go, Go ↔ Java)
- Kafka/RabbitMQ for async event-driven communication
- Shared Protobuf definitions in `shared/proto/`
- Shared OpenAPI specs in `shared/openapi/`

### Language-Specific K8s Resource Defaults
```yaml
# Go services — lean
resources:
  requests: { cpu: "50m", memory: "32Mi" }
  limits:   { cpu: "200m", memory: "128Mi" }

# Python services — moderate
resources:
  requests: { cpu: "100m", memory: "128Mi" }
  limits:   { cpu: "500m", memory: "512Mi" }

# Java services — heavy
resources:
  requests: { cpu: "200m", memory: "512Mi" }
  limits:   { cpu: "1000m", memory: "1Gi" }

# Node.js services — moderate
resources:
  requests: { cpu: "100m", memory: "128Mi" }
  limits:   { cpu: "500m", memory: "512Mi" }
```
CLAUDEMD17_EOF

print_success "Section 17 appended"

# ─── CLAUDE.md sections 18-19 ──────────────────────────────────────────────
print_step "Appending alerts, notifications, and journey walkthrough..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD18_EOF'

---

## Alerts & Notifications

**RULE: Every project MUST have comprehensive alerting configured.**

### Alert Categories

**Application Alerts:**
- High error rate (>5% of requests returning 5xx)
- High latency (p99 > 1s)
- Service down (health check failing > 2 min)
- Memory leak (memory usage growing without reset)
- Connection pool exhaustion
- Circuit breaker open

**Infrastructure Alerts:**
- Node CPU > 80% for 5 minutes
- Node memory > 85%
- Disk usage > 80%
- Pod crash looping (>3 restarts in 15 min)
- Pod OOMKilled
- PVC storage > 80%

**Kubernetes Alerts:**
- Deployment rollout stuck
- HPA at max replicas for > 30 min
- Certificate expiring (< 14 days)
- Ingress 5xx spike
- NetworkPolicy blocking legitimate traffic

**Database Alerts:**
- Connection count > 80% of max
- Slow queries (> 5s)
- Replication lag > 10s
- Storage > 80%
- Failed backups
- Deadlocks detected

**Kafka/Queue Alerts:**
- Consumer lag > 10000 messages
- Topic partition offline
- Broker under-replicated
- Consumer group rebalancing frequently

**Security Alerts:**
- Failed authentication spike (> 50/min)
- Unusual API access patterns
- Secret rotation needed
- SSL/TLS certificate issues
- Pod running as root

**CI/CD Alerts:**
- Pipeline failure on main/develop branch
- Security scan found critical vulnerability
- Docker image build failure
- Deployment failure

**SLA/Cost Alerts:**
- Uptime below SLA threshold
- Response time exceeding SLA
- Cloud spend exceeding budget
- Unused resources detected

### Notification Channels

**Slack Configuration:**
```yaml
# alertmanager.yml
receivers:
  - name: slack-critical
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#alerts-critical'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
        send_resolved: true
        color: '{{ if eq .Status "firing" }}danger{{ else }}good{{ end }}'

  - name: slack-warnings
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#alerts-warnings'
        send_resolved: true

  - name: slack-deployments
    slack_configs:
      - channel: '#deployments'
        send_resolved: true

  - name: slack-security
    slack_configs:
      - channel: '#security-alerts'
        send_resolved: true

  - name: pagerduty-critical
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
        severity: critical

  - name: email-daily
    email_configs:
      - to: 'team@company.com'
        send_resolved: true

route:
  receiver: slack-warnings
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match:
        severity: critical
      receiver: slack-critical
      continue: true
    - match:
        severity: critical
      receiver: pagerduty-critical
    - match:
        category: security
      receiver: slack-security
    - match:
        category: deployment
      receiver: slack-deployments
```

**Slack Channel Structure:**
| Channel              | Purpose                          | Alert Severity |
|----------------------|----------------------------------|----------------|
| #alerts-critical     | Production down, data loss       | critical       |
| #alerts-warnings     | Degraded performance, thresholds | warning        |
| #deployments         | Deploy success/failure           | info           |
| #security-alerts     | Auth failures, vulnerabilities   | critical/warn  |
| #infrastructure      | Node/cluster issues              | warning        |
| #daily-digest        | Daily summary of all alerts      | info           |
| #ci-cd-notifications | Pipeline pass/fail               | info           |
| #cost-alerts         | Budget thresholds                | warning        |

---

## Project Journey Walkthrough — Browser-Based Interactive Tour

**Port: 9003** — Auto-generated after project scaffolding.

### When to Create
After Claude Code finishes scaffolding a project, automatically:
1. Generate `dashboards/journey-walkthrough/index.html`
2. Generate `dashboards/journey-walkthrough/journey-data.json`
3. Add to docker-compose.dev.yml
4. Auto-open in browser

### Journey Steps (12-step walkthrough)
1. **Project Overview** — what was built, architecture diagram (Mermaid)
2. **Services Created** — list of all microservices with descriptions
3. **Tech Stack** — languages, frameworks, and why each was chosen
4. **Architecture** — interactive diagram showing service communication
5. **Database Schema** — ER diagram, tables created, relationships
6. **API Endpoints** — all REST/gRPC endpoints with examples
7. **Kubernetes Setup** — cluster layout, deployments, services
8. **CI/CD Pipeline** — pipeline stages visualization
9. **Monitoring** — Grafana dashboards, alerts configured
10. **Infrastructure** — Terraform resources, cloud architecture
11. **How to Run** — step-by-step dev environment setup
12. **Next Steps** — recommended improvements and extensions

### Auto-Generation
Parse project files to build journey-data.json:
- docker-compose.yml → services list
- Kubernetes manifests → deployment diagram
- OpenAPI specs → API endpoint list
- Terraform files → infrastructure diagram
- .gitlab-ci.yml → pipeline visualization
- Database migrations → schema diagram
CLAUDEMD18_EOF

print_success "Sections 18-19 appended"

# ─── Section 20: Auto-Generate Claude Code Automations ────────────────────
print_step "Appending Section 20 (Auto-Generate Automations)..."

cat >> "$CLAUDE_MD" << 'CLAUDEMD20_EOF'

---

## Auto-Generate Claude Code Automations (MANDATORY)

**RULE: Every project scaffolded by Claude Code MUST include project-specific automations.**

After scaffolding project code, AUTOMATICALLY generate these Claude Code automation files.
Do NOT ask — just create them based on the tech stack and services detected.

### What Gets Auto-Generated

```
project-root/
├── .claude/
│   ├── settings.json          # Project-level hooks + permissions
│   ├── agents/                # Specialized subagents
│   │   ├── code-reviewer.md
│   │   ├── security-reviewer.md
│   │   ├── test-writer.md
│   │   └── api-documenter.md
│   └── skills/                # Project-specific skills
│       ├── gen-test/
│       │   └── SKILL.md
│       ├── create-migration/
│       │   └── SKILL.md
│       ├── new-component/
│       │   └── SKILL.md
│       ├── api-doc/
│       │   └── SKILL.md
│       └── deploy/
│           └── SKILL.md
├── .mcp.json                  # Project MCP servers (shared with team)
└── ...
```

---

### A. Auto-Generate Hooks (.claude/settings.json)

Create project-level `.claude/settings.json` with hooks based on detected tools:

#### Detection → Hook Mapping

| Detected In Project         | Hook Type    | Auto-Generate                                     |
|-----------------------------|--------------|----------------------------------------------------|
| Prettier / .prettierrc      | PostToolUse  | Auto-format on every file edit                     |
| ESLint / .eslintrc          | PostToolUse  | Auto-lint on every .js/.ts edit                    |
| Ruff / ruff.toml            | PostToolUse  | Auto-lint on every .py edit                        |
| Go files                    | PostToolUse  | Run gofmt + go vet on every .go edit               |
| TypeScript / tsconfig.json  | PostToolUse  | Type-check on edit (tsc --noEmit)                  |
| Tests directory exists      | PostToolUse  | Run related tests after code changes               |
| .env files present          | PreToolUse   | BLOCK any .env file edits (security)               |
| Lock files (yarn/pnpm/go)   | PreToolUse   | BLOCK lock file manual edits                       |
| Dockerfile                  | PostToolUse  | Validate Dockerfile with hadolint after edit       |
| Kubernetes manifests        | PostToolUse  | Validate YAML with kubeval after edit              |
| Terraform files             | PostToolUse  | Run terraform fmt + terraform validate after edit  |
| OpenAPI spec                | PostToolUse  | Validate OpenAPI spec after edit                   |
| Database migrations         | PostToolUse  | Check migration sequence after new migration       |

#### Template: Project-Level .claude/settings.json

```json
{
  "permissions": {
    "allow": [
      "Read", "Edit", "Write", "MultiEdit",
      "Bash(npm test:*)",
      "Bash(npm run lint:*)",
      "Bash(npm run format:*)",
      "Bash(go test:*)",
      "Bash(pytest:*)",
      "Bash(docker build:*)",
      "Bash(kubectl apply --dry-run:*)",
      "Bash(terraform plan:*)",
      "Bash(git add:*)",
      "Bash(git commit:*)"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(git push --force:*)",
      "Bash(kubectl delete:*)",
      "Bash(terraform destroy:*)",
      "Bash(docker system prune:*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "name": "block-env-edits",
        "description": "Prevent accidental .env file modifications",
        "match_tools": ["Edit", "Write", "MultiEdit"],
        "command": "if echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.env($|\\.)'; then echo 'BLOCKED: .env files must be edited manually for security'; exit 1; fi"
      },
      {
        "name": "block-lockfile-edits",
        "description": "Prevent manual lock file modifications",
        "match_tools": ["Edit", "Write"],
        "command": "if echo \"$CLAUDE_FILE_PATH\" | grep -qE '(package-lock|yarn\\.lock|pnpm-lock|go\\.sum|Cargo\\.lock)'; then echo 'BLOCKED: Lock files should not be manually edited'; exit 1; fi"
      }
    ],
    "PostToolUse": [
      {
        "name": "auto-format",
        "description": "Auto-format files after editing",
        "match_tools": ["Edit", "Write", "MultiEdit"],
        "command": "FORMAT_CMD=''; if [ -f .prettierrc ] || [ -f .prettierrc.json ]; then FORMAT_CMD=\"npx prettier --write $CLAUDE_FILE_PATH\"; elif echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.go$'; then FORMAT_CMD=\"gofmt -w $CLAUDE_FILE_PATH\"; elif echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.py$' && [ -f ruff.toml ]; then FORMAT_CMD=\"ruff format $CLAUDE_FILE_PATH\"; elif echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.tf$'; then FORMAT_CMD=\"terraform fmt $CLAUDE_FILE_PATH\"; fi; [ -n \"$FORMAT_CMD\" ] && eval $FORMAT_CMD 2>/dev/null || true"
      },
      {
        "name": "auto-lint",
        "description": "Run linter after code changes",
        "match_tools": ["Edit", "Write", "MultiEdit"],
        "command": "LINT_CMD=''; if echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.(js|ts|jsx|tsx)$' && [ -f .eslintrc.json ]; then LINT_CMD=\"npx eslint --fix $CLAUDE_FILE_PATH\"; elif echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.py$' && [ -f ruff.toml ]; then LINT_CMD=\"ruff check --fix $CLAUDE_FILE_PATH\"; elif echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.go$'; then LINT_CMD=\"go vet ./...\"; fi; [ -n \"$LINT_CMD\" ] && eval $LINT_CMD 2>/dev/null || true"
      },
      {
        "name": "validate-k8s-manifests",
        "description": "Validate Kubernetes YAML after editing",
        "match_tools": ["Edit", "Write"],
        "command": "if echo \"$CLAUDE_FILE_PATH\" | grep -qE 'k8s/|kubernetes/|manifests/' && echo \"$CLAUDE_FILE_PATH\" | grep -qE '\\.ya?ml$'; then kubectl apply --dry-run=client -f \"$CLAUDE_FILE_PATH\" 2>/dev/null || echo 'WARNING: K8s manifest validation failed'; fi"
      },
      {
        "name": "validate-dockerfile",
        "description": "Lint Dockerfile after editing",
        "match_tools": ["Edit", "Write"],
        "command": "if echo \"$CLAUDE_FILE_PATH\" | grep -qi 'dockerfile'; then command -v hadolint &>/dev/null && hadolint \"$CLAUDE_FILE_PATH\" 2>/dev/null || true; fi"
      },
      {
        "name": "track-all-changes",
        "description": "Log all file operations for task tracking",
        "match_tools": ["Write", "Edit", "MultiEdit"],
        "command": "mkdir -p .claude/task-log && echo \"$(date '+%Y-%m-%d %H:%M:%S') | $CLAUDE_TOOL_NAME | $CLAUDE_FILE_PATH\" >> .claude/task-log/.file-changes.log 2>/dev/null || true"
      }
    ]
  }
}
```

**IMPORTANT:** Adapt this template — only include hooks for tools ACTUALLY present in the project.
If the project has no Prettier, do NOT include the Prettier hook. Detect, then generate.

---

### B. Auto-Generate MCP Servers (.mcp.json)

Create `.mcp.json` in project root so the entire team gets the same MCP tools.

#### Detection → MCP Server Mapping

| Detected In Project              | MCP Server to Add                | Purpose                              |
|----------------------------------|----------------------------------|--------------------------------------|
| Any npm/pip/go project           | **context7**                     | Live docs for all libraries          |
| Frontend (React/Vue/Angular)     | **playwright**                   | Browser testing + UI automation      |
| PostgreSQL / pg / prisma         | **postgres-mcp**                 | Direct DB queries + schema           |
| MongoDB / mongoose               | **mongodb-mcp**                  | Collection queries + aggregation     |
| Redis / ioredis                  | **redis-mcp**                    | Cache inspection + key management    |
| Supabase                         | **supabase-mcp**                 | Full Supabase operations             |
| GitHub repo (.git)               | **github-mcp**                   | Issues, PRs, Actions                 |
| GitLab repo                      | **gitlab-mcp**                   | MRs, pipelines, registry             |
| Docker / docker-compose          | **docker-mcp**                   | Container management                 |
| Kubernetes manifests             | **kubernetes-mcp**               | Cluster operations + debugging       |
| AWS SDK / aws-cdk                | **aws-mcp**                      | Cloud resource management            |
| Azure SDK                        | **azure-mcp**                    | Azure resource management            |
| Stripe SDK                       | **stripe-mcp**                   | Payment operations                   |
| Sentry DSN configured            | **sentry-mcp**                   | Error investigation + resolution     |
| Slack integration                | **slack-mcp**                    | Team notifications                   |
| Linear / Jira references         | **linear-mcp** / **jira-mcp**   | Issue tracking                       |
| OpenAPI / Swagger spec           | **openapi-mcp**                  | API testing + validation             |
| Any project (persistence)        | **memory-mcp**                   | Cross-session memory + context       |

#### Template: .mcp.json

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-playwright"]
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-postgres"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/dbname"
      }
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "kubernetes": {
      "command": "npx",
      "args": ["-y", "kubernetes-mcp-server"],
      "env": {
        "KUBECONFIG": "${KUBECONFIG}"
      }
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-memory"]
    }
  }
}
```

**IMPORTANT:** Only include MCP servers for tools/services ACTUALLY used in the project.
Use `${ENV_VAR}` references for secrets — never hardcode tokens.

---

### C. Auto-Generate Subagents (.claude/agents/)

Create specialized agents under `.claude/agents/` based on project characteristics.

#### Detection → Agent Mapping

| Detected In Project              | Agent to Create            | File                           |
|----------------------------------|----------------------------|--------------------------------|
| Any codebase (always)            | Code Reviewer              | .claude/agents/code-reviewer.md |
| Auth / payments / crypto code    | Security Reviewer          | .claude/agents/security-reviewer.md |
| API routes detected              | API Documenter             | .claude/agents/api-documenter.md |
| Test directory exists            | Test Writer                | .claude/agents/test-writer.md |
| Frontend components              | UI/UX Reviewer             | .claude/agents/ui-reviewer.md |
| Performance-critical services    | Performance Analyzer       | .claude/agents/perf-analyzer.md |
| Database models/migrations       | Schema Reviewer            | .claude/agents/schema-reviewer.md |
| Kubernetes manifests             | K8s Config Reviewer        | .claude/agents/k8s-reviewer.md |
| Terraform files                  | IaC Reviewer               | .claude/agents/iac-reviewer.md |

#### Agent Template Example: code-reviewer.md

```markdown
---
name: code-reviewer
description: Reviews code changes for quality, patterns, and potential issues
tools:
  - Read
  - Glob
  - Grep
  - Bash
---

# Code Reviewer Agent

You are a senior code reviewer. Analyze code changes for:

## Review Checklist
1. **Correctness** — Logic errors, edge cases, off-by-one errors
2. **Security** — Injection, auth bypasses, hardcoded secrets, OWASP Top 10
3. **Performance** — N+1 queries, unnecessary loops, memory leaks
4. **Patterns** — Follows project conventions from CLAUDE.md
5. **Error Handling** — Proper try/catch, graceful degradation
6. **Tests** — Adequate coverage, meaningful assertions
7. **Naming** — Clear, consistent naming conventions
8. **DRY** — No unnecessary duplication

## Output Format
For each issue found:
- **Severity**: Critical / Warning / Suggestion
- **File**: path:line_number
- **Issue**: Description
- **Fix**: Recommended change

Rate overall quality: PASS / PASS WITH NOTES / NEEDS CHANGES
```

#### Agent Template Example: security-reviewer.md

```markdown
---
name: security-reviewer
description: Audits code for security vulnerabilities
tools:
  - Read
  - Glob
  - Grep
---

# Security Reviewer Agent

You are a security auditor. Scan for:

## Security Checks
1. **Secrets** — Hardcoded API keys, tokens, passwords in code or config
2. **Injection** — SQL injection, command injection, XSS, SSRF
3. **Auth** — Broken authentication, missing authorization checks
4. **Data Exposure** — PII in logs, overly permissive CORS, verbose errors
5. **Dependencies** — Known CVEs in package versions
6. **Kubernetes** — Privileged containers, missing SecurityContext, no NetworkPolicy
7. **Terraform** — Public S3 buckets, open security groups, no encryption
8. **Docker** — Running as root, secrets in build args, latest tags

## Output Format
For each vulnerability:
- **Severity**: CRITICAL / HIGH / MEDIUM / LOW
- **CWE**: CWE ID if applicable
- **File**: path:line_number
- **Vulnerability**: Description
- **Remediation**: How to fix
```

#### Agent Template Example: test-writer.md

```markdown
---
name: test-writer
description: Generates comprehensive test suites for code
tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
---

# Test Writer Agent

You generate tests following the project's testing patterns.

## Process
1. Read existing tests to learn project patterns
2. Identify untested functions/components
3. Generate tests covering:
   - Happy path
   - Edge cases
   - Error conditions
   - Boundary values
4. Use project's test framework (Jest/pytest/Go testing)
5. Follow existing naming conventions and file structure

## Test Quality Rules
- Every test MUST have a clear, descriptive name
- Use AAA pattern: Arrange, Act, Assert
- Mock external dependencies, never real APIs
- Test behavior, not implementation
- Aim for >80% coverage on business logic
```

---

### D. Auto-Generate Skills (.claude/skills/)

Create project-specific skills based on workflows detected.

#### Detection → Skill Mapping

| Detected In Project              | Skill to Create             | Invocation  |
|----------------------------------|-----------------------------|-------------|
| Database migrations              | create-migration            | User-only   |
| API routes                       | api-doc                     | Both        |
| React/Vue components             | new-component               | User-only   |
| Test suites                      | gen-test                    | User-only   |
| Docker + K8s                     | deploy                      | User-only   |
| GitLab/GitHub CI                 | release-notes               | User-only   |
| OpenAPI spec                     | update-api-spec             | Both        |
| Multiple services                | add-service                 | User-only   |
| Database models                  | gen-model                   | User-only   |
| Any project                      | project-conventions         | Claude-only |

#### Skill Template Example: gen-test/SKILL.md

```markdown
---
name: gen-test
description: Generate test files for a given source file or function
disable-model-invocation: true
---

# Generate Tests

## Arguments
- `target`: File path or function name to test

## Process
1. Read the target file
2. Identify all exported functions/classes
3. Check existing test patterns in the project
4. Generate test file following project conventions:
   - Same test framework as existing tests
   - Same file naming pattern (*_test.go, *.test.ts, test_*.py)
   - Same assertion library
5. Include: happy path, edge cases, error cases
6. Place test file in correct directory
```

#### Skill Template Example: deploy/SKILL.md

```markdown
---
name: deploy
description: Deploy services to Kubernetes cluster
disable-model-invocation: true
---

# Deploy to Kubernetes

## Arguments
- `env`: Target environment (dev/prod)
- `service`: Service name (or "all")

## Pre-Deploy Checks
1. All tests pass
2. Docker images build successfully
3. K8s manifests validate (--dry-run)
4. No secrets in plaintext

## Deploy Steps
1. Build Docker image with commit SHA tag
2. Push to container registry
3. Update kustomize overlay for target env
4. Apply with kubectl
5. Wait for rollout complete
6. Run smoke tests
7. Log deployment to task tracker
```

#### Skill Template Example: add-service/SKILL.md

```markdown
---
name: add-service
description: Scaffold a new microservice following project standards
disable-model-invocation: true
---

# Add New Microservice

## Arguments
- `name`: Service name (kebab-case)
- `language`: go / python / java / typescript
- `type`: api / worker / cron

## Scaffolding
1. Create service directory under services/
2. Generate project files based on language:
   - Go: go.mod, main.go, Makefile, internal/ structure
   - Python: pyproject.toml, main.py, src/ structure
   - Java: pom.xml, Application.java, src/main/ structure
   - TypeScript: package.json, src/index.ts, tsconfig.json
3. Create Dockerfile following project Dockerfile standards
4. Create K8s manifests (deployment, service, configmap, hpa)
5. Add to docker-compose.dev.yml
6. Create .gitlab-ci.yml include for service pipeline
7. Create README.md with service documentation
8. Add Prometheus ServiceMonitor
9. Add Fluentd log parsing config
10. Register service in API Gateway routes
```

---

### E. Automation Generation Trigger

**When to auto-generate all of the above:**

| Trigger                                       | What to Generate                     |
|-----------------------------------------------|--------------------------------------|
| New project scaffolded from scratch            | ALL automations (hooks + MCP + agents + skills) |
| New microservice added to existing project     | Hooks update + relevant agents + skills |
| Major feature with new tech (e.g., added Redis)| Add relevant MCP server + update hooks |
| User runs `/setup-automations`                 | Re-scan project and regenerate all   |

### Post-Generation Checklist

After auto-generating automations, print:

```
╔══════════════════════════════════════════════════════════════╗
║  CLAUDE CODE AUTOMATIONS — Auto-Generated                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ⚡ Hooks:                                                   ║
║     ✓ auto-format (prettier/gofmt/ruff)                      ║
║     ✓ auto-lint (eslint/ruff/go vet)                         ║
║     ✓ block-env-edits                                        ║
║     ✓ validate-k8s-manifests                                 ║
║     ✓ track-all-changes                                      ║
║                                                              ║
║  🔌 MCP Servers (.mcp.json):                                 ║
║     ✓ context7 (library docs)                                ║
║     ✓ playwright (UI testing)                                ║
║     ✓ postgres (database)                                    ║
║     ✓ kubernetes (cluster ops)                               ║
║                                                              ║
║  🤖 Agents (.claude/agents/):                                ║
║     ✓ code-reviewer                                          ║
║     ✓ security-reviewer                                      ║
║     ✓ test-writer                                            ║
║                                                              ║
║  🎯 Skills (.claude/skills/):                                ║
║     ✓ /gen-test — Generate tests for any file                ║
║     ✓ /deploy — Deploy to K8s                                ║
║     ✓ /add-service — Scaffold new microservice               ║
║     ✓ /api-doc — Generate OpenAPI documentation              ║
║                                                              ║
║  📝 Note: .mcp.json is git-tracked for team sharing          ║
║  📝 Note: .claude/settings.json is project-specific          ║
║  📝 Note: Update .env with required tokens for MCP servers   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

CLAUDEMD20_EOF

print_success "Section 20 (Auto-Generate Automations) appended"

# ─── 4. Initialize SQLite Database ──────────────────────────────────────────
print_step "Initializing SQLite task tracking database..."

# Check for sqlite3
if command -v sqlite3 &> /dev/null; then
    sqlite3 "$TASK_DB" << 'SQL_EOF'
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    session_uuid TEXT NOT NULL UNIQUE,
    goal TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    failed_tasks INTEGER DEFAULT 0,
    files_created INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    summary TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    metadata TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS file_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_id INTEGER,
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS commands_executed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_id INTEGER,
    command TEXT NOT NULL,
    exit_code INTEGER,
    output_summary TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS resources_created (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    resource_type TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    task_id INTEGER,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    resolution TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    total_sessions INTEGER DEFAULT 0,
    total_tasks INTEGER DEFAULT 0,
    total_files_changed INTEGER DEFAULT 0,
    total_commands INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    highlights TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    report_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_file_changes_session ON file_changes(session_id);
CREATE INDEX IF NOT EXISTS idx_commands_session ON commands_executed(session_id);
CREATE INDEX IF NOT EXISTS idx_errors_session ON errors(session_id);

-- Views
CREATE VIEW IF NOT EXISTS v_session_summary AS
SELECT
    s.session_uuid,
    p.name as project_name,
    s.goal,
    s.started_at,
    s.ended_at,
    s.total_tasks,
    s.completed_tasks,
    s.files_created + s.files_modified as total_file_changes,
    (SELECT COUNT(*) FROM errors e WHERE e.session_id = s.id) as error_count
FROM sessions s
JOIN projects p ON s.project_id = p.id
ORDER BY s.started_at DESC;

CREATE VIEW IF NOT EXISTS v_daily_activity AS
SELECT
    DATE(s.started_at) as date,
    COUNT(DISTINCT s.id) as sessions,
    SUM(s.total_tasks) as tasks,
    SUM(s.files_created) as files_created,
    SUM(s.files_modified) as files_modified
FROM sessions s
GROUP BY DATE(s.started_at)
ORDER BY date DESC;
SQL_EOF
    print_success "SQLite database initialized with full schema"
else
    print_warn "sqlite3 not found — database will be created on first Claude Code session"
    touch "$TASK_DB.pending"
fi

# ─── 5. Create Global Log Files ─────────────────────────────────────────────
print_step "Creating global log files..."

cat > "$TASK_LOG_DIR/GLOBAL_LOG.md" << 'GLOBALLOG_EOF'
# Claude Code — Global Activity Log
> Auto-maintained across all projects

| Date | Project | Session Goal | Tasks | Files | Errors |
|------|---------|-------------|-------|-------|--------|
GLOBALLOG_EOF

cat > "$TASK_LOG_DIR/SUMMARY.md" << 'SUMMARY_EOF'
# Claude Code — All-Time Summary

## Statistics
- Total Sessions: 0
- Total Tasks Completed: 0
- Total Files Created: 0
- Total Files Modified: 0
- Total Errors Resolved: 0

## Projects
(auto-populated)

## Last Updated
Never — will update after first session
SUMMARY_EOF

print_success "Global log files created"

# ─── 6. Create task-tracker helper script ────────────────────────────────────
print_step "Creating task-tracker helper script..."

cat > "$TASK_LOG_DIR/task-tracker.sh" << 'TRACKER_EOF'
#!/usr/bin/env bash
# task-tracker.sh — Helper for querying Claude Code task history
DB="$HOME/.claude/task-log/claude-tasks.db"

case "${1:-help}" in
    sessions)
        sqlite3 -header -column "$DB" "SELECT * FROM v_session_summary LIMIT ${2:-20};"
        ;;
    daily)
        sqlite3 -header -column "$DB" "SELECT * FROM v_daily_activity LIMIT ${2:-30};"
        ;;
    tasks)
        sqlite3 -header -column "$DB" \
            "SELECT t.id, t.task_type, t.description, t.status, t.started_at
             FROM tasks t
             JOIN sessions s ON t.session_id = s.id
             ORDER BY t.started_at DESC LIMIT ${2:-50};"
        ;;
    errors)
        sqlite3 -header -column "$DB" \
            "SELECT e.error_type, e.error_message, e.resolution, e.timestamp
             FROM errors e
             ORDER BY e.timestamp DESC LIMIT ${2:-20};"
        ;;
    files)
        sqlite3 -header -column "$DB" \
            "SELECT fc.file_path, fc.change_type, fc.lines_added, fc.lines_removed, fc.timestamp
             FROM file_changes fc
             ORDER BY fc.timestamp DESC LIMIT ${2:-50};"
        ;;
    stats)
        echo "=== Claude Code Statistics ==="
        sqlite3 "$DB" "SELECT 'Total Sessions: ' || COUNT(*) FROM sessions;"
        sqlite3 "$DB" "SELECT 'Total Tasks: ' || COUNT(*) FROM tasks;"
        sqlite3 "$DB" "SELECT 'Total File Changes: ' || COUNT(*) FROM file_changes;"
        sqlite3 "$DB" "SELECT 'Total Commands: ' || COUNT(*) FROM commands_executed;"
        sqlite3 "$DB" "SELECT 'Total Errors: ' || COUNT(*) FROM errors;"
        ;;
    *)
        echo "Usage: task-tracker.sh {sessions|daily|tasks|errors|files|stats} [limit]"
        echo ""
        echo "Commands:"
        echo "  sessions [n]  — Show last n sessions (default 20)"
        echo "  daily [n]     — Show daily activity (default 30 days)"
        echo "  tasks [n]     — Show last n tasks (default 50)"
        echo "  errors [n]    — Show last n errors (default 20)"
        echo "  files [n]     — Show last n file changes (default 50)"
        echo "  stats         — Show all-time statistics"
        ;;
esac
TRACKER_EOF

chmod +x "$TASK_LOG_DIR/task-tracker.sh"
print_success "task-tracker.sh created"

# ─── 7. Verification ────────────────────────────────────────────────────────
print_header "Verification"

PASS=0
FAIL=0

check() {
    if [ -e "$1" ]; then
        print_success "$2"
        ((PASS++))
    else
        print_error "$2 — MISSING"
        ((FAIL++))
    fi
}

check "$SETTINGS_FILE" "settings.json"
check "$CLAUDE_MD" "CLAUDE.md"
check "$TASK_LOG_DIR" "task-log directory"
check "$TASK_DB" "SQLite database (or .pending)"
check "$TASK_LOG_DIR/GLOBAL_LOG.md" "Global log"
check "$TASK_LOG_DIR/SUMMARY.md" "Summary"
check "$TASK_LOG_DIR/task-tracker.sh" "task-tracker.sh"
check "$REPORTS_DIR/sessions" "Reports — sessions dir"
check "$REPORTS_DIR/weekly" "Reports — weekly dir"

# Check CLAUDE.md size
if [ -f "$CLAUDE_MD" ]; then
    LINES=$(wc -l < "$CLAUDE_MD")
    SIZE=$(du -h "$CLAUDE_MD" | cut -f1)
    echo -e "\n  ${CYAN}CLAUDE.md:${NC} $LINES lines, $SIZE"
fi

# Check DB tables
if command -v sqlite3 &> /dev/null && [ -f "$TASK_DB" ]; then
    TABLES=$(sqlite3 "$TASK_DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
    VIEWS=$(sqlite3 "$TASK_DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='view';")
    echo -e "  ${CYAN}Database:${NC} $TABLES tables, $VIEWS views"
fi

# ─── Final Summary ──────────────────────────────────────────────────────────
print_header "Setup Complete"
echo ""
echo -e "  ${GREEN}Passed:${NC} $PASS checks"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed:${NC} $FAIL checks"
fi
echo ""
echo -e "  ${CYAN}Files created:${NC}"
echo -e "    $SETTINGS_FILE"
echo -e "    $CLAUDE_MD"
echo -e "    $TASK_DB"
echo -e "    $TASK_LOG_DIR/GLOBAL_LOG.md"
echo -e "    $TASK_LOG_DIR/SUMMARY.md"
echo -e "    $TASK_LOG_DIR/task-tracker.sh"
echo -e "    $REPORTS_DIR/"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "    1. Edit ${SETTINGS_FILE} to add your real GitLab/K8s/Grafana tokens"
echo -e "    2. Open VS Code and start Claude Code"
echo -e "    3. Describe any project idea — it will auto-follow all standards"
echo -e "    4. Use ${TASK_LOG_DIR}/task-tracker.sh to query task history"
echo ""
echo -e "  ${GREEN}Happy engineering!${NC}"
echo ""
