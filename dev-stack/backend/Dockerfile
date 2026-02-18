# =============================================================================
# Dockerfile: DevOps Tools Backend
# =============================================================================
# Builds the container image for the FastAPI backend (port 8003).
# Built during 'docker compose up -d --build' from the dev-stack infrastructure
# compose file, or standalone via 'docker build -t devops-tools-backend .'.
#
# What it includes:
#   - Python 3.11 (slim base)
#   - Node.js 20 + @anthropic-ai/claude-code CLI (for Claude Code LLM provider)
#   - Terraform 1.7.5 CLI (for terraform plan/apply operations)
#   - skopeo (for container image inspection in registry operations)
#   - All Python dependencies from requirements.txt
#   - Application code (app/ package) and frontend static files (frontend/)
#
# The image exposes port 8003 and runs Uvicorn as the ASGI server.
# A health check polls /health every 30 seconds to support Docker restart policies.
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install Node.js (needed for Claude Code CLI) and Terraform
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates skopeo unzip && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    curl -fsSL https://releases.hashicorp.com/terraform/1.7.5/terraform_1.7.5_linux_amd64.zip -o /tmp/terraform.zip && \
    unzip /tmp/terraform.zip -d /usr/local/bin/ && \
    rm /tmp/terraform.zip && chmod +x /usr/local/bin/terraform && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy frontend
COPY frontend/ ./frontend/

# Create config directory
RUN mkdir -p /app/config

# Expose port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
