# INSTALLATION INSTRUCTIONS

## 📥 Download Complete!

You have downloaded the **Legacy Application Modernization Platform** deployment package.

---

## 📦 Package Contents

This ZIP file contains:
- `rebuild-platform.ps1` - Main deployment script
- `validate-platform.ps1` - Health check and validation script
- `docker-compose.yml` - Docker Compose configuration
- `prometheus.yml` - Prometheus monitoring configuration
- `loki-config.yml` - Loki log aggregation configuration
- `promtail-config.yml` - Promtail log collector configuration
- `README.md` - Complete documentation
- `QUICK-REFERENCE.md` - Command reference guide
- `TROUBLESHOOTING.md` - Troubleshooting guide

---

## 🚀 Quick Start (3 Steps)

### Step 1: Extract Files
Extract the ZIP file to a folder on your desktop, for example:
```
C:\LegacyModernizationPlatform\
```

### Step 2: Open PowerShell
Right-click on the folder and select **"Open in Terminal"** or:
```powershell
# Navigate to the folder
cd C:\LegacyModernizationPlatform
```

### Step 3: Run Deployment
```powershell
# Deploy everything
.\rebuild-platform.ps1
```

That's it! The script will:
✅ Deploy all infrastructure services
✅ Deploy monitoring stack
✅ Download AI models
✅ Validate everything

---

## ⏱️ Expected Deployment Time

- **Infrastructure Services**: 2-3 minutes
- **Monitoring Stack**: 1-2 minutes
- **AI Models Download**: 15-30 minutes (one-time)
- **Total**: ~20-35 minutes for first run

Subsequent runs (with models already downloaded):
```powershell
.\rebuild-platform.ps1 -SkipModels
```
Takes only: ~3-5 minutes

---

## 🔧 Prerequisites Check

Before running, ensure:
- ✅ Docker Desktop is installed and running
- ✅ WSL2 is enabled
- ✅ GPU support is configured (for Ollama)
- ✅ At least 32GB RAM available
- ✅ At least 100GB free disk space
- ✅ PowerShell 5.1+ or PowerShell Core 7+

Check Docker:
```powershell
docker --version
docker info
```

---

## 📝 Script Parameters

```powershell
# Full deployment (first time)
.\rebuild-platform.ps1

# Skip AI model downloads (if already downloaded)
.\rebuild-platform.ps1 -SkipModels

# Skip monitoring stack (minimal deployment)
.\rebuild-platform.ps1 -SkipMonitoring

# Validation only (check if everything is running)
.\rebuild-platform.ps1 -Validate
```

---

## 🔍 Post-Deployment Validation

After deployment completes, validate everything:
```powershell
.\validate-platform.ps1 -Detailed
```

This shows:
- Service health status
- Port availability
- Container status
- AI models installed
- Connectivity tests

---

## 🌐 Access Your Platform

After deployment, access services at:

**Infrastructure:**
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- MinIO Console: http://localhost:9001
- ChromaDB: http://localhost:8000
- Ollama: http://localhost:11434

**Monitoring:**
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin123)
- Loki: http://localhost:3100
- Jaeger: http://localhost:16686

---

## 🆘 Need Help?

1. **Check README.md** - Complete documentation
2. **Check QUICK-REFERENCE.md** - Common commands
3. **Check TROUBLESHOOTING.md** - Fix common issues

**Common Issues:**

Port already in use:
```powershell
netstat -ano | findstr :<port>
Stop-Process -Id <PID> -Force
```

Container won't start:
```powershell
docker logs <container-name>
```

Complete reset:
```powershell
.\rebuild-platform.ps1
```

---

## 📊 Verify Deployment Success

You should see output like:
```
🎉 Platform Deployment Completed Successfully! 🎉

Infrastructure Services:
  • PostgreSQL:      localhost:5432 ✓
  • Redis:           localhost:6379 ✓
  • MinIO Console:   http://localhost:9001 ✓
  • ChromaDB:        http://localhost:8000 ✓
  • Ollama:          http://localhost:11434 ✓

Monitoring Stack:
  • Prometheus:      http://localhost:9090 ✓
  • Grafana:         http://localhost:3000 ✓
  • Loki:            http://localhost:3100 ✓
  • Jaeger:          http://localhost:16686 ✓
```

---

## 📞 Support

If you encounter any issues:

1. Run validation:
   ```powershell
   .\validate-platform.ps1 -Detailed
   ```

2. Check container logs:
   ```powershell
   docker logs <container-name>
   ```

3. Review TROUBLESHOOTING.md for solutions

4. Generate diagnostic report:
   ```powershell
   docker info > diagnostic-report.txt
   docker ps -a >> diagnostic-report.txt
   .\validate-platform.ps1 -Detailed >> diagnostic-report.txt
   ```

---

## 🎯 Next Steps

After successful deployment:

1. **Test Core Services**
   ```powershell
   # Test Ollama
   docker exec ollama ollama list
   
   # Test PostgreSQL
   docker exec postgres psql -U modernization -d legacy_modernization -c "SELECT version();"
   
   # Test Redis
   docker exec redis redis-cli PING
   ```

2. **Configure Grafana Dashboards**
   - Visit http://localhost:3000
   - Add Prometheus data source: http://prometheus:9090
   - Add Loki data source: http://loki:3100

3. **Run Your Workflows**
   - Legacy code analysis
   - Architecture diagram generation
   - Jira ticket generation

---

## 🔐 Default Credentials

Remember to change these in production:

- **PostgreSQL**: modernization / modernization123
- **MinIO**: minioadmin / minioadmin123
- **Grafana**: admin / admin123

---

## ✨ Enjoy Your Platform!

You now have a complete AI-powered Legacy Application Modernization Platform running locally with full monitoring and observability!

For detailed documentation, refer to README.md

**Last Updated**: 2026-01-16
**Platform Version**: 1.0.0
