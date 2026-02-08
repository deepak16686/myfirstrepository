"""
Default workflow and Dockerfile templates for various languages.

Provides built-in templates for Java, Python, Node.js, and Go.
"""
from typing import Dict, Any


def _get_default_workflow(analysis: Dict[str, Any], runner_type: str = "self-hosted") -> str:
    """Get default GitHub Actions workflow template"""
    language = analysis.get("language", "java")
    framework = analysis.get("framework", "generic")

    templates = {
        "java": _get_java_workflow_template(runner_type),
        "python": _get_python_workflow_template(runner_type),
        "javascript": _get_nodejs_workflow_template(runner_type),
        "go": _get_go_workflow_template(runner_type)
    }

    return templates.get(language, templates["java"])


def _get_java_workflow_template(runner_type: str = "self-hosted") -> str:
    """Java workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/maven:3.9-eclipse-temurin-17
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Build with Maven
        run: |
          mvn clean package -DskipTests
          mkdir -p artifacts
          find target -name "*.jar" ! -name "*-sources*" ! -name "*-javadoc*" | head -1 | xargs -I {{}} cp {{}} artifacts/app.jar
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: artifacts/
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-artifacts
          path: artifacts/
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

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
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/maven:3.9-eclipse-temurin-17
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run Static Analysis
        run: mvn checkstyle:check || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=src \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
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
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''


def _get_python_workflow_template(runner_type: str = "self-hosted") -> str:
    """Python workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/python:3.11-slim
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Install Dependencies
        run: |
          pip install --no-cache-dir -r requirements.txt
          pip install pytest flake8
      - name: Run Tests
        run: pytest tests/ -v || true
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: .
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

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
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/python:3.11-slim
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run Flake8
        run: |
          pip install flake8
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=. \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
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
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''


def _get_nodejs_workflow_template(runner_type: str = "self-hosted") -> str:
    """Node.js workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/node:18-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Install and Build
        run: |
          npm ci
          npm run build --if-present
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: |
            dist/
            build/
            .next/
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-artifacts
          path: .
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

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
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/node:18-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run ESLint
        run: |
          npm ci
          npm run lint --if-present || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=src \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
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
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''


def _get_go_workflow_template(runner_type: str = "self-hosted") -> str:
    """Go workflow template"""
    return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/golang:1.21-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Build Binary
        run: |
          CGO_ENABLED=0 GOOS=linux go build -o app .
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: app
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-artifacts
          path: .
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

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
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/golang:1.21-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run Go Vet
        run: go vet ./... || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=. \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
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
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''


def _get_default_dockerfile(analysis: Dict[str, Any]) -> str:
    """Get default Dockerfile based on language"""
    language = analysis.get("language", "java")

    dockerfiles = {
        "java": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/amazoncorretto:17-alpine-jdk
WORKDIR /app
COPY artifacts/app.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
''',
        "python": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
        "javascript": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]
''',
        "go": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/alpine:3.18
WORKDIR /app
COPY app .
RUN chmod +x app
EXPOSE 8080
CMD ["./app"]
'''
    }

    return dockerfiles.get(language, dockerfiles["java"])
