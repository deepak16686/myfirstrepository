# Kubernetes Production Environment

## Overview
Your entire Docker production environment has been migrated to Kubernetes cluster in the `prod-environment` namespace.

## Deployed Services

### Infrastructure
- **Postgres** - Main database (ClusterIP internal)
- **Redis** - Cache/queue (ClusterIP internal)
- **MinIO** - S3-compatible storage
  - API: http://localhost:30900
  - Console: http://localhost:30901
  - Default credentials: admin / `${MINIO_ROOT_PASSWORD}` — set via k8s Secret `minio-secret` (see `manifests/_secrets-template.yaml`)

### AI & ML
- **ChromaDB** - Vector database
  - URL: http://localhost:30800
- **Ollama** - Local LLM server
  - URL: http://localhost:31434

### DevOps Tools
- **Jenkins** - CI/CD automation
  - URL: http://localhost:30808
  - JNLP: port 30500
- **GitLab** - Full DevOps platform
  - URL: http://localhost:30929
  - SSH: port 30224
- **SonarQube** - Code quality
  - URL: http://localhost:30902
  - Default: admin / admin
- **Nexus** - Artifact repository
  - URL: http://localhost:30810
  - Docker registry: port 30501

### Monitoring
- **Prometheus** - Metrics collection
  - URL: http://localhost:30909
- **Grafana** - Visualization
  - URL: http://localhost:30300
  - Default: admin / `${GRAFANA_ADMIN_PASSWORD}` — set via k8s Secret `grafana-secret` (see `manifests/_secrets-template.yaml`)

## Kubernetes Commands

### Check status
```bash
kubectl get all -n prod-environment
kubectl get pods -n prod-environment
kubectl get svc -n prod-environment
```

### View logs
```bash
kubectl logs -f deployment/jenkins -n prod-environment
kubectl logs -f deployment/gitlab -n prod-environment
```

### Scale services
```bash
kubectl scale deployment/jenkins --replicas=2 -n prod-environment
```

### Delete environment
```bash
kubectl delete namespace prod-environment
```

## Storage
All services use PersistentVolumeClaims (PVCs) for data persistence:
- postgres-pvc: 10Gi
- redis-pvc: 5Gi
- minio-pvc: 20Gi
- chromadb-pvc: 10Gi
- ollama-pvc: 50Gi
- jenkins-pvc: 20Gi
- sonarqube-*-pvc: 20Gi total
- nexus-pvc: 50Gi
- gitlab-*-pvc: 40Gi total
- prometheus-pvc: 10Gi
- grafana-pvc: 5Gi

**Total storage allocated: ~250Gi**

## Resource Allocation

### Memory Requests/Limits
- Postgres: 512Mi / 2Gi
- Redis: 256Mi / 1Gi
- MinIO: 512Mi / 2Gi
- ChromaDB: 512Mi / 2Gi
- Ollama: 2Gi / 8Gi
- Jenkins: 1Gi / 4Gi
- SonarQube: 2Gi / 4Gi (+ 512Mi/1Gi DB)
- Nexus: 2Gi / 4Gi
- GitLab: 4Gi / 8Gi
- Prometheus: 512Mi / 2Gi
- Grafana: 256Mi / 1Gi

**Total memory requests: ~13Gi**
**Total memory limits: ~41Gi**

## Network Access

All services are exposed via **NodePort** for easy access from your host machine at `localhost:<port>`.

Internal services (Postgres, Redis, SonarQube DB) use **ClusterIP** and are only accessible within the cluster.

## Next Steps

1. **Wait for pods to be ready** (~5-10 minutes for GitLab/Nexus)
   ```bash
   kubectl get pods -n prod-environment -w
   ```

2. **Access Jenkins** and retrieve initial admin password:
   ```bash
   kubectl exec -it deployment/jenkins -n prod-environment -- cat /var/jenkins_home/secrets/initialAdminPassword
   ```

3. **Access GitLab** root password:
   ```bash
   kubectl exec -it deployment/gitlab -n prod-environment -- grep 'Password:' /etc/gitlab/initial_root_password
   ```

4. **Configure Prometheus** data sources in Grafana:
   - Add data source: http://prometheus:9090

## Advantages Over Docker Compose

✅ **Auto-healing** - Pods restart automatically on failure
✅ **Resource limits** - Prevents any single service from consuming all resources
✅ **Declarative config** - GitOps-ready YAML manifests
✅ **Scalability** - Easy to scale services with replicas
✅ **Health checks** - Liveness and readiness probes
✅ **Service discovery** - DNS-based service names
✅ **Rolling updates** - Zero-downtime deployments

## Troubleshooting

### Pod stuck in ContainerCreating
```bash
kubectl describe pod <pod-name> -n prod-environment
```

### Check events
```bash
kubectl get events -n prod-environment --sort-by='.lastTimestamp'
```

### Persistent volume issues
```bash
kubectl get pvc -n prod-environment
kubectl describe pvc <pvc-name> -n prod-environment
```

### Resource constraints
```bash
kubectl top pods -n prod-environment
kubectl top nodes
```
