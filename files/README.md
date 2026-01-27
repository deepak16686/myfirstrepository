# Legacy Application Modernization Platform - Setup Guide

## 🚀 Quick Start

After reinstalling Docker Desktop, you have **two deployment options**:

### Option 1: PowerShell Script (Recommended)
```powershell
# Full deployment with all services and AI models
.\rebuild-platform.ps1

# Skip AI model downloads (if already downloaded)
.\rebuild-platform.ps1 -SkipModels

# Skip monitoring stack
.\rebuild-platform.ps1 -SkipMonitoring

# Validation only
.\rebuild-platform.ps1 -Validate
```

### Option 2: Docker Compose
```powershell
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Stop and remove volumes (CAUTION: data loss)
docker-compose down -v
```

---

## 📋 Prerequisites

- **Docker Desktop** installed and running
- **Windows 11 Pro** with WSL2 enabled
- **GPU Support** configured (for Ollama)
- **PowerShell 5.1+** or PowerShell Core 7+
- **Minimum 32GB RAM** (64GB+ recommended)
- **500GB+ available disk space** (for models and data)

---

## 🏗️ Platform Architecture

### Infrastructure Services
| Service | Port | Purpose | Credentials |
|---------|------|---------|-------------|
| PostgreSQL | 5432 | Relational database | `modernization` / `modernization123` |
| Redis | 6379 | Caching layer | No authentication |
| MinIO | 9000, 9001 | Object storage | `minioadmin` / `minioadmin123` |
| ChromaDB | 8000 | Vector database | No authentication |
| Ollama | 11434 | AI model server | No authentication |

### Monitoring Stack
| Service | Port | Purpose | Credentials |
|---------|------|---------|-------------|
| Prometheus | 9090 | Metrics collection | No authentication |
| Grafana | 3000 | Visualization | `admin` / `admin123` |
| Loki | 3100 | Log aggregation | No authentication |
| Jaeger | 16686 | Distributed tracing | No authentication |

### AI Models (Ollama)
- **DeepSeek Coder 33B** (`deepseek-coder:33b-instruct-q4_K_M`) - ~18GB
- **Qwen2.5-Coder 32B** (`qwen2.5-coder:32b-instruct-q4_K_M`) - ~18GB

---

## 🔍 Validation & Health Checks

### Quick Health Check
```powershell
.\validate-platform.ps1
```

### Detailed Health Check
```powershell
.\validate-platform.ps1 -Detailed
```

### Continuous Monitoring
```powershell
# Check every 30 seconds
.\validate-platform.ps1 -Continuous -Interval 30
```

---

## 🛠️ Manual AI Model Management

### Pull Additional Models
```powershell
# List available models
docker exec ollama ollama list

# Pull a specific model
docker exec ollama ollama pull deepseek-coder:6.7b-instruct-q4_K_M

# Pull larger models (70B+)
docker exec ollama ollama pull qwen2.5-coder:72b-instruct-q4_K_M
```

### Test Model Inference
```powershell
# Test DeepSeek Coder
docker exec ollama ollama run deepseek-coder:33b-instruct-q4_K_M "Write a Python function to reverse a string"

# Test Qwen2.5-Coder
docker exec ollama ollama run qwen2.5-coder:32b-instruct-q4_K_M "Explain what a microservice is"
```

---

## 📊 Accessing Services

### Web Interfaces
- **MinIO Console**: http://localhost:9001
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
- **Jaeger**: http://localhost:16686

### API Endpoints
- **Ollama API**: http://localhost:11434
- **ChromaDB API**: http://localhost:8000
- **Loki API**: http://localhost:3100

### Database Connections

**PostgreSQL**:
```powershell
# Via Docker
docker exec -it postgres psql -U modernization -d legacy_modernization

# Connection string
postgresql://modernization:modernization123@localhost:5432/legacy_modernization
```

**Redis**:
```powershell
# Via Docker
docker exec -it redis redis-cli

# Connection string
redis://localhost:6379
```

---

## 🔧 Troubleshooting

### Check Container Status
```powershell
# View all containers
docker ps -a

# View specific container logs
docker logs -f <container-name>

# Check container resource usage
docker stats
```

### Common Issues

#### 1. Port Already in Use
```powershell
# Find process using port
netstat -ano | findstr :<port>

# Kill process
Stop-Process -Id <PID> -Force
```

#### 2. Container Won't Start
```powershell
# Check logs
docker logs <container-name>

# Restart container
docker restart <container-name>

# Remove and recreate
docker rm -f <container-name>
.\rebuild-platform.ps1
```

#### 3. Ollama GPU Not Detected
```powershell
# Verify GPU support in Docker
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi

# Check Ollama container GPU access
docker exec ollama nvidia-smi
```

#### 4. Out of Memory
```powershell
# Check memory usage
docker stats --no-stream

# Restart Docker Desktop
# Or reduce number of running models
```

---

## 🗑️ Cleanup & Reset

### Stop All Containers
```powershell
docker stop $(docker ps -aq)
```

### Remove All Containers
```powershell
docker rm $(docker ps -aq)
```

### Remove Volumes (⚠️ DATA LOSS)
```powershell
docker volume rm postgres-data redis-data minio-data chromadb-data ollama-data prometheus-data grafana-data loki-data
```

### Complete Reset
```powershell
# Stop and remove everything
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
docker volume prune -f
docker network prune -f

# Rebuild from scratch
.\rebuild-platform.ps1
```

---

## 📈 Monitoring & Metrics

### Prometheus Targets
Visit http://localhost:9090/targets to verify all scrape targets are UP.

### Grafana Dashboards
1. Log in to Grafana: http://localhost:3000 (admin / admin123)
2. Add Prometheus data source:
   - URL: `http://prometheus:9090`
3. Add Loki data source:
   - URL: `http://loki:3100`
4. Import dashboards for:
   - Ollama metrics
   - System metrics
   - Container metrics
   - GPU metrics

### Common Queries

**Prometheus**:
```promql
# Ollama request rate
rate(ollama_request_total[5m])

# Container CPU usage
rate(container_cpu_usage_seconds_total[5m])

# Memory usage
container_memory_usage_bytes / 1024 / 1024 / 1024
```

---

## 🔐 Security Considerations

### Default Credentials (Change in Production!)
- PostgreSQL: `modernization` / `modernization123`
- MinIO: `minioadmin` / `minioadmin123`
- Grafana: `admin` / `admin123`

### Network Isolation
- Services are isolated in Docker networks
- Only necessary ports are exposed to host
- Consider using reverse proxy (Traefik/Nginx) for production

### Data Persistence
- All data stored in Docker volumes
- Volumes persist after container removal
- Regular backup recommended for production

---

## 📝 Next Steps

1. **Test Core Workflows**:
   - Legacy code analysis
   - Architecture diagram generation
   - Jira ticket generation

2. **Configure Monitoring**:
   - Set up Grafana dashboards
   - Configure alert rules in Prometheus
   - Set up log forwarding to Loki

3. **Deploy Application Layer**:
   - REST API services
   - Web UI components
   - Integration services

4. **Scale to Cloud**:
   - Plan Kubernetes migration
   - Set up CI/CD pipelines
   - Configure auto-scaling

---

## 🆘 Support & Resources

### Platform Status
```powershell
.\validate-platform.ps1 -Detailed
```

### Docker Desktop Settings
- **WSL Integration**: Enabled
- **GPU Support**: Enabled
- **Memory**: 64GB+ allocated
- **Disk**: 500GB+ available

### Useful Links
- [Docker Documentation](https://docs.docker.com/)
- [Ollama Documentation](https://github.com/ollama/ollama)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)

---

## 📄 License & Attribution

Legacy Application Modernization Platform
Copyright © 2026 - Cloud, AI & DevOps Architecture Team

---

**Last Updated**: 2026-01-16
**Platform Version**: 1.0.0
**Deployment Environment**: Windows 11 Pro + Docker Desktop + WSL2
