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
description: Generate GitLab CI pipeline YAML using Nexus private registry images
"""
import os, requests

REGISTRY = os.getenv("NEXUS_REGISTRY", "http://ai-nexus:5001").rstrip("/")
USER = os.getenv("NEXUS_USER", "admin")
PASS = os.getenv("NEXUS_PASS", "r")
PULL_REGISTRY = "localhost:5001"

COMPILE_SCRIPTS = {
    "java": ["mvn clean package -DskipTests", "find target -maxdepth 1 -name \\"*.jar\\" ! -name \\"*-sources*\\" ! -name \\"original-*\\" | head -1 | xargs -I {} cp {} target/app.jar"],
    "python": ["pip install --no-cache-dir -r requirements.txt", "python -m compileall ."],
    "node": ["npm ci", "npm run build"],
    "golang": ["go mod download", "CGO_ENABLED=0 go build -o app ."],
    "php": ["composer install --no-dev --optimize-autoloader"],
    "dotnet": ["dotnet restore", "dotnet publish -c Release -o out"],
    "rust": ["cargo build --release"],
    "ruby": ["bundle install --without development test", "ruby -c app.rb"],
    "gradle": ["gradle dependencies --no-daemon", "gradle build --no-daemon -x test"]
}

IMAGE_MAP = {
    "java": "maven",
    "python": "python",
    "node": "node",
    "golang": "golang",
    "go": "golang",
    "php": "php",
    "dotnet": "dotnet",
    "aspnet": "dotnet",
    "rust": "rust",
    "sonarqube": "sonar-scanner",
    "sonar": "sonar-scanner",
    "quality": "sonar-scanner",
    "nginx": "nginx",
    "redis": "redis",
    "mongo": "mongo",
    "postgres": "postgres",
    "maven": "maven",
    "alpine": "alpine",
    "ruby": "ruby",
    "gradle": "gradle"
}

# When technology is a stage name, map to default stages
STAGE_ALIASES = {
    "sonarqube": "quality",
    "sonar": "quality",
    "trivy": "security",
    "security": "security",
    "sast": "sast",
    "test": "test",
    "build": "build",
    "compile": "compile",
    "push": "push",
    "notify": "notify",
    "deploy": "push"
}

class Tools:
    def get_pipeline_template(self, technology: str = "java", stages: str = "all") -> str:
        """Generate a complete .gitlab-ci.yml pipeline for a technology. Returns ready-to-use YAML.
        technology: java, python, node, golang, php, dotnet, rust, sonarqube, trivy
        stages: 'all' for complete pipeline, or comma-separated like: compile,build,test,quality,security"""
        auth = (USER, PASS)
        tech = technology.lower().strip()

        # If technology is actually a stage name, use java as default tech and that as stage
        actual_tech = tech
        if tech in STAGE_ALIASES and tech not in COMPILE_SCRIPTS:
            actual_stages = STAGE_ALIASES[tech]
            if stages == "all":
                stages = actual_stages
            actual_tech = "java"  # default tech for standalone stage requests

        # Find images from Nexus
        image_keyword = IMAGE_MAP.get(actual_tech, actual_tech)
        try:
            catalog = requests.get(f"{REGISTRY}/v2/_catalog", auth=auth, timeout=10)
            catalog.raise_for_status()
            repos = catalog.json().get("repositories", [])

            def find_image(keyword):
                matched = [r for r in repos if keyword.lower() in r.lower()]
                if matched:
                    resp = requests.get(f"{REGISTRY}/v2/{matched[0]}/tags/list", auth=auth, timeout=10)
                    resp.raise_for_status()
                    tags = resp.json().get("tags", [])
                    if tags:
                        return f"${{NEXUS_PULL_REGISTRY}}/{matched[0]}:{tags[0]}"
                return ""

            main_image = find_image(image_keyword)
            kaniko_image = find_image("kaniko")
            alpine_image = find_image("alpine-curl") or find_image("alpine")
            trivy_image = find_image("trivy")
            sonar_image = find_image("sonar-scanner")

        except Exception as e:
            return f"Error connecting to Nexus registry: {str(e)}"

        if not main_image and actual_tech in COMPILE_SCRIPTS:
            return f"{actual_tech} image is not available in your private Nexus registry. Please upload the required image to your Nexus repository first."

        requested = [s.strip() for s in stages.split(",")] if stages != "all" else ["compile", "build", "test", "sast", "quality", "security", "push", "notify"]

        compile_scripts = COMPILE_SCRIPTS.get(actual_tech, [f"echo \\"Building {actual_tech} application...\\""])

        yaml_parts = []

        # Header
        yaml_parts.append("stages:\\n  - " + "\\n  - ".join(requested))
        yaml_parts.append(f"""variables:
  RELEASE_TAG: "1.0.release-${{CI_PIPELINE_IID}}"
  NEXUS_REGISTRY: "ai-nexus:5001"
  NEXUS_PULL_REGISTRY: "{PULL_REGISTRY}"
  NEXUS_USERNAME: "admin"
  NEXUS_PASSWORD: "${{NEXUS_PASSWORD}}"
  IMAGE_NAME: "${{CI_PROJECT_NAME}}"
  IMAGE_TAG: "1.0.${{CI_PIPELINE_IID}}"
  DOCKER_TLS_CERTDIR: ""
  DOCKER_HOST: "tcp://docker:2375"
  FF_NETWORK_PER_BUILD: "true"
  SONAR_HOST_URL: "http://ai-sonarqube:9000"
  SONAR_TOKEN: "${{SONAR_TOKEN}}"
""")

        if "compile" in requested and main_image:
            scripts = "\\n".join([f"    - {s}" for s in compile_scripts])
            yaml_parts.append(f"""compile:
  stage: compile
  image: {main_image}
  tags:
    - docker
  script:
{scripts}
  artifacts:
    paths:
      - target/
      - .
    expire_in: 1 hour""")

        if "build" in requested and kaniko_image:
            yaml_parts.append(f"""build_image:
  stage: build
  image:
    name: {kaniko_image}
    entrypoint: [""]
  tags:
    - docker
  script:
    - mkdir -p /kaniko/.docker
    - echo "{{\\"auths\\":{{\\"${{NEXUS_REGISTRY}}\\":{{\\"username\\":\\"${{NEXUS_USERNAME}}\\",\\"password\\":\\"${{NEXUS_PASSWORD}}\\"}}}}}}" > /kaniko/.docker/config.json
    - /kaniko/executor --context "${{CI_PROJECT_DIR}}" --dockerfile "${{CI_PROJECT_DIR}}/Dockerfile" --destination "${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}" --destination "${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:latest" --insecure --skip-tls-verify
  dependencies:
    - compile""")

        if "test" in requested and alpine_image:
            yaml_parts.append(f"""test_image:
  stage: test
  image: {alpine_image}
  tags:
    - docker
  before_script:
    - apk add --no-cache curl jq
  script:
    - |
      RESPONSE=$(curl -s -o /dev/null -w "%{{http_code}}" -u "${{NEXUS_USERNAME}}:${{NEXUS_PASSWORD}}" "http://${{NEXUS_REGISTRY}}/v2/apm-repo/demo/${{IMAGE_NAME}}/manifests/latest" -H "Accept: application/vnd.docker.distribution.manifest.v2+json")
    - |
      if [ "$RESPONSE" = "200" ]; then
        echo "Image found in registry!"
      else
        echo "ERROR: Image not found (HTTP $RESPONSE)"
        exit 1
      fi
  dependencies:
    - build_image""")

        if "sast" in requested and main_image:
            yaml_parts.append(f"""static_analysis:
  stage: sast
  image: {main_image}
  tags:
    - docker
  script:
    - echo "=== Running Static Analysis ==="
    - mvn clean compile spotbugs:check -DskipTests || true
    - mvn pmd:check -DskipTests || true
  artifacts:
    paths:
      - target/spotbugsXml.xml
      - target/pmd.xml
    when: always
  allow_failure: true""")

        if "quality" in requested:
            scan_image = sonar_image if sonar_image else main_image
            if scan_image:
                yaml_parts.append(f"""sonarqube:
  stage: quality
  image: {scan_image}
  tags:
    - docker
  variables:
    SONAR_USER_HOME: "${{CI_PROJECT_DIR}}/.sonar"
  script:
    - echo "=== Running SonarQube Analysis ==="
    - sonar-scanner -Dsonar.projectKey=${{CI_PROJECT_NAME}} -Dsonar.projectName="${{CI_PROJECT_NAME}}" -Dsonar.host.url=${{SONAR_HOST_URL}} -Dsonar.token=${{SONAR_TOKEN}} -Dsonar.sources=.
  allow_failure: true""")

        if "security" in requested and alpine_image and trivy_image:
            yaml_parts.append(f"""trivy_scan:
  stage: security
  image: {alpine_image}
  services:
    - name: {trivy_image}
      alias: trivy-server
      command: ["server", "--listen", "0.0.0.0:8080"]
  tags:
    - docker
  before_script:
    - apk add --no-cache curl
    - curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
  script:
    - export TRIVY_USERNAME="${{NEXUS_USERNAME}}"
    - export TRIVY_PASSWORD="${{NEXUS_PASSWORD}}"
    - trivy image --server http://trivy-server:8080 --severity HIGH,CRITICAL --insecure ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:latest
  allow_failure: true""")

        if "push" in requested and alpine_image:
            yaml_parts.append(f"""push_release:
  stage: push
  image: {alpine_image}
  tags:
    - docker
  before_script:
    - apk add --no-cache curl jq
  script:
    - |
      MANIFEST=$(curl -s -u "${{NEXUS_USERNAME}}:${{NEXUS_PASSWORD}}" -H "Accept: application/vnd.docker.distribution.manifest.v2+json" "http://${{NEXUS_REGISTRY}}/v2/apm-repo/demo/${{IMAGE_NAME}}/manifests/latest")
    - |
      curl -s -u "${{NEXUS_USERNAME}}:${{NEXUS_PASSWORD}}" -X PUT -H "Content-Type: application/vnd.docker.distribution.manifest.v2+json" -d "$MANIFEST" "http://${{NEXUS_REGISTRY}}/v2/apm-repo/demo/${{IMAGE_NAME}}/manifests/${{RELEASE_TAG}}"
    - echo "Release tag ${{RELEASE_TAG}} created!"
  dependencies:
    - test_image""")

        if "notify" in requested and alpine_image:
            yaml_parts.append(f"""notify_success:
  stage: notify
  image: {alpine_image}
  tags:
    - docker
  script:
    - apk add --no-cache curl
    - |
      curl -k -X POST "${{SPLUNK_HEC_URL}}/services/collector/event" -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" -H "Content-Type: application/json" -d '{{"event":{{"pipeline_id":"'"${{CI_PIPELINE_ID}}"'","status":"success","project":"'"${{CI_PROJECT_NAME}}"'","branch":"'"${{CI_COMMIT_REF_NAME}}"'"}}}}'
  when: on_success
  allow_failure: true""")

        return "\\n\\n".join(yaml_parts)
''').strip())

meta = ToolMeta(description="Generate GitLab CI pipeline YAML using Nexus private registry images")
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
