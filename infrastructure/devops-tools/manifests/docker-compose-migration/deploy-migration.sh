#!/bin/bash
###############################################################################
# DEPLOY DOCKER COMPOSE → KUBERNETES MIGRATION
# Deploys services previously running in Docker Compose to Kubernetes
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
# PHASE 0: Increase maxPods on Docker Desktop
###############################################################################
increase_max_pods() {
  info "Checking maxPods capacity..."
  CURRENT_MAX=$(kubectl get node docker-desktop -o jsonpath='{.status.capacity.pods}' 2>/dev/null)

  if [ "$CURRENT_MAX" -lt 500 ] 2>/dev/null; then
    warn "maxPods is $CURRENT_MAX (need 500). Updating kubelet config..."

    # Update kubelet config
    MSYS_NO_PATHCONV=1 docker run --rm --privileged --pid=host alpine:3 \
      nsenter -t 1 -m -u -i -n -- sh -c '
        sed -i "/^maxPods/d" /etc/kubeadm/kubelet.yaml
        echo "maxPods: 500" >> /etc/kubeadm/kubelet.yaml
      '

    # Start kubelet with --max-pods=500 in a persistent container
    docker rm -f kubelet-starter 2>/dev/null || true
    MSYS_NO_PATHCONV=1 docker run -d --rm --privileged --pid=host --name kubelet-starter \
      alpine:3 nsenter -t 1 -m -u -i -n -- \
      /usr/bin/kubelet \
        --kubeconfig=/etc/kubernetes/kubelet.conf \
        --config=/etc/kubeadm/kubelet.yaml \
        --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf \
        --hostname-override=docker-desktop \
        --container-runtime-endpoint=unix:///var/run/cri-dockerd.sock \
        --max-pods=500

    sleep 20
    NEW_MAX=$(kubectl get node docker-desktop -o jsonpath='{.status.capacity.pods}' 2>/dev/null)
    log "maxPods updated: $CURRENT_MAX → $NEW_MAX"
  else
    log "maxPods already at $CURRENT_MAX"
  fi
}

###############################################################################
# PHASE 1: Create namespaces
###############################################################################
create_namespaces() {
  info "Creating namespaces..."
  kubectl apply -f "$SCRIPT_DIR/namespaces.yaml"
  log "Namespaces created"
}

###############################################################################
# PHASE 2: Deploy services
###############################################################################
deploy_services() {
  info "Deploying Docker Compose migration services..."

  for manifest in ollama chromadb splunk jira redmine loki redis cadvisor devops-tools-backend jaeger; do
    info "Deploying $manifest..."
    kubectl apply -f "$SCRIPT_DIR/${manifest}.yaml" 2>&1
    log "$manifest deployed"
  done
}

###############################################################################
# PHASE 3: Wait and verify
###############################################################################
verify_deployment() {
  info "Waiting 60s for pods to start..."
  sleep 60

  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║       DOCKER COMPOSE → K8s MIGRATION STATUS                ║"
  echo "╠══════════════════════════════════════════════════════════════╣"

  for ns in ollama chromadb splunk jira redmine loki redis cadvisor devops-tools jaeger; do
    PODS=$(kubectl get pods -n $ns --no-headers 2>/dev/null | awk '{printf "%s(%s) ", $1, $3}')
    printf "║  %-12s %s\n" "$ns:" "$PODS"
  done

  echo "╠══════════════════════════════════════════════════════════════╣"

  TOTAL=$(kubectl get pods --all-namespaces --no-headers 2>/dev/null | wc -l)
  RUNNING=$(kubectl get pods --all-namespaces --no-headers 2>/dev/null | grep "Running" | wc -l)
  MAX_PODS=$(kubectl get node docker-desktop -o jsonpath='{.status.capacity.pods}' 2>/dev/null)

  echo "║  Total Pods: $TOTAL / $MAX_PODS max                         "
  echo "║  Running:    $RUNNING                                        "
  echo "╚══════════════════════════════════════════════════════════════╝"
}

###############################################################################
# MAIN
###############################################################################
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Docker Compose → Kubernetes Migration Script               ║"
echo "╚══════════════════════════════════════════════════════════════╝"

increase_max_pods
create_namespaces
deploy_services
verify_deployment

echo ""
log "Migration complete!"
