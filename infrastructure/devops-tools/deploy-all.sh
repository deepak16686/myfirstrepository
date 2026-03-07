#!/bin/bash
###############################################################################
# MASTER DEPLOYMENT SCRIPT — Deploy 80+ DevOps Tools on Docker Desktop K8s
# All services exposed via NodePort for localhost access
# Minimal resource limits to fit on single node
###############################################################################
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

###############################################################################
# PHASE 0: Create all namespaces
###############################################################################
phase_namespaces() {
  info "Creating namespaces..."
  for ns in gitea gogs forgejo onedev gitlab \
            drone woodpecker tekton argo-workflows gocd concourse \
            artifactory docker-registry verdaccio zot \
            portainer rancher kubernetes-dashboard flux-system helm-dashboard \
            awx atlantis \
            thanos mimir victoriametrics zabbix nagios icinga uptime-kuma netdata \
            logstash fluentd loki graylog opensearch \
            zipkin signoz otel-collector tempo sentry elastic-apm \
            clair anchore defectdojo owasp-zap falco \
            conjur infisical \
            keycloak istio-system linkerd consul traefik nginx-ingress haproxy kong apisix \
            mysql mariadb rabbitmq kafka nats etcd-cluster \
            wikijs bookstack outline mattermost rocketchat backstage; do
    kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null
  done
  log "All namespaces created"
}

###############################################################################
# PHASE 1: Add all Helm repos
###############################################################################
phase_helm_repos() {
  info "Adding Helm repositories..."
  declare -A repos=(
    ["gitea-charts"]="https://dl.gitea.com/charts/"
    ["gogs"]="https://gogs.github.io/helm-chart/"
    ["forgejo"]="https://codeberg.org/forgejo-contrib/helm-chart/raw/branch/main"
    ["drone"]="https://charts.drone.io"
    ["woodpecker"]="https://woodpecker-ci.org/helm"
    ["argo"]="https://argoproj.github.io/argo-helm"
    ["gocd"]="https://gocd.github.io/helm-chart"
    ["concourse"]="https://concourse-charts.storage.googleapis.com/"
    ["jfrog"]="https://charts.jfrog.io"
    ["twuni"]="https://helm.twun.io"
    ["verdaccio"]="https://charts.verdaccio.org"
    ["portainer"]="https://portainer.github.io/k8s/"
    ["rancher-latest"]="https://releases.rancher.com/server-charts/latest"
    ["kubernetes-dashboard"]="https://kubernetes.github.io/dashboard/"
    ["fluxcd"]="https://fluxcd-community.github.io/helm-charts"
    ["helm-dashboard"]="https://helm-dashboard.github.io/helm-dashboard"
    ["awx-operator"]="https://ansible-community.github.io/awx-operator-helm/"
    ["atlantis"]="https://runatlantis.github.io/helm-charts"
    ["thanos"]="https://charts.bitnami.com/bitnami"
    ["grafana"]="https://grafana.github.io/helm-charts"
    ["victoriametrics"]="https://victoriametrics.github.io/helm-charts/"
    ["zabbix"]="https://zabbix-community.github.io/helm-zabbix/"
    ["nagios"]="https://nagios-helm.github.io/nagios-helm/"
    ["uptime-kuma"]="https://dirsigler.github.io/uptime-kuma-helm"
    ["netdata"]="https://netdata.github.io/helmchart/"
    ["elastic"]="https://helm.elastic.co"
    ["fluent"]="https://fluent.github.io/helm-charts"
    ["graylog"]="https://charts.graylog.org"
    ["opensearch"]="https://opensearch-project.github.io/helm-charts/"
    ["signoz"]="https://charts.signoz.io"
    ["open-telemetry"]="https://open-telemetry.github.io/opentelemetry-helm-charts"
    ["sentry"]="https://sentry-kubernetes.github.io/charts"
    ["anchore"]="https://charts.anchore.io"
    ["defectdojo"]="https://raw.githubusercontent.com/DefectDojo/django-DefectDojo/helm-charts"
    ["falcosecurity"]="https://falcosecurity.github.io/charts"
    ["conjur"]="https://cyberark.github.io/helm-charts"
    ["infisical"]="https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/"
    ["codecentric"]="https://codecentric.github.io/helm-charts"
    ["istio"]="https://istio-release.storage.googleapis.com/charts"
    ["linkerd"]="https://helm.linkerd.io/edge"
    ["hashicorp"]="https://helm.releases.hashicorp.com"
    ["traefik"]="https://traefik.github.io/charts"
    ["ingress-nginx"]="https://kubernetes.github.io/ingress-nginx"
    ["haproxy"]="https://haproxytech.github.io/helm-charts"
    ["kong"]="https://charts.konghq.com"
    ["apisix"]="https://charts.apiseven.com"
    ["bitnami"]="https://charts.bitnami.com/bitnami"
    ["strimzi"]="https://strimzi.io/charts/"
    ["nats"]="https://nats-io.github.io/k8s/helm/charts/"
    ["wikijs"]="https://charts.js.wiki"
    ["bookstack"]="https://charts.jb2.nl"
    ["outline"]="https://gitlab.com/api/v4/projects/52218399/packages/helm/main"
    ["mattermost"]="https://helm.mattermost.com"
    ["rocketchat"]="https://rocketchat.github.io/helm-charts"
    ["backstage"]="https://backstage.github.io/charts"
    ["cert-manager"]="https://charts.jetstack.io"
  )

  for repo in "${!repos[@]}"; do
    helm repo add "$repo" "${repos[$repo]}" 2>/dev/null || true
  done
  helm repo update 2>/dev/null
  log "All Helm repos added and updated"
}

###############################################################################
# Deploy functions by category
###############################################################################

deploy_git_platforms() {
  info "=== BATCH 1: Git Platforms ==="

  # Gitea (lightweight, port 30201)
  helm upgrade --install gitea gitea-charts/gitea \
    --namespace gitea --create-namespace \
    --set resources.requests.cpu=50m \
    --set resources.requests.memory=128Mi \
    --set resources.limits.cpu=500m \
    --set resources.limits.memory=512Mi \
    --set service.http.type=NodePort \
    --set service.http.nodePort=30201 \
    --set service.ssh.type=NodePort \
    --set service.ssh.nodePort=30202 \
    --set persistence.size=5Gi \
    --set "gitea.admin.username=admin" \
    --set "gitea.admin.password=Admin@123" \
    --set postgresql-ha.enabled=false \
    --set postgresql.enabled=true \
    --set postgresql.primary.resources.requests.cpu=25m \
    --set postgresql.primary.resources.requests.memory=64Mi \
    --set redis-cluster.enabled=false \
    --set redis.enabled=false \
    --set test.enabled=false \
    --wait --timeout 5m 2>&1 || warn "Gitea install issue"
  log "Gitea deployed (port 30201)"

  # Gogs (very lightweight, port 30203)
  kubectl apply -n gogs -f "$SCRIPT_DIR/manifests/gogs.yaml" 2>&1 || warn "Gogs issue"
  log "Gogs deployed (port 30203)"

  # Forgejo (Gitea fork, port 30204)
  kubectl apply -n forgejo -f "$SCRIPT_DIR/manifests/forgejo.yaml" 2>&1 || warn "Forgejo issue"
  log "Forgejo deployed (port 30204)"

  # OneDev (port 30205)
  kubectl apply -n onedev -f "$SCRIPT_DIR/manifests/onedev.yaml" 2>&1 || warn "OneDev issue"
  log "OneDev deployed (port 30205)"

  # GitLab (heavy — using minimal CE, port 30200)
  kubectl apply -n gitlab -f "$SCRIPT_DIR/manifests/gitlab.yaml" 2>&1 || warn "GitLab issue"
  log "GitLab deployed (port 30200) — takes 5-10 min to start"
}

deploy_cicd() {
  info "=== BATCH 2: CI/CD Tools ==="

  # Drone CI (port 30210)
  kubectl apply -n drone -f "$SCRIPT_DIR/manifests/drone.yaml" 2>&1 || warn "Drone issue"
  log "Drone CI deployed (port 30210)"

  # Woodpecker CI (port 30211)
  kubectl apply -n woodpecker -f "$SCRIPT_DIR/manifests/woodpecker.yaml" 2>&1 || warn "Woodpecker issue"
  log "Woodpecker CI deployed (port 30211)"

  # Tekton Pipelines + Dashboard (port 30212)
  kubectl apply -f https://storage.googleapis.com/tekton-releases/pipeline/latest/release.yaml 2>&1 || warn "Tekton pipelines issue"
  kubectl apply -f https://storage.googleapis.com/tekton-releases/dashboard/latest/release.yaml 2>&1 || warn "Tekton dashboard issue"
  kubectl -n tekton-pipelines patch svc tekton-dashboard --type='json' \
    -p='[{"op":"replace","path":"/spec/type","value":"NodePort"},{"op":"add","path":"/spec/ports/0/nodePort","value":30212}]' 2>&1 || warn "Tekton patch issue"
  log "Tekton deployed (port 30212)"

  # Argo Workflows (port 30213)
  helm upgrade --install argo-workflows argo/argo-workflows \
    --namespace argo-workflows --create-namespace \
    --set server.serviceType=NodePort \
    --set server.serviceNodePort=30213 \
    --set controller.resources.requests.cpu=25m \
    --set controller.resources.requests.memory=64Mi \
    --set controller.resources.limits.cpu=200m \
    --set controller.resources.limits.memory=256Mi \
    --set server.resources.requests.cpu=25m \
    --set server.resources.requests.memory=64Mi \
    --set server.resources.limits.cpu=200m \
    --set server.resources.limits.memory=256Mi \
    --set server.extraArgs="{--auth-mode=server}" \
    --wait --timeout 5m 2>&1 || warn "Argo Workflows issue"
  log "Argo Workflows deployed (port 30213)"

  # GoCD (port 30214)
  helm upgrade --install gocd gocd/gocd \
    --namespace gocd --create-namespace \
    --set server.service.type=NodePort \
    --set server.service.nodePort=30214 \
    --set server.resources.requests.cpu=50m \
    --set server.resources.requests.memory=256Mi \
    --set server.resources.limits.cpu=500m \
    --set server.resources.limits.memory=1Gi \
    --set agent.replicaCount=0 \
    --wait --timeout 5m 2>&1 || warn "GoCD issue"
  log "GoCD deployed (port 30214)"

  # Concourse CI (port 30215)
  helm upgrade --install concourse concourse/concourse \
    --namespace concourse --create-namespace \
    --set web.service.type=NodePort \
    --set web.service.atc.nodePort=30215 \
    --set concourse.web.externalUrl=http://localhost:30215 \
    --set web.resources.requests.cpu=50m \
    --set web.resources.requests.memory=128Mi \
    --set web.resources.limits.cpu=500m \
    --set web.resources.limits.memory=512Mi \
    --set worker.replicas=1 \
    --set worker.resources.requests.cpu=50m \
    --set worker.resources.requests.memory=128Mi \
    --set worker.resources.limits.cpu=500m \
    --set worker.resources.limits.memory=1Gi \
    --set secrets.localUsers="admin:Admin@123" \
    --wait --timeout 5m 2>&1 || warn "Concourse issue"
  log "Concourse CI deployed (port 30215)"

  # Buildkite Agent (no UI, agent only, port N/A)
  kubectl apply -n default -f "$SCRIPT_DIR/manifests/buildkite-agent.yaml" 2>&1 || warn "Buildkite issue"
  log "Buildkite Agent deployed (agent-only, no UI)"
}

deploy_artifact_repos() {
  info "=== BATCH 3: Artifact Repositories ==="

  # JFrog Artifactory OSS (port 30220)
  kubectl apply -n artifactory -f "$SCRIPT_DIR/manifests/artifactory.yaml" 2>&1 || warn "Artifactory issue"
  log "Artifactory OSS deployed (port 30220)"

  # Docker Registry (port 30221)
  kubectl apply -n docker-registry -f "$SCRIPT_DIR/manifests/docker-registry.yaml" 2>&1 || warn "Docker Registry issue"
  log "Docker Registry deployed (port 30221)"

  # Verdaccio npm registry (port 30222)
  helm upgrade --install verdaccio verdaccio/verdaccio \
    --namespace verdaccio --create-namespace \
    --set service.type=NodePort \
    --set service.nodePort=30222 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "Verdaccio issue"
  log "Verdaccio deployed (port 30222)"

  # Zot OCI registry (port 30224)
  kubectl apply -n zot -f "$SCRIPT_DIR/manifests/zot.yaml" 2>&1 || warn "Zot issue"
  log "Zot deployed (port 30224)"
}

deploy_management() {
  info "=== BATCH 4: Management Tools ==="

  # Portainer (port 30230)
  helm upgrade --install portainer portainer/portainer \
    --namespace portainer --create-namespace \
    --set service.type=NodePort \
    --set service.nodePort=30230 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "Portainer issue"
  log "Portainer deployed (port 30230)"

  # Kubernetes Dashboard (port 30232)
  helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard \
    --namespace kubernetes-dashboard --create-namespace \
    --set service.type=NodePort \
    --set service.nodePort=30232 \
    --wait --timeout 3m 2>&1 || warn "K8s Dashboard issue"
  log "Kubernetes Dashboard deployed (port 30232)"

  # Helm Dashboard (port 30234)
  helm upgrade --install helm-dashboard helm-dashboard/helm-dashboard \
    --namespace helm-dashboard --create-namespace \
    --set service.type=NodePort \
    --set service.nodePort=30234 \
    --wait --timeout 3m 2>&1 || warn "Helm Dashboard issue"
  log "Helm Dashboard deployed (port 30234)"

  # Flux CD (controllers, no UI — port 30233 for notification receiver)
  kubectl apply -f https://github.com/fluxcd/flux2/releases/latest/download/install.yaml 2>&1 || warn "Flux CD issue"
  log "Flux CD deployed (controllers only)"

  # Rancher (port 30231) — needs cert-manager
  helm upgrade --install cert-manager cert-manager/cert-manager \
    --namespace cert-manager --create-namespace \
    --set crds.enabled=true \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --wait --timeout 3m 2>&1 || warn "cert-manager issue"
  helm upgrade --install rancher rancher-latest/rancher \
    --namespace rancher --create-namespace \
    --set hostname=rancher.localhost \
    --set replicas=1 \
    --set bootstrapPassword=Admin@123 \
    --set resources.requests.cpu=50m \
    --set resources.requests.memory=256Mi \
    --set resources.limits.cpu=500m \
    --set resources.limits.memory=1Gi \
    --wait --timeout 5m 2>&1 || warn "Rancher issue"
  kubectl -n rancher patch svc rancher --type='json' \
    -p='[{"op":"replace","path":"/spec/type","value":"NodePort"},{"op":"add","path":"/spec/ports/0/nodePort","value":30231}]' 2>&1 || true
  log "Rancher deployed (port 30231)"
}

deploy_iac_config() {
  info "=== BATCH 5: IaC / Config Management ==="

  # AWX (Ansible Tower, port 30235)
  helm upgrade --install awx-operator awx-operator/awx-operator \
    --namespace awx --create-namespace \
    --set AWX.enabled=true \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --wait --timeout 5m 2>&1 || warn "AWX operator issue"
  kubectl apply -n awx -f "$SCRIPT_DIR/manifests/awx-instance.yaml" 2>&1 || warn "AWX instance issue"
  log "AWX deployed (port 30235)"

  # Atlantis (port 30237)
  kubectl apply -n atlantis -f "$SCRIPT_DIR/manifests/atlantis.yaml" 2>&1 || warn "Atlantis issue"
  log "Atlantis deployed (port 30237)"
}

deploy_monitoring() {
  info "=== BATCH 6: Monitoring ==="

  # Victoria Metrics (port 30242)
  helm upgrade --install victoria-metrics victoriametrics/victoria-metrics-single \
    --namespace victoriametrics --create-namespace \
    --set server.service.type=NodePort \
    --set server.service.nodePort=30242 \
    --set server.resources.requests.cpu=25m \
    --set server.resources.requests.memory=128Mi \
    --set server.resources.limits.cpu=500m \
    --set server.resources.limits.memory=512Mi \
    --wait --timeout 3m 2>&1 || warn "VictoriaMetrics issue"
  log "Victoria Metrics deployed (port 30242)"

  # Thanos (port 30240 — query frontend)
  kubectl apply -n thanos -f "$SCRIPT_DIR/manifests/thanos.yaml" 2>&1 || warn "Thanos issue"
  log "Thanos deployed (port 30240)"

  # Mimir (port 30241)
  kubectl apply -n mimir -f "$SCRIPT_DIR/manifests/mimir.yaml" 2>&1 || warn "Mimir issue"
  log "Mimir deployed (port 30241)"

  # Zabbix (port 30243)
  kubectl apply -n zabbix -f "$SCRIPT_DIR/manifests/zabbix.yaml" 2>&1 || warn "Zabbix issue"
  log "Zabbix deployed (port 30243)"

  # Nagios (port 30244)
  kubectl apply -n nagios -f "$SCRIPT_DIR/manifests/nagios.yaml" 2>&1 || warn "Nagios issue"
  log "Nagios deployed (port 30244)"

  # Icinga (port 30245)
  kubectl apply -n icinga -f "$SCRIPT_DIR/manifests/icinga.yaml" 2>&1 || warn "Icinga issue"
  log "Icinga deployed (port 30245)"

  # Uptime Kuma (port 30246)
  helm upgrade --install uptime-kuma uptime-kuma/uptime-kuma \
    --namespace uptime-kuma --create-namespace \
    --set service.type=NodePort \
    --set service.nodePort=30246 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "Uptime Kuma issue"
  log "Uptime Kuma deployed (port 30246)"

  # Netdata (port 30247)
  helm upgrade --install netdata netdata/netdata \
    --namespace netdata --create-namespace \
    --set parent.service.type=NodePort \
    --set parent.service.nodePort=30247 \
    --set parent.resources.requests.cpu=25m \
    --set parent.resources.requests.memory=128Mi \
    --set parent.resources.limits.cpu=500m \
    --set parent.resources.limits.memory=512Mi \
    --set child.resources.requests.cpu=25m \
    --set child.resources.requests.memory=64Mi \
    --set child.resources.limits.cpu=200m \
    --set child.resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "Netdata issue"
  log "Netdata deployed (port 30247)"
}

deploy_logging() {
  info "=== BATCH 7: Logging ==="

  # Loki (port 30252)
  helm upgrade --install loki grafana/loki \
    --namespace loki --create-namespace \
    --set loki.auth_enabled=false \
    --set singleBinary.replicas=1 \
    --set singleBinary.resources.requests.cpu=25m \
    --set singleBinary.resources.requests.memory=128Mi \
    --set singleBinary.resources.limits.cpu=500m \
    --set singleBinary.resources.limits.memory=512Mi \
    --set loki.commonConfig.replication_factor=1 \
    --set loki.storage.type=filesystem \
    --set monitoring.selfMonitoring.enabled=false \
    --set monitoring.lokiCanary.enabled=false \
    --set test.enabled=false \
    --set gateway.enabled=false \
    --wait --timeout 5m 2>&1 || warn "Loki issue"
  kubectl -n loki patch svc loki --type='json' \
    -p='[{"op":"replace","path":"/spec/type","value":"NodePort"},{"op":"add","path":"/spec/ports/0/nodePort","value":30252}]' 2>&1 || true
  log "Loki deployed (port 30252)"

  # Fluentd (DaemonSet, port 30251 for forward input)
  helm upgrade --install fluentd fluent/fluentd \
    --namespace fluentd --create-namespace \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "Fluentd issue"
  log "Fluentd deployed"

  # Logstash (port 30250)
  kubectl apply -n logstash -f "$SCRIPT_DIR/manifests/logstash.yaml" 2>&1 || warn "Logstash issue"
  log "Logstash deployed (port 30250)"

  # Graylog (port 30253)
  kubectl apply -n graylog -f "$SCRIPT_DIR/manifests/graylog.yaml" 2>&1 || warn "Graylog issue"
  log "Graylog deployed (port 30253)"

  # OpenSearch + Dashboards (port 30254/30255)
  helm upgrade --install opensearch opensearch/opensearch \
    --namespace opensearch --create-namespace \
    --set singleNode=true \
    --set replicas=1 \
    --set resources.requests.cpu=50m \
    --set resources.requests.memory=256Mi \
    --set resources.limits.cpu=500m \
    --set resources.limits.memory=1Gi \
    --set persistence.size=5Gi \
    --wait --timeout 5m 2>&1 || warn "OpenSearch issue"
  helm upgrade --install opensearch-dashboards opensearch/opensearch-dashboards \
    --namespace opensearch \
    --set service.type=NodePort \
    --set service.nodePort=30255 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=128Mi \
    --set resources.limits.cpu=500m \
    --set resources.limits.memory=512Mi \
    --wait --timeout 5m 2>&1 || warn "OpenSearch Dashboards issue"
  log "OpenSearch deployed (port 30255)"
}

deploy_tracing() {
  info "=== BATCH 8: Tracing & APM ==="

  # Zipkin (port 30260)
  kubectl apply -n zipkin -f "$SCRIPT_DIR/manifests/zipkin.yaml" 2>&1 || warn "Zipkin issue"
  log "Zipkin deployed (port 30260)"

  # SigNoz (port 30261)
  kubectl apply -n signoz -f "$SCRIPT_DIR/manifests/signoz.yaml" 2>&1 || warn "SigNoz issue"
  log "SigNoz deployed (port 30261)"

  # OpenTelemetry Collector (port 30262)
  helm upgrade --install otel-collector open-telemetry/opentelemetry-collector \
    --namespace otel-collector --create-namespace \
    --set mode=deployment \
    --set service.type=NodePort \
    --set ports.otlp.servicePort=4317 \
    --set ports.otlp-http.servicePort=4318 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "OTel Collector issue"
  log "OpenTelemetry Collector deployed (port 30262)"

  # Grafana Tempo (port 30263)
  helm upgrade --install tempo grafana/tempo \
    --namespace tempo --create-namespace \
    --set tempo.resources.requests.cpu=25m \
    --set tempo.resources.requests.memory=128Mi \
    --set tempo.resources.limits.cpu=500m \
    --set tempo.resources.limits.memory=512Mi \
    --wait --timeout 3m 2>&1 || warn "Tempo issue"
  kubectl -n tempo patch svc tempo --type='json' \
    -p='[{"op":"replace","path":"/spec/type","value":"NodePort"},{"op":"add","path":"/spec/ports/0/nodePort","value":30263}]' 2>&1 || true
  log "Grafana Tempo deployed (port 30263)"

  # Sentry (port 30264 — self-hosted, heavy)
  kubectl apply -n sentry -f "$SCRIPT_DIR/manifests/sentry.yaml" 2>&1 || warn "Sentry issue"
  log "Sentry deployed (port 30264)"

  # Elastic APM Server (port 30265)
  kubectl apply -n elastic-apm -f "$SCRIPT_DIR/manifests/elastic-apm.yaml" 2>&1 || warn "Elastic APM issue"
  log "Elastic APM deployed (port 30265)"
}

deploy_security() {
  info "=== BATCH 9: Security Tools ==="

  # Clair (port 30270)
  kubectl apply -n clair -f "$SCRIPT_DIR/manifests/clair.yaml" 2>&1 || warn "Clair issue"
  log "Clair deployed (port 30270)"

  # Anchore (port 30271)
  kubectl apply -n anchore -f "$SCRIPT_DIR/manifests/anchore.yaml" 2>&1 || warn "Anchore issue"
  log "Anchore deployed (port 30271)"

  # DefectDojo (port 30272)
  kubectl apply -n defectdojo -f "$SCRIPT_DIR/manifests/defectdojo.yaml" 2>&1 || warn "DefectDojo issue"
  log "DefectDojo deployed (port 30272)"

  # OWASP ZAP (port 30273)
  kubectl apply -n owasp-zap -f "$SCRIPT_DIR/manifests/owasp-zap.yaml" 2>&1 || warn "OWASP ZAP issue"
  log "OWASP ZAP deployed (port 30273)"

  # Falco (DaemonSet, runtime security)
  helm upgrade --install falco falcosecurity/falco \
    --namespace falco --create-namespace \
    --set driver.kind=modern_ebpf \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --set falcosidekick.enabled=false \
    --wait --timeout 5m 2>&1 || warn "Falco issue"
  log "Falco deployed (DaemonSet)"
}

deploy_secrets() {
  info "=== BATCH 10: Secrets Management ==="

  # CyberArk Conjur (port 30280)
  kubectl apply -n conjur -f "$SCRIPT_DIR/manifests/conjur.yaml" 2>&1 || warn "Conjur issue"
  log "Conjur deployed (port 30280)"

  # Infisical (port 30281)
  kubectl apply -n infisical -f "$SCRIPT_DIR/manifests/infisical.yaml" 2>&1 || warn "Infisical issue"
  log "Infisical deployed (port 30281)"
}

deploy_networking() {
  info "=== BATCH 11: Networking & Service Mesh ==="

  # Keycloak (port 30290)
  kubectl apply -n keycloak -f "$SCRIPT_DIR/manifests/keycloak.yaml" 2>&1 || warn "Keycloak issue"
  log "Keycloak deployed (port 30290)"

  # Consul (port 30293)
  helm upgrade --install consul hashicorp/consul \
    --namespace consul --create-namespace \
    --set server.replicas=1 \
    --set server.resources.requests.cpu=25m \
    --set server.resources.requests.memory=64Mi \
    --set server.resources.limits.cpu=200m \
    --set server.resources.limits.memory=256Mi \
    --set ui.service.type=NodePort \
    --set ui.service.nodePort=30293 \
    --wait --timeout 5m 2>&1 || warn "Consul issue"
  log "Consul deployed (port 30293)"

  # Traefik (port 30294)
  helm upgrade --install traefik traefik/traefik \
    --namespace traefik --create-namespace \
    --set service.type=NodePort \
    --set ports.web.nodePort=30294 \
    --set ports.websecure.nodePort=30295 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --set dashboard.enabled=true \
    --set ingressRoute.dashboard.enabled=true \
    --wait --timeout 3m 2>&1 || warn "Traefik issue"
  log "Traefik deployed (port 30294)"

  # Nginx Ingress Controller (port 30296)
  helm upgrade --install nginx-ingress ingress-nginx/ingress-nginx \
    --namespace nginx-ingress --create-namespace \
    --set controller.service.type=NodePort \
    --set controller.service.nodePorts.http=30296 \
    --set controller.service.nodePorts.https=30297 \
    --set controller.resources.requests.cpu=25m \
    --set controller.resources.requests.memory=64Mi \
    --set controller.resources.limits.cpu=200m \
    --set controller.resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "Nginx Ingress issue"
  log "Nginx Ingress deployed (port 30296)"

  # Kong (port 30298)
  helm upgrade --install kong kong/kong \
    --namespace kong --create-namespace \
    --set proxy.type=NodePort \
    --set proxy.http.nodePort=30298 \
    --set admin.enabled=true \
    --set admin.type=NodePort \
    --set admin.http.nodePort=30299 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=64Mi \
    --set resources.limits.cpu=200m \
    --set resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "Kong issue"
  log "Kong deployed (port 30298)"

  # APISIX (port 30310)
  kubectl apply -n apisix -f "$SCRIPT_DIR/manifests/apisix.yaml" 2>&1 || warn "APISIX issue"
  log "APISIX deployed (port 30310)"

  # HAProxy (port 30312)
  kubectl apply -n haproxy -f "$SCRIPT_DIR/manifests/haproxy.yaml" 2>&1 || warn "HAProxy issue"
  log "HAProxy deployed (port 30312)"

  # Envoy (port 30314)
  kubectl apply -n default -f "$SCRIPT_DIR/manifests/envoy.yaml" 2>&1 || warn "Envoy issue"
  log "Envoy deployed (port 30314)"

  # Istio (control plane)
  helm upgrade --install istio-base istio/base \
    --namespace istio-system --create-namespace \
    --wait --timeout 3m 2>&1 || warn "Istio base issue"
  helm upgrade --install istiod istio/istiod \
    --namespace istio-system \
    --set pilot.resources.requests.cpu=25m \
    --set pilot.resources.requests.memory=128Mi \
    --set pilot.resources.limits.cpu=500m \
    --set pilot.resources.limits.memory=512Mi \
    --wait --timeout 5m 2>&1 || warn "Istiod issue"
  log "Istio deployed (control plane)"

  # Linkerd (port 30316 for dashboard)
  kubectl apply -n linkerd -f "$SCRIPT_DIR/manifests/linkerd.yaml" 2>&1 || warn "Linkerd issue"
  log "Linkerd deployed (port 30316)"
}

deploy_databases() {
  info "=== BATCH 12: Databases & Messaging ==="

  # PostgreSQL standalone (port 30400)
  helm upgrade --install postgresql bitnami/postgresql \
    --namespace default \
    --set primary.service.type=NodePort \
    --set primary.service.nodePorts.postgresql=30400 \
    --set auth.postgresPassword=Admin@123 \
    --set primary.resources.requests.cpu=25m \
    --set primary.resources.requests.memory=128Mi \
    --set primary.resources.limits.cpu=500m \
    --set primary.resources.limits.memory=512Mi \
    --set primary.persistence.size=5Gi \
    --wait --timeout 3m 2>&1 || warn "PostgreSQL issue"
  log "PostgreSQL deployed (port 30400)"

  # MySQL (port 30401)
  helm upgrade --install mysql bitnami/mysql \
    --namespace mysql --create-namespace \
    --set primary.service.type=NodePort \
    --set primary.service.nodePorts.mysql=30401 \
    --set auth.rootPassword=Admin@123 \
    --set primary.resources.requests.cpu=25m \
    --set primary.resources.requests.memory=128Mi \
    --set primary.resources.limits.cpu=500m \
    --set primary.resources.limits.memory=512Mi \
    --set primary.persistence.size=5Gi \
    --wait --timeout 3m 2>&1 || warn "MySQL issue"
  log "MySQL deployed (port 30401)"

  # MariaDB (port 30402)
  helm upgrade --install mariadb bitnami/mariadb \
    --namespace mariadb --create-namespace \
    --set primary.service.type=NodePort \
    --set primary.service.nodePorts.mysql=30402 \
    --set auth.rootPassword=Admin@123 \
    --set primary.resources.requests.cpu=25m \
    --set primary.resources.requests.memory=128Mi \
    --set primary.resources.limits.cpu=500m \
    --set primary.resources.limits.memory=512Mi \
    --set primary.persistence.size=5Gi \
    --wait --timeout 3m 2>&1 || warn "MariaDB issue"
  log "MariaDB deployed (port 30402)"

  # Redis standalone (port 30403)
  helm upgrade --install redis bitnami/redis \
    --namespace default \
    --set master.service.type=NodePort \
    --set master.service.nodePorts.redis=30403 \
    --set auth.password=Admin@123 \
    --set master.resources.requests.cpu=25m \
    --set master.resources.requests.memory=64Mi \
    --set master.resources.limits.cpu=200m \
    --set master.resources.limits.memory=256Mi \
    --set replica.replicaCount=0 \
    --wait --timeout 3m 2>&1 || warn "Redis issue"
  log "Redis deployed (port 30403)"

  # RabbitMQ (port 30404 amqp, 30406 management)
  helm upgrade --install rabbitmq bitnami/rabbitmq \
    --namespace rabbitmq --create-namespace \
    --set service.type=NodePort \
    --set service.nodePorts.amqp=30404 \
    --set service.nodePorts.manager=30406 \
    --set auth.username=admin \
    --set auth.password=Admin@123 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=128Mi \
    --set resources.limits.cpu=500m \
    --set resources.limits.memory=512Mi \
    --set persistence.size=5Gi \
    --wait --timeout 3m 2>&1 || warn "RabbitMQ issue"
  log "RabbitMQ deployed (port 30404/30406)"

  # Kafka via Strimzi (port 30407)
  kubectl apply -f 'https://strimzi.io/install/latest?namespace=kafka' -n kafka 2>&1 || warn "Strimzi operator issue"
  sleep 10
  kubectl apply -n kafka -f "$SCRIPT_DIR/manifests/kafka-cluster.yaml" 2>&1 || warn "Kafka cluster issue"
  log "Kafka (Strimzi) deployed (port 30407)"

  # NATS (port 30408)
  helm upgrade --install nats nats/nats \
    --namespace nats --create-namespace \
    --set nats.resources.requests.cpu=25m \
    --set nats.resources.requests.memory=64Mi \
    --set nats.resources.limits.cpu=200m \
    --set nats.resources.limits.memory=256Mi \
    --wait --timeout 3m 2>&1 || warn "NATS issue"
  kubectl -n nats patch svc nats --type='json' \
    -p='[{"op":"replace","path":"/spec/type","value":"NodePort"},{"op":"add","path":"/spec/ports/0/nodePort","value":30408}]' 2>&1 || true
  log "NATS deployed (port 30408)"

  # etcd (port 30409)
  kubectl apply -n etcd-cluster -f "$SCRIPT_DIR/manifests/etcd.yaml" 2>&1 || warn "etcd issue"
  log "etcd deployed (port 30409)"
}

deploy_collaboration() {
  info "=== BATCH 13: Collaboration & Knowledge ==="

  # Wiki.js (port 30500)
  kubectl apply -n wikijs -f "$SCRIPT_DIR/manifests/wikijs.yaml" 2>&1 || warn "Wiki.js issue"
  log "Wiki.js deployed (port 30500)"

  # BookStack (port 30501)
  kubectl apply -n bookstack -f "$SCRIPT_DIR/manifests/bookstack.yaml" 2>&1 || warn "BookStack issue"
  log "BookStack deployed (port 30501)"

  # Outline (port 30502)
  kubectl apply -n outline -f "$SCRIPT_DIR/manifests/outline.yaml" 2>&1 || warn "Outline issue"
  log "Outline deployed (port 30502)"

  # Mattermost (port 30503)
  helm upgrade --install mattermost mattermost/mattermost-team-edition \
    --namespace mattermost --create-namespace \
    --set service.type=NodePort \
    --set service.nodePort=30503 \
    --set resources.requests.cpu=25m \
    --set resources.requests.memory=128Mi \
    --set resources.limits.cpu=500m \
    --set resources.limits.memory=512Mi \
    --set mysql.enabled=true \
    --set mysql.mysqlUser=mattermost \
    --set mysql.mysqlPassword=Admin@123 \
    --wait --timeout 5m 2>&1 || warn "Mattermost issue"
  log "Mattermost deployed (port 30503)"

  # Rocket.Chat (port 30504)
  kubectl apply -n rocketchat -f "$SCRIPT_DIR/manifests/rocketchat.yaml" 2>&1 || warn "Rocket.Chat issue"
  log "Rocket.Chat deployed (port 30504)"

  # Backstage (port 30505)
  kubectl apply -n backstage -f "$SCRIPT_DIR/manifests/backstage.yaml" 2>&1 || warn "Backstage issue"
  log "Backstage deployed (port 30505)"
}

###############################################################################
# Print summary
###############################################################################
print_summary() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════════════╗"
  echo "║              DEVOPS TOOLS DEPLOYMENT — COMPLETE                     ║"
  echo "╠══════════════════════════════════════════════════════════════════════╣"
  echo "║                                                                      ║"
  echo "║  === Already Running ===                                             ║"
  echo "║  ArgoCD           http://localhost:30443                             ║"
  echo "║  Jenkins           http://localhost:30800                             ║"
  echo "║  Harbor            http://localhost:30870                             ║"
  echo "║  Harness           http://localhost:30880                             ║"
  echo "║  Prometheus        http://localhost:30090                             ║"
  echo "║  Grafana           http://localhost:30300                             ║"
  echo "║  Alertmanager      http://localhost:30093                             ║"
  echo "║  Elasticsearch     http://localhost:30920                             ║"
  echo "║  Kibana            http://localhost:30560                             ║"
  echo "║  Jaeger            http://localhost:30860                             ║"
  echo "║  Nexus             http://localhost:30810                             ║"
  echo "║  SonarQube         http://localhost:30820                             ║"
  echo "║  Vault             http://localhost:30830                             ║"
  echo "║  MinIO             http://localhost:30840                             ║"
  echo "║                                                                      ║"
  echo "║  === Git Platforms ===                                               ║"
  echo "║  GitLab            http://localhost:30200                             ║"
  echo "║  Gitea             http://localhost:30201                             ║"
  echo "║  Gogs              http://localhost:30203                             ║"
  echo "║  Forgejo           http://localhost:30204                             ║"
  echo "║  OneDev            http://localhost:30205                             ║"
  echo "║                                                                      ║"
  echo "║  === CI/CD ===                                                       ║"
  echo "║  Drone CI          http://localhost:30210                             ║"
  echo "║  Woodpecker CI     http://localhost:30211                             ║"
  echo "║  Tekton Dashboard  http://localhost:30212                             ║"
  echo "║  Argo Workflows    http://localhost:30213                             ║"
  echo "║  GoCD              http://localhost:30214                             ║"
  echo "║  Concourse CI      http://localhost:30215                             ║"
  echo "║                                                                      ║"
  echo "║  === Artifact Repos ===                                              ║"
  echo "║  Artifactory       http://localhost:30220                             ║"
  echo "║  Docker Registry   http://localhost:30221                             ║"
  echo "║  Verdaccio         http://localhost:30222                             ║"
  echo "║  Zot               http://localhost:30224                             ║"
  echo "║                                                                      ║"
  echo "║  === Management ===                                                  ║"
  echo "║  Portainer         http://localhost:30230                             ║"
  echo "║  Rancher           http://localhost:30231                             ║"
  echo "║  K8s Dashboard     http://localhost:30232                             ║"
  echo "║  Helm Dashboard    http://localhost:30234                             ║"
  echo "║  AWX               http://localhost:30235                             ║"
  echo "║  Atlantis          http://localhost:30237                             ║"
  echo "║                                                                      ║"
  echo "║  === Monitoring ===                                                  ║"
  echo "║  Thanos            http://localhost:30240                             ║"
  echo "║  Mimir             http://localhost:30241                             ║"
  echo "║  VictoriaMetrics   http://localhost:30242                             ║"
  echo "║  Zabbix            http://localhost:30243                             ║"
  echo "║  Nagios            http://localhost:30244                             ║"
  echo "║  Icinga            http://localhost:30245                             ║"
  echo "║  Uptime Kuma       http://localhost:30246                             ║"
  echo "║  Netdata           http://localhost:30247                             ║"
  echo "║                                                                      ║"
  echo "║  === Logging ===                                                     ║"
  echo "║  Logstash          http://localhost:30250                             ║"
  echo "║  Loki              http://localhost:30252                             ║"
  echo "║  Graylog           http://localhost:30253                             ║"
  echo "║  OpenSearch Dash   http://localhost:30255                             ║"
  echo "║                                                                      ║"
  echo "║  === Tracing & APM ===                                               ║"
  echo "║  Zipkin            http://localhost:30260                             ║"
  echo "║  SigNoz            http://localhost:30261                             ║"
  echo "║  OTel Collector    http://localhost:30262                             ║"
  echo "║  Grafana Tempo     http://localhost:30263                             ║"
  echo "║  Sentry            http://localhost:30264                             ║"
  echo "║  Elastic APM       http://localhost:30265                             ║"
  echo "║                                                                      ║"
  echo "║  === Security ===                                                    ║"
  echo "║  Clair             http://localhost:30270                             ║"
  echo "║  Anchore           http://localhost:30271                             ║"
  echo "║  DefectDojo        http://localhost:30272                             ║"
  echo "║  OWASP ZAP         http://localhost:30273                             ║"
  echo "║                                                                      ║"
  echo "║  === Secrets ===                                                     ║"
  echo "║  Conjur            http://localhost:30280                             ║"
  echo "║  Infisical         http://localhost:30281                             ║"
  echo "║                                                                      ║"
  echo "║  === Networking ===                                                  ║"
  echo "║  Keycloak          http://localhost:30290                             ║"
  echo "║  Consul            http://localhost:30293                             ║"
  echo "║  Traefik           http://localhost:30294                             ║"
  echo "║  Nginx Ingress     http://localhost:30296                             ║"
  echo "║  Kong              http://localhost:30298                             ║"
  echo "║  APISIX            http://localhost:30310                             ║"
  echo "║  HAProxy           http://localhost:30312                             ║"
  echo "║  Envoy             http://localhost:30314                             ║"
  echo "║                                                                      ║"
  echo "║  === Databases & Messaging ===                                       ║"
  echo "║  PostgreSQL        localhost:30400                                    ║"
  echo "║  MySQL             localhost:30401                                    ║"
  echo "║  MariaDB           localhost:30402                                    ║"
  echo "║  Redis             localhost:30403                                    ║"
  echo "║  RabbitMQ Mgmt     http://localhost:30406                             ║"
  echo "║  Kafka (Strimzi)   localhost:30407                                    ║"
  echo "║  NATS              localhost:30408                                    ║"
  echo "║  etcd              localhost:30409                                    ║"
  echo "║                                                                      ║"
  echo "║  === Collaboration ===                                               ║"
  echo "║  Wiki.js           http://localhost:30500                             ║"
  echo "║  BookStack         http://localhost:30501                             ║"
  echo "║  Outline           http://localhost:30502                             ║"
  echo "║  Mattermost        http://localhost:30503                             ║"
  echo "║  Rocket.Chat       http://localhost:30504                             ║"
  echo "║  Backstage         http://localhost:30505                             ║"
  echo "║                                                                      ║"
  echo "║  Default credentials: admin / Admin@123                              ║"
  echo "╚══════════════════════════════════════════════════════════════════════╝"
}

###############################################################################
# MAIN
###############################################################################
main() {
  echo "╔══════════════════════════════════════════════════════════════════════╗"
  echo "║        DEPLOYING 80+ DEVOPS TOOLS TO KUBERNETES                     ║"
  echo "║        Target: Docker Desktop (single node)                         ║"
  echo "║        Mode: Minimal resources, NodePort exposure                   ║"
  echo "╚══════════════════════════════════════════════════════════════════════╝"
  echo ""

  phase_namespaces
  phase_helm_repos

  deploy_git_platforms
  deploy_cicd
  deploy_artifact_repos
  deploy_management
  deploy_iac_config
  deploy_monitoring
  deploy_logging
  deploy_tracing
  deploy_security
  deploy_secrets
  deploy_networking
  deploy_databases
  deploy_collaboration

  print_summary
}

# Allow running individual batches
case "${1:-all}" in
  namespaces)   phase_namespaces ;;
  repos)        phase_helm_repos ;;
  git)          deploy_git_platforms ;;
  cicd)         deploy_cicd ;;
  artifacts)    deploy_artifact_repos ;;
  management)   deploy_management ;;
  iac)          deploy_iac_config ;;
  monitoring)   deploy_monitoring ;;
  logging)      deploy_logging ;;
  tracing)      deploy_tracing ;;
  security)     deploy_security ;;
  secrets)      deploy_secrets ;;
  networking)   deploy_networking ;;
  databases)    deploy_databases ;;
  collaboration) deploy_collaboration ;;
  summary)      print_summary ;;
  all)          main ;;
  *)            echo "Usage: $0 {all|namespaces|repos|git|cicd|artifacts|management|iac|monitoring|logging|tracing|security|secrets|networking|databases|collaboration|summary}" ;;
esac
