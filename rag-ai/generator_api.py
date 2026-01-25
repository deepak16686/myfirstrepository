from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import chromadb
import json
import logging
from typing import Optional
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Dockerfile & GitLab CI Generator")

# Connect to ChromaDB
chroma_client = chromadb.HttpClient(host='localhost', port=8000)
dockerfile_collection = chroma_client.get_collection("templates_dockerfile")
gitlab_collection = chroma_client.get_collection("templates_gitlab")
golden_rules_collection = chroma_client.get_collection("golden_rules")

# Load catalog
with open('rag-ai/catalog.json', 'r') as f:
    CATALOG = json.load(f)

class DockerfileRequest(BaseModel):
    stack: str  # java, python, node
    framework: Optional[str] = None
    port: Optional[int] = 8080
    workdir: Optional[str] = "/app"

class GitLabCIRequest(BaseModel):
    stack: str  # java, python, node
    build_tool: Optional[str] = None

class ValidationResult(BaseModel):
    valid: bool
    issues: list = []

@app.get("/")
def root():
    return {"status": "AI Generator API Running", "version": "1.1"}

@app.get("/health")
def health():
    """Health check endpoint"""
    try:
        chroma_client.heartbeat()
        df_count = dockerfile_collection.count()
        gl_count = gitlab_collection.count()
        return {
            "status": "healthy",
            "chromadb": "connected",
            "templates": {"dockerfiles": df_count, "gitlab_ci": gl_count},
            "catalog_stacks": list(CATALOG.keys()),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unhealthy: {str(e)}")

@app.get("/collections")
def list_collections():
    """List ChromaDB collections with document counts"""
    try:
        return {
            "templates_dockerfile": dockerfile_collection.count(),
            "templates_gitlab": gitlab_collection.count(),
            "golden_rules": golden_rules_collection.count()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/dockerfile")
def generate_dockerfile(request: DockerfileRequest):
    """Generate Dockerfile from templates and Nexus catalog"""
    logger.info(f"Dockerfile request: stack={request.stack}, framework={request.framework}")

    # Step 1: Classify request
    base_key = request.stack

    # Step 2: Resolve base image from catalog
    if base_key not in CATALOG:
        raise HTTPException(
            status_code=400,
            detail=f"TEMPLATE_MISSING: No base image for stack '{base_key}' in Nexus catalog. "
                   f"Available stacks: {[k for k in CATALOG.keys() if k in ['java','python','node']]}"
        )

    base_image_info = CATALOG[base_key]
    base_image = f"{base_image_info['image_path']}:{base_image_info['selected_tag']}"

    # Step 3: Retrieve template from ChromaDB
    try:
        results = dockerfile_collection.query(
            query_texts=[f"{request.stack} {request.framework or ''} application"],
            n_results=1,
            where={"stack": request.stack}
        )
    except Exception as e:
        logger.error(f"ChromaDB query failed: {e}")
        raise HTTPException(status_code=500, detail=f"ChromaDB query error: {str(e)}")

    if not results['ids'][0]:
        raise HTTPException(
            status_code=404,
            detail=f"TEMPLATE_MISSING: No Dockerfile template for stack '{request.stack}'. "
                   f"Run 'python ingest_templates.py' to load templates."
        )

    template_content = results['documents'][0][0]
    template_id = results['ids'][0][0]
    template_metadata = results['metadatas'][0][0] if results['metadatas'][0] else {}

    # Step 4: Fill placeholders
    dockerfile = template_content.replace("${BASE_REGISTRY}", "localhost:5001")
    dockerfile = dockerfile.replace("ARG BASE_REGISTRY=ai-nexus:5001", f"# Base: {base_image}")

    # Only replace workdir and port if they differ from defaults
    if request.workdir != "/app":
        dockerfile = dockerfile.replace("/app", request.workdir)
    if request.port != 8080:
        dockerfile = dockerfile.replace("8080", str(request.port))

    # Step 5: Validate (check for public registry references)
    public_registries = ["docker.io", "FROM python:", "FROM node:", "FROM openjdk:", "ghcr.io"]
    for reg in public_registries:
        if reg in dockerfile:
            raise HTTPException(
                status_code=400,
                detail=f"VALIDATION_FAILED: Public registry '{reg}' detected in generated Dockerfile"
            )

    logger.info(f"Dockerfile generated: template={template_id}, base={base_image}")

    return {
        "content": dockerfile,
        "audit": {
            "template_id": template_id,
            "base_image": base_image,
            "stack": request.stack,
            "framework": request.framework,
            "port": request.port,
            "workdir": request.workdir,
            "template_metadata": template_metadata,
            "generated_at": datetime.utcnow().isoformat()
        }
    }

@app.post("/generate/gitlabci")
def generate_gitlab_ci(request: GitLabCIRequest):
    """Generate .gitlab-ci.yml from templates"""
    logger.info(f"GitLab CI request: stack={request.stack}, build_tool={request.build_tool}")

    # Step 1: Retrieve template from ChromaDB
    try:
        results = gitlab_collection.query(
            query_texts=[f"{request.stack} {request.build_tool or ''} pipeline"],
            n_results=1,
            where={"stack": request.stack}
        )
    except Exception as e:
        logger.error(f"ChromaDB query failed: {e}")
        raise HTTPException(status_code=500, detail=f"ChromaDB query error: {str(e)}")

    if not results['ids'][0]:
        raise HTTPException(
            status_code=404,
            detail=f"TEMPLATE_MISSING: No GitLab CI template for stack '{request.stack}'. "
                   f"Run 'python ingest_templates.py' to load templates."
        )

    template_content = results['documents'][0][0]
    template_id = results['ids'][0][0]
    template_metadata = results['metadatas'][0][0] if results['metadatas'][0] else {}

    # Step 2: Return template
    gitlab_ci = template_content

    # Step 3: Validate YAML structure
    if "stages:" not in gitlab_ci:
        raise HTTPException(
            status_code=400,
            detail="VALIDATION_FAILED: Missing 'stages' in GitLab CI"
        )

    # Step 4: Count stages for audit
    stage_count = gitlab_ci.count("stage:")

    logger.info(f"GitLab CI generated: template={template_id}, stages={stage_count}")

    return {
        "content": gitlab_ci,
        "audit": {
            "template_id": template_id,
            "stack": request.stack,
            "build_tool": request.build_tool,
            "stage_count": stage_count,
            "template_metadata": template_metadata,
            "generated_at": datetime.utcnow().isoformat()
        }
    }

@app.post("/validate/dockerfile")
def validate_dockerfile(content: dict):
    """Validate a Dockerfile against golden rules"""
    dockerfile_content = content.get("content", "")
    issues = []

    if not dockerfile_content:
        raise HTTPException(status_code=400, detail="No content provided")

    # Check for public registries
    public_registries = ["docker.io", "FROM python:", "FROM node:", "FROM openjdk:",
                         "ghcr.io", "quay.io", "mcr.microsoft.com"]
    for reg in public_registries:
        if reg in dockerfile_content:
            issues.append(f"Public registry detected: {reg}")

    # Check required directives
    if "FROM" not in dockerfile_content:
        issues.append("Missing FROM statement")
    if "EXPOSE" not in dockerfile_content:
        issues.append("Missing EXPOSE statement")
    if "WORKDIR" not in dockerfile_content:
        issues.append("Missing WORKDIR statement")

    # Check for private registry usage
    if "localhost:5001" not in dockerfile_content and "ai-nexus:5001" not in dockerfile_content:
        issues.append("No private registry (localhost:5001 or ai-nexus:5001) reference found")

    return {"valid": len(issues) == 0, "issues": issues}

@app.post("/validate/gitlabci")
def validate_gitlab_ci(content: dict):
    """Validate a GitLab CI file against golden rules"""
    ci_content = content.get("content", "")
    issues = []

    if not ci_content:
        raise HTTPException(status_code=400, detail="No content provided")

    if "stages:" not in ci_content:
        issues.append("Missing 'stages:' definition")
    if "docker.io" in ci_content:
        issues.append("Public registry reference detected")
    if "build" not in ci_content.lower():
        issues.append("No build stage found")

    return {"valid": len(issues) == 0, "issues": issues}

@app.get("/catalog")
def get_catalog():
    """View available base images"""
    return CATALOG

@app.get("/catalog/{stack}")
def get_catalog_stack(stack: str):
    """Get catalog entry for a specific stack"""
    if stack not in CATALOG:
        raise HTTPException(status_code=404, detail=f"Stack '{stack}' not found in catalog")
    return {stack: CATALOG[stack]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
