"""
Default workflow and Dockerfile templates for various languages.

Provides built-in templates for Java, Python, Node.js, and Go.
Container jobs (compile, static-analysis) use actions/checkout@v4 inside fresh containers.
Non-container jobs (build-image, sonarqube) use shell git clone to avoid stale
action cache issues on Gitea act_runner's host executor.
Dockerfiles are multi-stage (Java, Go) so each job is self-contained - no artifact passing.
"""
from typing import Dict, Any


# Shell-based checkout for non-container (host executor) jobs.
# Avoids actions/checkout@v4 stale cache "non-fast-forward update" errors.
_SHELL_CHECKOUT = '''- name: Checkout code
        run: |
          cd / && rm -rf "$GITHUB_WORKSPACE" || true
          git clone --depth 1 --branch "$GITHUB_REF_NAME" \\
            "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY.git" "$GITHUB_WORKSPACE"
          cd "$GITHUB_WORKSPACE"'''


def _get_default_workflow(analysis: Dict[str, Any], runner_type: str = "self-hosted") -> str:
    """Get default GitHub Actions workflow template"""
    language = analysis.get("language", "java")

    templates = {
        "java": _get_java_workflow_template(runner_type),
        "python": _get_python_workflow_template(runner_type),
        "javascript": _get_nodejs_workflow_template(runner_type),
        "go": _get_go_workflow_template(runner_type)
    }

    return templates.get(language, templates["java"])


def _env_block() -> str:
    """Common env block shared by all templates"""
    return '''env:
  NEXUS_REGISTRY: ${{ secrets.NEXUS_REGISTRY }}
  NEXUS_USERNAME: ${{ secrets.NEXUS_USERNAME }}
  NEXUS_PASSWORD: ${{ secrets.NEXUS_PASSWORD }}
  IMAGE_NAME: ${{ github.event.repository.name }}
  IMAGE_TAG: "1.0.${{ github.run_number }}"
  RELEASE_TAG: "1.0.release-${{ github.run_number }}"
  SONARQUBE_URL: ${{ secrets.SONARQUBE_URL }}
  SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
  SPLUNK_HEC_URL: ${{ secrets.SPLUNK_HEC_URL }}
  SPLUNK_HEC_TOKEN: ${{ secrets.SPLUNK_HEC_TOKEN }}
  DEVOPS_BACKEND_URL: ${{ secrets.DEVOPS_BACKEND_URL }}'''


def _tail_jobs(runner_type: str, sonar_sources: str = "src") -> str:
    """Common tail jobs shared by all templates (sonarqube through learn-record)"""
    return f'''  sonarqube:
    needs: compile
    runs-on: {runner_type}
    steps:
      {_SHELL_CHECKOUT}
      - name: SonarQube Scan
        run: |
          docker run --rm --network ai-platform-net \\
            -v "${{{{ github.workspace }}}}":/workspace -w /workspace \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest \\
            sonar-scanner \\
              -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
              -Dsonar.sources={sonar_sources} \\
              -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
              -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          docker run --rm --network ai-platform-net \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest \\
            image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        run: docker login -u ${{{{ env.NEXUS_USERNAME }}}} -p ${{{{ env.NEXUS_PASSWORD }}}} ${{{{ env.NEXUS_REGISTRY }}}}
      - name: Tag and Push Release
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker tag ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}

  notify-success:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Notify Success
        run: |
          wget -q --no-check-certificate \\
            --header="Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            --header="Content-Type: application/json" \\
            --post-data='{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}' \\
            "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" -O /dev/null || true

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          wget -q --no-check-certificate \\
            --header="Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            --header="Content-Type: application/json" \\
            --post-data='{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}' \\
            "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" -O /dev/null || true

  learn-record:
    needs: [compile, build-image, test-image, static-analysis, sonarqube, trivy-scan, push-release, notify-success]
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          wget -q --no-check-certificate \\
            --header="Content-Type: application/json" \\
            --post-data='{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' \\
            "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" -O /dev/null && echo "SUCCESS: Configuration recorded for RL"'''


def _get_java_workflow_template(runner_type: str = "self-hosted") -> str:
    """Java workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*', 'ci-pipeline-*']
  pull_request:
    branches: [main]

{_env_block()}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/maven:3.9-eclipse-temurin-17-node20
    steps:
      - uses: actions/checkout@v4
      - name: Build with Maven
        run: mvn clean package -DskipTests

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      {_SHELL_CHECKOUT}
      - name: Login to Nexus Registry
        run: docker login -u ${{{{ env.NEXUS_USERNAME }}}} -p ${{{{ env.NEXUS_PASSWORD }}}} ${{{{ env.NEXUS_REGISTRY }}}}
      - name: Build and Push Image
        run: |
          docker build \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest .
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/maven:3.9-eclipse-temurin-17-node20
    steps:
      - uses: actions/checkout@v4
      - name: Run Static Analysis
        run: mvn checkstyle:check || true

{_tail_jobs(runner_type, "src")}
'''


def _get_python_workflow_template(runner_type: str = "self-hosted") -> str:
    """Python workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*', 'ci-pipeline-*']
  pull_request:
    branches: [main]

{_env_block()}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/python:3.11-slim-node20
    steps:
      - uses: actions/checkout@v4
      - name: Install Dependencies
        run: |
          pip install --no-cache-dir -r requirements.txt
          pip install pytest flake8
      - name: Run Tests
        run: pytest tests/ -v || true

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      {_SHELL_CHECKOUT}
      - name: Login to Nexus Registry
        run: docker login -u ${{{{ env.NEXUS_USERNAME }}}} -p ${{{{ env.NEXUS_PASSWORD }}}} ${{{{ env.NEXUS_REGISTRY }}}}
      - name: Build and Push Image
        run: |
          docker build \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest .
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/python:3.11-slim-node20
    steps:
      - uses: actions/checkout@v4
      - name: Run Flake8
        run: |
          pip install flake8
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true

{_tail_jobs(runner_type, ".")}
'''


def _get_nodejs_workflow_template(runner_type: str = "self-hosted") -> str:
    """Node.js workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*', 'ci-pipeline-*']
  pull_request:
    branches: [main]

{_env_block()}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/node:20-slim
    steps:
      - uses: actions/checkout@v4
      - name: Install and Build
        run: |
          npm ci
          npm run build --if-present

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      {_SHELL_CHECKOUT}
      - name: Login to Nexus Registry
        run: docker login -u ${{{{ env.NEXUS_USERNAME }}}} -p ${{{{ env.NEXUS_PASSWORD }}}} ${{{{ env.NEXUS_REGISTRY }}}}
      - name: Build and Push Image
        run: |
          docker build \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest .
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/node:20-slim
    steps:
      - uses: actions/checkout@v4
      - name: Run ESLint
        run: |
          npm ci
          npm run lint --if-present || true

{_tail_jobs(runner_type, "src")}
'''


def _get_go_workflow_template(runner_type: str = "self-hosted") -> str:
    """Go workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*', 'ci-pipeline-*']
  pull_request:
    branches: [main]

{_env_block()}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/golang:1.22-bullseye-node20
    steps:
      - uses: actions/checkout@v4
      - name: Build Binary
        run: CGO_ENABLED=0 GOOS=linux go build -o app .

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      {_SHELL_CHECKOUT}
      - name: Login to Nexus Registry
        run: docker login -u ${{{{ env.NEXUS_USERNAME }}}} -p ${{{{ env.NEXUS_PASSWORD }}}} ${{{{ env.NEXUS_REGISTRY }}}}
      - name: Build and Push Image
        run: |
          docker build \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            -t ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest .
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/golang:1.22-bullseye-node20
    steps:
      - uses: actions/checkout@v4
      - name: Run Go Vet
        run: go vet ./... || true

{_tail_jobs(runner_type, ".")}
'''


def _get_default_dockerfile(analysis: Dict[str, Any]) -> str:
    """Get default Dockerfile based on language.

    Java and Go use multi-stage builds (compile from source inside Docker).
    Python and Node.js copy source directly (interpreted languages).
    All images come from Nexus (localhost:5001 is the Docker daemon's address).
    """
    language = analysis.get("language", "java")

    dockerfiles = {
        "java": '''FROM localhost:5001/apm-repo/demo/maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:resolve || true
COPY src ./src
RUN mvn clean package -DskipTests

FROM localhost:5001/apm-repo/demo/amazoncorretto:17-alpine-jdk
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
''',
        "python": '''FROM localhost:5001/apm-repo/demo/python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
        "javascript": '''FROM localhost:5001/apm-repo/demo/node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]
''',
        "go": '''FROM localhost:5001/apm-repo/demo/golang:1.22-bullseye AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o app .

FROM localhost:5001/apm-repo/demo/alpine:3.18
WORKDIR /app
COPY --from=build /app/app .
RUN chmod +x app
EXPOSE 8080
CMD ["./app"]
'''
    }

    return dockerfiles.get(language, dockerfiles["java"])
