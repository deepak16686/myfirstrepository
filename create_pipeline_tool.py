import textwrap, os
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR
from pathlib import Path

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"
TOOL_ID = "gitlab_pipeline_generator"

content = replace_imports(textwrap.dedent('''
"""
description: Generate GitLab CI pipeline templates using Nexus private registry images
"""
import os, requests, json

REGISTRY = os.getenv("NEXUS_REGISTRY", "http://ai-nexus:5001").rstrip("/")
USER = os.getenv("NEXUS_USER", "admin")
PASS = os.getenv("NEXUS_PASS", "r")

STAGE_TEMPLATES = {
    "compile": {
        "java": {
            "stage": "compile",
            "image_query": "maven",
            "script": [
                "echo \\"Compiling Java application with Maven...\\"",
                "mvn clean package -DskipTests",
                "find target -maxdepth 1 -name \\"*.jar\\" ! -name \\"*-sources*\\" ! -name \\"original-*\\" | head -1 | xargs -I {} cp {} target/app.jar"
            ],
            "artifacts": {"paths": ["target/app.jar"], "expire_in": "1 hour"},
            "cache": {"paths": [".m2/repository"]}
        },
        "python": {
            "stage": "compile",
            "image_query": "python",
            "script": [
                "echo \\"Installing Python dependencies...\\"",
                "pip install --no-cache-dir -r requirements.txt",
                "python -m compileall ."
            ],
            "artifacts": {"paths": ["."], "expire_in": "1 hour"}
        },
        "node": {
            "stage": "compile",
            "image_query": "node",
            "script": [
                "echo \\"Installing Node.js dependencies...\\"",
                "npm ci",
                "npm run build"
            ],
            "artifacts": {"paths": ["node_modules/", "dist/"], "expire_in": "1 hour"},
            "cache": {"paths": ["node_modules/"]}
        },
        "golang": {
            "stage": "compile",
            "image_query": "golang",
            "script": [
                "echo \\"Compiling Go application...\\"",
                "go mod download",
                "CGO_ENABLED=0 go build -o app ."
            ],
            "artifacts": {"paths": ["app"], "expire_in": "1 hour"},
            "cache": {"paths": ["/go/pkg/mod/"]}
        },
        "php": {
            "stage": "compile",
            "image_query": "php",
            "script": [
                "echo \\"Installing PHP dependencies...\\"",
                "composer install --no-dev --optimize-autoloader"
            ],
            "artifacts": {"paths": ["vendor/"], "expire_in": "1 hour"},
            "cache": {"paths": ["vendor/"]}
        },
        "dotnet": {
            "stage": "compile",
            "image_query": "dotnet",
            "script": [
                "echo \\"Building .NET application...\\"",
                "dotnet restore",
                "dotnet publish -c Release -o out"
            ],
            "artifacts": {"paths": ["out/"], "expire_in": "1 hour"}
        },
        "rust": {
            "stage": "compile",
            "image_query": "rust",
            "script": [
                "echo \\"Compiling Rust application...\\"",
                "cargo build --release",
                "cp target/release/app ."
            ],
            "artifacts": {"paths": ["app"], "expire_in": "1 hour"},
            "cache": {"paths": ["target/"]}
        }
    },
    "build": {
        "description": "Build Docker image using Kaniko and push to Nexus",
        "image_query": "kaniko",
        "script_template": "kaniko_build"
    },
    "test": {
        "description": "Verify image exists in Nexus registry",
        "image_query": "alpine",
        "script_template": "registry_verify"
    },
    "sast": {
        "java": {
            "stage": "sast",
            "image_query": "maven",
            "script": [
                "echo \\"=== Running SpotBugs Analysis ===\\"",
                "mvn clean compile spotbugs:check -DskipTests || true",
                "echo \\"=== Running PMD Analysis ===\\"",
                "mvn pmd:check -DskipTests || true"
            ],
            "allow_failure": True
        }
    },
    "quality": {
        "description": "SonarQube analysis",
        "image_query": "maven",
        "script_template": "sonarqube"
    },
    "security": {
        "description": "Trivy vulnerability scan",
        "image_query": "alpine",
        "service_image_query": "trivy",
        "script_template": "trivy_scan"
    },
    "push": {
        "description": "Tag and push release to Nexus",
        "image_query": "alpine",
        "script_template": "registry_tag"
    },
    "notify": {
        "description": "Send pipeline status to Splunk",
        "image_query": "alpine",
        "script_template": "splunk_notify"
    }
}

class Tools:
    def get_pipeline_template(self, technology: str = "", stages: str = "all") -> dict:
        """Get GitLab CI pipeline template for a technology.
        technology: java, python, node, golang, php, dotnet, rust
        stages: 'all' for complete pipeline, or comma-separated: compile,build,test,sast,quality,security,push,notify"""
        auth = (USER, PASS)

        # Get available images from Nexus
        try:
            catalog = requests.get(f"{REGISTRY}/v2/_catalog", auth=auth, timeout=10)
            catalog.raise_for_status()
            repos = catalog.json().get("repositories", [])
        except:
            repos = []

        def find_image(query):
            matched = [r for r in repos if query.lower() in r.lower()]
            results = []
            for repo in matched[:3]:
                try:
                    resp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()
                    results.append({"repository": data.get("name", repo), "tags": data.get("tags", [])})
                except:
                    pass
            return results

        tech = technology.lower().strip()
        requested_stages = [s.strip() for s in stages.split(",")] if stages != "all" else ["compile", "build", "test", "sast", "quality", "security", "push", "notify"]

        pipeline = {
            "technology": tech,
            "requested_stages": requested_stages,
            "registry": "localhost:5001",
            "stages_config": [],
            "variables": {
                "RELEASE_TAG": "1.0.release-${CI_PIPELINE_IID}",
                "NEXUS_REGISTRY": "ai-nexus:5001",
                "NEXUS_PULL_REGISTRY": "localhost:5001",
                "NEXUS_USERNAME": "admin",
                "NEXUS_PASSWORD": "${NEXUS_PASSWORD}",
                "IMAGE_NAME": "${CI_PROJECT_NAME}",
                "IMAGE_TAG": "1.0.${CI_PIPELINE_IID}",
                "DOCKER_TLS_CERTDIR": "",
                "DOCKER_HOST": "tcp://docker:2375",
                "FF_NETWORK_PER_BUILD": "true"
            }
        }

        for stage_name in requested_stages:
            stage_info = {"stage": stage_name}

            if stage_name == "compile" and tech in STAGE_TEMPLATES.get("compile", {}):
                template = STAGE_TEMPLATES["compile"][tech]
                images = find_image(template["image_query"])
                stage_info["template"] = template
                stage_info["available_images"] = images

            elif stage_name == "build":
                images = find_image("kaniko")
                stage_info["description"] = "Build Docker image with Kaniko and push to Nexus"
                stage_info["available_images"] = images
                stage_info["build_method"] = "kaniko"

            elif stage_name == "test":
                images = find_image("alpine-curl") or find_image("alpine")
                stage_info["description"] = "Verify image exists in registry"
                stage_info["available_images"] = images

            elif stage_name == "sast" and tech in STAGE_TEMPLATES.get("sast", {}):
                template = STAGE_TEMPLATES["sast"][tech]
                images = find_image(template["image_query"])
                stage_info["template"] = template
                stage_info["available_images"] = images

            elif stage_name == "quality":
                images = find_image("maven") if tech == "java" else find_image(tech)
                stage_info["description"] = "SonarQube code quality analysis"
                stage_info["available_images"] = images

            elif stage_name == "security":
                images_base = find_image("alpine-curl") or find_image("alpine")
                images_trivy = find_image("trivy")
                stage_info["description"] = "Trivy vulnerability scan"
                stage_info["available_images"] = images_base
                stage_info["service_images"] = images_trivy

            elif stage_name == "push":
                images = find_image("alpine-curl") or find_image("alpine")
                stage_info["description"] = "Tag release and push to Nexus"
                stage_info["available_images"] = images

            elif stage_name == "notify":
                images = find_image("alpine-curl") or find_image("alpine")
                stage_info["description"] = "Send notification to Splunk"
                stage_info["available_images"] = images

            else:
                # Generic stage
                images = find_image(tech) if tech else []
                stage_info["available_images"] = images

            pipeline["stages_config"].append(stage_info)

        pipeline["instructions"] = (
            "Generate a .gitlab-ci.yml file using ONLY images from localhost:5001/. "
            "Use the available_images data to pick the correct FROM image for each stage. "
            "Format: ${NEXUS_PULL_REGISTRY}/<repository>:<tag>. "
            "For build stage, use Kaniko executor. "
            "For test stage, verify image in registry with curl. "
            "For security stage, use Trivy as a service. "
            "For notify stage, send to Splunk HEC. "
            "All images MUST come from the private Nexus registry."
        )

        return pipeline
''').strip())

meta = ToolMeta(description="Generate GitLab CI pipeline templates using Nexus private registry images")
form = ToolForm(id=TOOL_ID, name="GitLab Pipeline Generator", content=content, meta=meta, access_control=None)

existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)

module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
