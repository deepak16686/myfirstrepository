"""
Create simplified Pipeline tools for Open WebUI.
These tools work directly without requiring the devops-tools-backend service.
"""
import textwrap
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR
from pathlib import Path

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"

# ============================================================
# Tool 1: GitLab Pipeline Generator
# ============================================================
PIPELINE_TOOL_ID = "gitlab_pipeline_generator"
PIPELINE_CONTENT = replace_imports(textwrap.dedent('''
"""
title: GitLab Pipeline Generator
description: Generate GitLab CI/CD pipeline YAML using Nexus private registry images
author: AI DevOps
version: 2.0.0
"""
import os
import requests

class Tools:
    def __init__(self):
        self.registry = os.getenv("NEXUS_REGISTRY", "http://ai-nexus:5001").rstrip("/")
        self.user = os.getenv("NEXUS_USER", "admin")
        self.password = os.getenv("NEXUS_PASS", "r")
        self.pull_registry = "localhost:5001"

    def get_pipeline_template(self, technology: str = "java", stages: str = "all") -> str:
        """
        Generate a complete .gitlab-ci.yml pipeline for a technology.

        Args:
            technology: java, python, node, golang, php, dotnet, rust, ruby, gradle
            stages: 'all' for complete pipeline, or comma-separated like: compile,build,test

        Returns:
            Ready-to-use YAML pipeline configuration
        """
        tech = technology.lower().strip()
        auth = (self.user, self.password)

        # Get images from Nexus
        try:
            resp = requests.get(f"{self.registry}/v2/_catalog", auth=auth, timeout=10)
            resp.raise_for_status()
            data = resp.json() or {}
            repos = data.get("repositories", [])
        except Exception as e:
            return f"Error connecting to Nexus: {e}"

        def find_image(keyword):
            matched = [r for r in repos if keyword.lower() in r.lower()]
            if matched:
                try:
                    r = requests.get(f"{self.registry}/v2/{matched[0]}/tags/list", auth=auth, timeout=10)
                    r.raise_for_status()
                    tag_data = r.json() or {}
                    tags = tag_data.get("tags") or []
                    if tags:
                        return f"${{NEXUS_PULL_REGISTRY}}/{matched[0]}:{tags[0]}"
                except:
                    pass
            return ""

        # Map technology to image keywords
        image_map = {
            "java": "maven", "python": "python", "node": "node",
            "golang": "golang", "go": "golang", "php": "php",
            "dotnet": "dotnet", "rust": "rust", "ruby": "ruby", "gradle": "gradle"
        }

        main_image = find_image(image_map.get(tech, tech))
        kaniko_image = find_image("kaniko")
        alpine_image = find_image("alpine-curl") or find_image("alpine")
        trivy_image = find_image("trivy")
        sonar_image = find_image("sonar-scanner")

        if not main_image and tech in image_map:
            return f"Error: {tech} image not found in Nexus registry. Available repos: {repos[:10]}"

        # Determine stages
        if stages == "all":
            requested = ["compile", "build", "test", "sast", "quality", "security", "push", "notify"]
        else:
            requested = [s.strip() for s in stages.split(",")]

        # Compile scripts per technology
        compile_scripts = {
            "java": ["mvn clean package -DskipTests", "cp target/*.jar target/app.jar 2>/dev/null || true"],
            "python": ["pip install -r requirements.txt", "python -m compileall ."],
            "node": ["npm ci", "npm run build || true"],
            "golang": ["go mod download", "CGO_ENABLED=0 go build -o app ."],
            "gradle": ["gradle build -x test"]
        }

        scripts = compile_scripts.get(tech, [f"echo Building {tech}..."])

        # Build YAML
        yaml = []
        yaml.append("stages:\\n  - " + "\\n  - ".join(requested))
        yaml.append(f"""
variables:
  RELEASE_TAG: "1.0.release-${{CI_PIPELINE_IID}}"
  NEXUS_REGISTRY: "ai-nexus:5001"
  NEXUS_PULL_REGISTRY: "{self.pull_registry}"
  IMAGE_NAME: "${{CI_PROJECT_NAME}}"
  IMAGE_TAG: "1.0.${{CI_PIPELINE_IID}}"
  DOCKER_TLS_CERTDIR: ""
  DOCKER_HOST: "tcp://docker:2375"
  FF_NETWORK_PER_BUILD: "true"
  SONAR_HOST_URL: "http://ai-sonarqube:9000"
""")

        if "compile" in requested and main_image:
            script_lines = "\\n".join([f"    - {s}" for s in scripts])
            yaml.append(f"""
compile:
  stage: compile
  image: {main_image}
  tags: [docker]
  script:
{script_lines}
  artifacts:
    paths: [target/, dist/, build/, .]
    expire_in: 1 hour
""")

        if "build" in requested and kaniko_image:
            yaml.append(f"""
build_image:
  stage: build
  image:
    name: {kaniko_image}
    entrypoint: [""]
  tags: [docker]
  script:
    - mkdir -p /kaniko/.docker
    - echo "{{\\"auths\\":{{\\"${{NEXUS_REGISTRY}}\\":{{\\"username\\":\\"${{NEXUS_USERNAME}}\\",\\"password\\":\\"${{NEXUS_PASSWORD}}\\"}}}}}}" > /kaniko/.docker/config.json
    - /kaniko/executor --context "${{CI_PROJECT_DIR}}" --dockerfile "${{CI_PROJECT_DIR}}/Dockerfile" --destination "${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}" --insecure --skip-tls-verify
""")

        if "test" in requested and alpine_image:
            yaml.append(f"""
test_image:
  stage: test
  image: {alpine_image}
  tags: [docker]
  script:
    - apk add --no-cache curl
    - 'curl -sf -u "${{NEXUS_USERNAME}}:${{NEXUS_PASSWORD}}" "http://${{NEXUS_REGISTRY}}/v2/apm-repo/demo/${{IMAGE_NAME}}/manifests/latest" || echo "Image check completed"'
""")

        if "quality" in requested and sonar_image:
            yaml.append(f"""
sonarqube:
  stage: quality
  image: {sonar_image}
  tags: [docker]
  script:
    - sonar-scanner -Dsonar.projectKey=${{CI_PROJECT_NAME}} -Dsonar.host.url=${{SONAR_HOST_URL}} -Dsonar.token=${{SONAR_TOKEN}}
  allow_failure: true
""")

        if "security" in requested and trivy_image and alpine_image:
            yaml.append(f"""
trivy_scan:
  stage: security
  image: {alpine_image}
  services:
    - name: {trivy_image}
      alias: trivy-server
      command: ["server", "--listen", "0.0.0.0:8080"]
  tags: [docker]
  script:
    - apk add --no-cache curl
    - curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin || true
    - trivy image --server http://trivy-server:8080 --severity HIGH,CRITICAL ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:latest || true
  allow_failure: true
""")

        if "push" in requested and alpine_image:
            yaml.append(f"""
push_release:
  stage: push
  image: {alpine_image}
  tags: [docker]
  script:
    - apk add --no-cache curl jq
    - 'MANIFEST=$(curl -s -u "${{NEXUS_USERNAME}}:${{NEXUS_PASSWORD}}" -H "Accept: application/vnd.docker.distribution.manifest.v2+json" "http://${{NEXUS_REGISTRY}}/v2/apm-repo/demo/${{IMAGE_NAME}}/manifests/latest")'
    - 'curl -s -u "${{NEXUS_USERNAME}}:${{NEXUS_PASSWORD}}" -X PUT -H "Content-Type: application/vnd.docker.distribution.manifest.v2+json" -d "$MANIFEST" "http://${{NEXUS_REGISTRY}}/v2/apm-repo/demo/${{IMAGE_NAME}}/manifests/${{RELEASE_TAG}}"'
""")

        if "notify" in requested and alpine_image:
            yaml.append(f"""
notify_success:
  stage: notify
  image: {alpine_image}
  tags: [docker]
  script:
    - echo "Pipeline completed successfully"
  when: on_success
  allow_failure: true
""")

        return "\\n".join(yaml)
''').strip())

# ============================================================
# Tool 2: Nexus Docker Images
# ============================================================
DOCKER_TOOL_ID = "nexus_docker_images"
DOCKER_CONTENT = replace_imports(textwrap.dedent('''
"""
title: Nexus Docker Images
description: List Docker images from Nexus and generate Dockerfiles
author: AI DevOps
version: 2.0.0
"""
import os
import requests

class Tools:
    def __init__(self):
        self.registry = os.getenv("NEXUS_REGISTRY", "http://ai-nexus:5001").rstrip("/")
        self.user = os.getenv("NEXUS_USER", "admin")
        self.password = os.getenv("NEXUS_PASS", "r")
        self.pull_registry = "localhost:5001"

    def list_docker_images(self, query: str = "") -> str:
        """
        List Docker images from Nexus and generate a Dockerfile.

        Args:
            query: Search keyword like python, node, java, nginx, alpine, etc.

        Returns:
            Available images and a sample Dockerfile
        """
        auth = (self.user, self.password)

        try:
            resp = requests.get(f"{self.registry}/v2/_catalog", auth=auth, timeout=10)
            resp.raise_for_status()
            data = resp.json() or {}
            repos = data.get("repositories", [])
        except Exception as e:
            return f"Error connecting to Nexus: {e}"

        if not repos:
            return "No repositories found in Nexus registry."

        # Filter by query
        if query:
            matched = [r for r in repos if query.lower() in r.lower()]
        else:
            matched = repos[:20]

        if not matched:
            return f"No images found matching '{query}'. Available: {', '.join(repos[:15])}"

        # Get tags for matched repos
        results = []
        for repo in matched[:5]:
            try:
                r = requests.get(f"{self.registry}/v2/{repo}/tags/list", auth=auth, timeout=10)
                r.raise_for_status()
                tag_data = r.json() or {}
                tags = tag_data.get("tags") or []
                if tags:
                    results.append(f"- **{repo}**: {', '.join(tags[:5])}")
            except:
                results.append(f"- **{repo}**: (unable to fetch tags)")

        # Generate sample Dockerfile
        base_image = matched[0] if matched else "alpine"
        dockerfile = self._generate_dockerfile(query or "generic", base_image)

        output = f"""## Available Images in Nexus Registry

{chr(10).join(results)}

---

## Sample Dockerfile for {query or 'generic'} application

```dockerfile
{dockerfile}
```

**Pull command:**
```bash
docker pull {self.pull_registry}/{matched[0]}:latest
```
"""
        return output

    def _generate_dockerfile(self, tech: str, base_image: str) -> str:
        tech = tech.lower()
        registry = "ai-nexus:5001/apm-repo/demo"

        if "python" in tech or "python" in base_image:
            return f"""ARG BASE_REGISTRY={registry}
FROM ${{BASE_REGISTRY}}/python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
        elif "node" in tech or "node" in base_image:
            return f"""ARG BASE_REGISTRY={registry}
FROM ${{BASE_REGISTRY}}/node:18-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .

EXPOSE 3000
CMD ["npm", "start"]
"""
        elif "java" in tech or "maven" in base_image:
            return f"""ARG BASE_REGISTRY={registry}
FROM ${{BASE_REGISTRY}}/amazoncorretto:17-alpine-jdk

WORKDIR /app
COPY target/app.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
"""
        elif "go" in tech or "golang" in base_image:
            return f"""ARG BASE_REGISTRY={registry}
FROM ${{BASE_REGISTRY}}/golang:1.21-alpine as builder
WORKDIR /app
COPY . .
RUN CGO_ENABLED=0 go build -o main .

FROM ${{BASE_REGISTRY}}/alpine:3.18
WORKDIR /app
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]
"""
        else:
            return f"""ARG BASE_REGISTRY={registry}
FROM ${{BASE_REGISTRY}}/alpine:3.18

WORKDIR /app
COPY . .

CMD ["/bin/sh"]
"""
''').strip())

# ============================================================
# Create the tools
# ============================================================
def create_tool(tool_id, name, content, description):
    # Delete if exists
    existing = Tools.get_tool_by_id(tool_id)
    if existing:
        Tools.delete_tool_by_id(tool_id)
        print(f"Deleted existing tool: {tool_id}")

    # Create form
    meta = ToolMeta(description=description)
    form = ToolForm(id=tool_id, name=name, content=content, meta=meta, access_control=None)

    # Load module to get specs
    module, frontmatter = load_tool_module_by_id(tool_id, content=form.content)
    form.meta.manifest = frontmatter
    specs = get_tool_specs(module)

    # Create tool
    tool = Tools.insert_new_tool(USER_ID, form, specs)

    # Ensure cache dir exists
    (CACHE_DIR / "tools" / tool_id).mkdir(parents=True, exist_ok=True)

    return {"created": bool(tool), "id": tool_id, "specs": specs}

# Create both tools
print("Creating GitLab Pipeline Generator tool...")
result1 = create_tool(
    PIPELINE_TOOL_ID,
    "GitLab Pipeline Generator",
    PIPELINE_CONTENT,
    "Generate GitLab CI/CD pipeline YAML using Nexus private registry images"
)
print(f"  Result: {result1}")

print("\nCreating Nexus Docker Images tool...")
result2 = create_tool(
    DOCKER_TOOL_ID,
    "Nexus Docker Images",
    DOCKER_CONTENT,
    "List Docker images from Nexus and generate Dockerfiles"
)
print(f"  Result: {result2}")

print("\nDone!")
