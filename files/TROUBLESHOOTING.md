# 🔧 Troubleshooting Guide

## Common Issues and Solutions

---

## 🚨 Docker Desktop Issues

### Issue: Docker Desktop Won't Start
**Symptoms:**
- Docker Desktop stuck at "Starting..."
- Error: "Docker Desktop is not running"

**Solutions:**
1. **Restart Docker Desktop**:
   ```powershell
   # Via PowerShell (as Administrator)
   Stop-Service docker
   Start-Service docker
   
   # Or restart via Docker Desktop UI
   ```

2. **Check WSL2 Status**:
   ```powershell
   wsl -l -v
   # Ensure WSL2 is running
   wsl --update
   ```

3. **Reset Docker Desktop**:
   - Open Docker Desktop
   - Settings > Trouble shoot > Reset to factory defaults
   - **WARNING**: This will delete all containers, images, and volumes

4. **Check Windows Services**:
   - Open Services (services.msc)
   - Ensure "Docker Desktop Service" is running
   - Start type should be "Automatic"

---

## 🔌 Port Already in Use

### Issue: Port Conflict When Starting Containers
**Symptoms:**
- Error: "Bind for 0.0.0.0:5432 failed: port is already allocated"
- Container fails to start

**Solutions:**
1. **Identify Process Using Port**:
   ```powershell
   # Find process ID
   netstat -ano | findstr :<port>
   
   # Example for PostgreSQL (port 5432)
   netstat -ano | findstr :5432
   ```

2. **Kill Process**:
   ```powershell
   # Kill process by PID
   Stop-Process -Id <PID> -Force
   
   # Example
   Stop-Process -Id 12345 -Force
   ```

3. **Change Port in Configuration**:
   - Edit docker-compose.yml
   - Change port mapping (e.g., "5433:5432" instead of "5432:5432")

---

## 🐳 Container Issues

### Issue: Container Keeps Restarting
**Symptoms:**
- Container status shows "Restarting"
- Container exits immediately after start

**Solutions:**
1. **Check Container Logs**:
   ```powershell
   docker logs <container-name>
   ```

2. **Inspect Container**:
   ```powershell
   docker inspect <container-name>
   ```

3. **Common Causes**:
   - **Configuration Error**: Check environment variables
   - **Port Conflict**: Ensure port is available
   - **Volume Mount Issue**: Verify volume paths exist
   - **Insufficient Resources**: Check RAM/CPU allocation

4. **Fix and Restart**:
   ```powershell
   # Remove problematic container
   docker rm -f <container-name>
   
   # Rebuild
   .\rebuild-platform.ps1
   ```

### Issue: Container is Unhealthy
**Symptoms:**
- Docker ps shows "unhealthy" status
- Health check failing

**Solutions:**
1. **Check Health Check Logs**:
   ```powershell
   docker inspect --format='{{json .State.Health}}' <container-name>
   ```

2. **Manual Health Check**:
   ```powershell
   # Example for Ollama
   curl http://localhost:11434/
   
   # Example for ChromaDB
   curl http://localhost:8000/api/v1/heartbeat
   ```

3. **Restart Container**:
   ```powershell
   docker restart <container-name>
   ```

---

## 🤖 Ollama Issues

### Issue: GPU Not Detected by Ollama
**Symptoms:**
- Ollama running on CPU only
- Slow model inference
- nvidia-smi not working in container

**Solutions:**
1. **Verify Docker GPU Support**:
   ```powershell
   docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
   ```

2. **Check Ollama Container GPU Access**:
   ```powershell
   docker exec ollama nvidia-smi
   ```

3. **Verify Docker Desktop GPU Settings**:
   - Docker Desktop > Settings > Resources
   - Ensure "Use GPU" is enabled
   - Restart Docker Desktop

4. **Recreate Ollama Container**:
   ```powershell
   docker rm -f ollama
   .\rebuild-platform.ps1
   ```

### Issue: Model Download Fails
**Symptoms:**
- Error: "pull model manifest"
- Download interrupted
- Insufficient disk space

**Solutions:**
1. **Check Disk Space**:
   ```powershell
   # Check available space
   Get-PSDrive C
   ```

2. **Retry Download**:
   ```powershell
   docker exec ollama ollama pull <model-name>
   ```

3. **Download Smaller Model**:
   ```powershell
   # Use 7B instead of 33B
   docker exec ollama ollama pull deepseek-coder:6.7b-instruct-q4_K_M
   ```

4. **Clear Failed Downloads**:
   ```powershell
   docker exec ollama ollama rm <model-name>
   ```

### Issue: Model Inference is Slow
**Symptoms:**
- Long response times
- High CPU usage
- Out of memory errors

**Solutions:**
1. **Check GPU Utilization**:
   ```powershell
   nvidia-smi
   ```

2. **Use Smaller Model or Lower Quantization**:
   - Q4_K_M (medium quality, faster)
   - Q2_K (lower quality, fastest)

3. **Reduce Concurrent Requests**:
   - Limit parallel inference calls
   - Implement request queuing

4. **Increase GPU Memory**:
   - Close other GPU-intensive applications
   - Use model with smaller parameters

---

## 💾 Database Issues

### Issue: PostgreSQL Connection Refused
**Symptoms:**
- Error: "could not connect to server"
- Connection timeout

**Solutions:**
1. **Verify Container is Running**:
   ```powershell
   docker ps --filter "name=postgres"
   ```

2. **Check Logs**:
   ```powershell
   docker logs postgres
   ```

3. **Test Connection**:
   ```powershell
   docker exec postgres psql -U modernization -d legacy_modernization -c "SELECT version();"
   ```

4. **Verify Port is Open**:
   ```powershell
   Test-NetConnection -ComputerName localhost -Port 5432
   ```

### Issue: Redis Connection Issues
**Symptoms:**
- Error: "Could not connect to Redis"
- Commands timing out

**Solutions:**
1. **Test Redis**:
   ```powershell
   docker exec redis redis-cli PING
   # Should return PONG
   ```

2. **Check Redis Logs**:
   ```powershell
   docker logs redis
   ```

3. **Restart Redis**:
   ```powershell
   docker restart redis
   ```

---

## 📊 Monitoring Issues

### Issue: Prometheus Targets Down
**Symptoms:**
- Targets showing as "DOWN" in Prometheus UI
- No metrics being collected

**Solutions:**
1. **Check Target Accessibility**:
   ```powershell
   # Test Ollama metrics
   curl http://localhost:11434/metrics
   ```

2. **Verify Network Connectivity**:
   ```powershell
   docker exec prometheus wget -O- http://ollama:11434/metrics
   ```

3. **Check Prometheus Configuration**:
   ```powershell
   docker exec prometheus cat /etc/prometheus/prometheus.yml
   ```

4. **Reload Prometheus Configuration**:
   ```powershell
   # Via API
   Invoke-WebRequest -Method POST http://localhost:9090/-/reload
   
   # Or restart
   docker restart prometheus
   ```

### Issue: Grafana Dashboard Shows No Data
**Symptoms:**
- Empty graphs
- "No data" message

**Solutions:**
1. **Verify Data Source Connection**:
   - Grafana > Configuration > Data Sources
   - Test connection to Prometheus/Loki

2. **Check Query Syntax**:
   - Verify PromQL/LogQL queries
   - Test queries in Prometheus UI first

3. **Verify Time Range**:
   - Check dashboard time picker
   - Ensure data exists for selected time range

4. **Check Prometheus Scrape Status**:
   - Visit http://localhost:9090/targets
   - Verify all targets are UP

---

## 🗄️ Storage Issues

### Issue: Volume Mount Fails
**Symptoms:**
- Container can't access volume
- Permission denied errors
- Data not persisting

**Solutions:**
1. **Check Volume Exists**:
   ```powershell
   docker volume ls | Select-String <volume-name>
   ```

2. **Recreate Volume**:
   ```powershell
   docker volume rm <volume-name>
   docker volume create <volume-name>
   ```

3. **Check Volume Permissions**:
   ```powershell
   docker exec <container-name> ls -la /path/to/mount
   ```

### Issue: Disk Space Full
**Symptoms:**
- "No space left on device"
- Containers failing to start
- Unable to download models

**Solutions:**
1. **Check Disk Usage**:
   ```powershell
   docker system df
   ```

2. **Clean Up Docker**:
   ```powershell
   # Remove unused images
   docker image prune -a -f
   
   # Remove unused volumes (CAUTION)
   docker volume prune -f
   
   # Complete cleanup
   docker system prune -a -f --volumes
   ```

3. **Move Docker Data Location**:
   - Docker Desktop > Settings > Resources > Advanced
   - Change "Disk image location"

---

## 🌐 Network Issues

### Issue: Containers Can't Communicate
**Symptoms:**
- Services can't reach each other
- Network timeout errors

**Solutions:**
1. **Verify Network Exists**:
   ```powershell
   docker network ls | Select-String modernization
   ```

2. **Check Container Network Connections**:
   ```powershell
   docker inspect <container-name> --format='{{json .NetworkSettings.Networks}}'
   ```

3. **Reconnect Container to Network**:
   ```powershell
   docker network connect modernization-network <container-name>
   ```

4. **Recreate Network**:
   ```powershell
   docker network rm modernization-network
   docker network create modernization-network
   ```

---

## 🔐 Authentication Issues

### Issue: Can't Connect to MinIO Console
**Symptoms:**
- Login fails
- "Access Denied" error

**Solutions:**
1. **Verify Credentials**:
   - Username: `minioadmin`
   - Password: `minioadmin123`

2. **Check Environment Variables**:
   ```powershell
   docker exec minio env | Select-String MINIO_ROOT
   ```

3. **Reset MinIO**:
   ```powershell
   docker rm -f minio
   docker volume rm minio-data
   .\rebuild-platform.ps1
   ```

### Issue: Grafana Login Issues
**Symptoms:**
- Default credentials not working
- Locked out of Grafana

**Solutions:**
1. **Reset Admin Password**:
   ```powershell
   docker exec grafana grafana-cli admin reset-admin-password newpassword123
   ```

2. **Check Environment Variables**:
   ```powershell
   docker exec grafana env | Select-String GF_SECURITY
   ```

---

## 🔄 Performance Issues

### Issue: High CPU Usage
**Symptoms:**
- System running slow
- Containers using 100% CPU

**Solutions:**
1. **Identify Resource Hog**:
   ```powershell
   docker stats --no-stream
   ```

2. **Limit Container Resources**:
   ```yaml
   # In docker-compose.yml
   services:
     ollama:
       deploy:
         resources:
           limits:
             cpus: '8'
             memory: 32G
   ```

3. **Reduce Concurrent Operations**:
   - Limit parallel model inference
   - Reduce scrape frequency in Prometheus

### Issue: High Memory Usage
**Symptoms:**
- System running out of RAM
- OOM (Out of Memory) errors

**Solutions:**
1. **Check Memory Usage**:
   ```powershell
   docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}"
   ```

2. **Increase Docker Memory Allocation**:
   - Docker Desktop > Settings > Resources
   - Increase Memory slider

3. **Use Smaller Models**:
   - Switch to 7B models instead of 33B
   - Use higher quantization (Q2_K instead of Q4_K_M)

---

## 📝 Configuration Issues

### Issue: Changes Not Taking Effect
**Symptoms:**
- Configuration updates ignored
- Old settings persist

**Solutions:**
1. **Reload Configuration**:
   ```powershell
   # For Prometheus
   Invoke-WebRequest -Method POST http://localhost:9090/-/reload
   ```

2. **Recreate Containers**:
   ```powershell
   docker-compose down
   docker-compose up -d --force-recreate
   ```

3. **Clear Docker Cache**:
   ```powershell
   docker-compose build --no-cache
   docker-compose up -d
   ```

---

## 🆘 Emergency Recovery

### Complete Platform Reset
If nothing else works, perform a complete reset:

```powershell
# 1. Stop everything
docker stop $(docker ps -aq)

# 2. Remove all containers
docker rm $(docker ps -aq)

# 3. Remove all volumes (DATA LOSS!)
docker volume prune -f

# 4. Remove all networks
docker network prune -f

# 5. Remove all images (optional)
docker image prune -a -f

# 6. Restart Docker Desktop
# - Docker Desktop > Restart

# 7. Rebuild platform
.\rebuild-platform.ps1
```

---

## 📞 Getting Help

### Collect Diagnostic Information
```powershell
# Generate system report
docker info > system-report.txt
docker ps -a >> system-report.txt
docker stats --no-stream >> system-report.txt
docker volume ls >> system-report.txt
docker network ls >> system-report.txt
.\validate-platform.ps1 -Detailed >> system-report.txt
```

### Check Service Logs
```powershell
# Export logs from all containers
docker logs postgres > logs/postgres.log 2>&1
docker logs redis > logs/redis.log 2>&1
docker logs ollama > logs/ollama.log 2>&1
docker logs prometheus > logs/prometheus.log 2>&1
```

---

## 🔍 Prevention Tips

1. **Regular Health Checks**:
   ```powershell
   .\validate-platform.ps1 -Continuous -Interval 300
   ```

2. **Monitor Resource Usage**:
   - Keep an eye on CPU/RAM/Disk usage
   - Set up alerts in Prometheus

3. **Regular Backups**:
   - Backup volumes regularly
   - Export important configurations

4. **Keep Docker Updated**:
   - Update Docker Desktop regularly
   - Update container images periodically

5. **Documentation**:
   - Document custom configurations
   - Keep track of changes

---

**Last Updated**: 2026-01-16
