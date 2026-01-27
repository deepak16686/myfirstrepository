# ============================================================================
# QUICK REFERENCE CARD - Common Commands
# ============================================================================

# ============================================================================
# 🚀 DEPLOYMENT COMMANDS
# ============================================================================

# Full platform rebuild
.\rebuild-platform.ps1

# Rebuild without AI models
.\rebuild-platform.ps1 -SkipModels

# Rebuild without monitoring
.\rebuild-platform.ps1 -SkipMonitoring

# Docker Compose deployment
docker-compose up -d

# Docker Compose with rebuild
docker-compose up -d --build --force-recreate

# ============================================================================
# 🔍 VALIDATION & HEALTH CHECKS
# ============================================================================

# Quick health check
.\validate-platform.ps1

# Detailed health check with connectivity tests
.\validate-platform.ps1 -Detailed

# Continuous monitoring (30 second intervals)
.\validate-platform.ps1 -Continuous -Interval 30

# Check all container status
docker ps -a

# Check specific service
docker ps --filter "name=ollama"

# ============================================================================
# 📊 MONITORING COMMANDS
# ============================================================================

# View container logs (live)
docker logs -f <container-name>

# View last 100 lines
docker logs --tail 100 <container-name>

# View logs with timestamps
docker logs -t <container-name>

# Resource usage (real-time)
docker stats

# Resource usage (snapshot)
docker stats --no-stream

# Container inspection
docker inspect <container-name>

# ============================================================================
# 🤖 OLLAMA AI MODEL COMMANDS
# ============================================================================

# List installed models
docker exec ollama ollama list

# Pull new model
docker exec ollama ollama pull <model-name>

# Examples:
docker exec ollama ollama pull deepseek-coder:6.7b-instruct-q4_K_M
docker exec ollama ollama pull qwen2.5-coder:7b-instruct-q4_K_M
docker exec ollama ollama pull codellama:13b-instruct-q4_K_M

# Run model interactively
docker exec -it ollama ollama run deepseek-coder:33b-instruct-q4_K_M

# Test model with prompt
docker exec ollama ollama run deepseek-coder:33b-instruct-q4_K_M "Write a Python function to calculate factorial"

# Remove model
docker exec ollama ollama rm <model-name>

# Show model info
docker exec ollama ollama show deepseek-coder:33b-instruct-q4_K_M

# ============================================================================
# 💾 DATABASE COMMANDS
# ============================================================================

# PostgreSQL
# -----------
# Connect to PostgreSQL
docker exec -it postgres psql -U modernization -d legacy_modernization

# Run SQL query
docker exec postgres psql -U modernization -d legacy_modernization -c "SELECT version();"

# Backup database
docker exec postgres pg_dump -U modernization legacy_modernization > backup.sql

# Restore database
cat backup.sql | docker exec -i postgres psql -U modernization -d legacy_modernization

# Redis
# -----
# Connect to Redis
docker exec -it redis redis-cli

# Get all keys
docker exec redis redis-cli KEYS '*'

# Get specific key
docker exec redis redis-cli GET <key>

# Flush all data (CAUTION!)
docker exec redis redis-cli FLUSHALL

# ============================================================================
# 🗄️ STORAGE COMMANDS
# ============================================================================

# MinIO
# -----
# Access MinIO console: http://localhost:9001
# Credentials: minioadmin / minioadmin123

# ChromaDB
# --------
# Access ChromaDB API: http://localhost:8000
# Check health
curl http://localhost:8000/api/v1/heartbeat

# ============================================================================
# 🔄 CONTAINER MANAGEMENT
# ============================================================================

# Start all containers
docker start $(docker ps -aq)

# Stop all containers
docker stop $(docker ps -aq)

# Restart specific container
docker restart <container-name>

# Remove container
docker rm <container-name>

# Remove container (force)
docker rm -f <container-name>

# Recreate container
docker rm -f <container-name>
.\rebuild-platform.ps1

# ============================================================================
# 📦 VOLUME MANAGEMENT
# ============================================================================

# List volumes
docker volume ls

# Inspect volume
docker volume inspect <volume-name>

# Remove unused volumes
docker volume prune -f

# Remove specific volume
docker volume rm <volume-name>

# Backup volume
docker run --rm -v <volume-name>:/data -v ${PWD}:/backup alpine tar czf /backup/volume-backup.tar.gz -C /data .

# Restore volume
docker run --rm -v <volume-name>:/data -v ${PWD}:/backup alpine tar xzf /backup/volume-backup.tar.gz -C /data

# ============================================================================
# 🌐 NETWORK COMMANDS
# ============================================================================

# List networks
docker network ls

# Inspect network
docker network inspect modernization-network

# Connect container to network
docker network connect <network-name> <container-name>

# Disconnect container from network
docker network disconnect <network-name> <container-name>

# Remove network
docker network rm <network-name>

# ============================================================================
# 🧹 CLEANUP COMMANDS
# ============================================================================

# Stop all containers
docker stop $(docker ps -aq)

# Remove all containers
docker rm $(docker ps -aq)

# Remove unused images
docker image prune -a -f

# Remove unused volumes
docker volume prune -f

# Remove unused networks
docker network prune -f

# Complete cleanup (CAUTION: removes everything)
docker system prune -a -f --volumes

# ============================================================================
# 🔬 TROUBLESHOOTING COMMANDS
# ============================================================================

# Check Docker Desktop status
docker info

# Check WSL2 integration
wsl -l -v

# Check GPU availability
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi

# Check port usage
netstat -ano | findstr :<port>

# Test connectivity to service
Test-NetConnection -ComputerName localhost -Port <port>

# Check container IP address
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <container-name>

# Execute command in container
docker exec <container-name> <command>

# Get shell in container
docker exec -it <container-name> /bin/sh
docker exec -it <container-name> /bin/bash

# ============================================================================
# 📈 PROMETHEUS QUERIES
# ============================================================================

# Access Prometheus: http://localhost:9090

# Example queries:
# -----------------
# Ollama request rate
rate(ollama_request_total[5m])

# Container CPU usage
rate(container_cpu_usage_seconds_total[5m]) * 100

# Container memory usage (GB)
container_memory_usage_bytes / 1024 / 1024 / 1024

# GPU utilization
nvidia_gpu_utilization

# Disk usage
(node_filesystem_size_bytes - node_filesystem_free_bytes) / node_filesystem_size_bytes * 100

# ============================================================================
# 📊 GRAFANA COMMANDS
# ============================================================================

# Access Grafana: http://localhost:3000
# Default credentials: admin / admin123

# Add Prometheus data source:
# Configuration > Data Sources > Add data source > Prometheus
# URL: http://prometheus:9090

# Add Loki data source:
# Configuration > Data Sources > Add data source > Loki
# URL: http://loki:3100

# ============================================================================
# 🔐 SECURITY COMMANDS
# ============================================================================

# View container environment variables
docker exec <container-name> env

# Check file permissions in container
docker exec <container-name> ls -la /path

# Update password (example: Grafana)
docker exec grafana grafana-cli admin reset-admin-password <new-password>

# ============================================================================
# 📝 LOGGING COMMANDS
# ============================================================================

# View logs from all containers
docker-compose logs -f

# View logs from specific service
docker-compose logs -f <service-name>

# Export logs to file
docker logs <container-name> > container-logs.txt 2>&1

# Follow logs with grep filter
docker logs -f <container-name> | grep ERROR

# ============================================================================
# 🆘 EMERGENCY COMMANDS
# ============================================================================

# Complete platform restart
docker restart $(docker ps -aq)

# Force stop all containers
docker kill $(docker ps -aq)

# Rebuild everything from scratch
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
docker volume rm $(docker volume ls -q)
docker network rm modernization-network monitoring-network
.\rebuild-platform.ps1

# Restart Docker Desktop
# Stop-Service docker
# Start-Service docker
# Or restart via Docker Desktop UI

# ============================================================================
# 📞 SUPPORT COMMANDS
# ============================================================================

# Generate system report
docker info > system-report.txt
docker ps -a >> system-report.txt
docker stats --no-stream >> system-report.txt
docker volume ls >> system-report.txt
docker network ls >> system-report.txt

# Export configuration
docker-compose config > current-config.yml

# Check version information
docker version
docker-compose version

# ============================================================================
# END OF QUICK REFERENCE
# ============================================================================
