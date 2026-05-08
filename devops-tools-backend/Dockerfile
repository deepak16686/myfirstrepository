FROM python:3.11-slim

WORKDIR /app

# Install Node.js (for Codex Code and optional legacy CLI providers) +
# curl/ca-certificates so we can
# pull the NodeSource setup script. The Codex CLI runs as the default LLM
# provider when LLM_PROVIDER=codex-code is set in the environment, and
# authenticates via the host's ~/.codex directory mounted to /root/.codex.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates skopeo && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @openai/codex && \
    npm install -g @anthropic-ai/claude-code && \
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

# Health check — python-only so we don't need to install curl into the slim image.
# Matches the compose-level healthcheck in devops-tools-backend/docker-compose.yml.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8003/health', timeout=5).status==200 else 1)" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
