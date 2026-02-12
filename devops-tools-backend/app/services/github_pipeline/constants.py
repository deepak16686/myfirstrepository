"""
GitHub Actions Pipeline Generator Constants

Module-level constants for GitHub Actions workflow generation.
"""

FEEDBACK_COLLECTION = "github_actions_feedback"
TEMPLATES_COLLECTION = "github_actions_templates"
SUCCESSFUL_PIPELINES_COLLECTION = "github_actions_successful_pipelines"
DEFAULT_MODEL = "pipeline-generator-v5"

# Required jobs in the GitHub Actions workflow
REQUIRED_JOBS = [
    'compile', 'build-image', 'test-image', 'static-analysis',
    'sonarqube', 'trivy-scan', 'push-release', 'notify-success',
    'notify-failure', 'learn-record'
]

# Language -> correct compile/build image in Nexus (same as Jenkins/GitLab)
LANGUAGE_COMPILE_IMAGES = {
    "java": "maven:3.9-eclipse-temurin-17",
    "kotlin": "gradle:8.7-jdk17-alpine",
    "scala": "maven:3.9-eclipse-temurin-17",
    "spring-boot": "maven:3.9-eclipse-temurin-17",
    "quarkus": "maven:3.9-eclipse-temurin-17",
    "python": "python:3.11-slim",
    "django": "python:3.11-slim",
    "flask": "python:3.11-slim",
    "fastapi": "python:3.11-slim",
    "streamlit": "python:3.12-slim",
    "celery": "python:3.11-slim",
    "go": "golang:1.22-alpine",
    "golang": "golang:1.22-alpine",
    "rust": "rust:1.93-slim",
    "javascript": "node:20-alpine",
    "typescript": "node:20-alpine",
    "nodejs": "node:20-alpine",
    "node": "node:20-alpine",
    "ruby": "ruby:3.3-alpine",
    "php": "php:8.3-fpm-alpine",
    "csharp": "dotnet-aspnet:8.0-alpine",
    "dotnet": "dotnet-aspnet:8.0-alpine",
}

# Language -> correct Dockerfile base image in Nexus
LANGUAGE_DOCKERFILE_IMAGES = {
    "java": "maven:3.9-eclipse-temurin-17",
    "kotlin": "gradle:8.7-jdk17-alpine",
    "scala": "maven:3.9-eclipse-temurin-17",
    "python": "python:3.11-slim",
    "go": "golang:1.22-alpine",
    "golang": "golang:1.22-alpine",
    "rust": "rust:1.93-slim",
    "javascript": "node:20-alpine",
    "typescript": "node:20-alpine",
    "ruby": "ruby:3.3-alpine",
    "php": "php:8.3-fpm-alpine",
    "csharp": "dotnet-aspnet:8.0-alpine",
    "dotnet": "dotnet-aspnet:8.0-alpine",
}

# Language -> correct runtime image in Nexus
LANGUAGE_RUNTIME_IMAGES = {
    "java": "eclipse-temurin:17-jre",
    "kotlin": "eclipse-temurin:17-jre",
    "scala": "eclipse-temurin:17-jre",
    "python": "python:3.11-slim",
    "go": "alpine:3.18",
    "golang": "alpine:3.18",
    "rust": "alpine:3.18",
    "javascript": "nginx:alpine",
    "typescript": "nginx:alpine",
    "ruby": "ruby:3.3-alpine",
    "php": "php:8.3-fpm-alpine",
    "csharp": "dotnet-aspnet:8.0-alpine",
    "dotnet": "dotnet-aspnet:8.0-alpine",
}

# Language -> correct compile commands
LANGUAGE_COMPILE_COMMANDS = {
    "java": ["mvn clean package -DskipTests"],
    "kotlin": ["mvn clean package -DskipTests"],
    "scala": ["sbt assembly || sbt package"],
    "python": ["pip install -r requirements.txt"],
    "go": ["go build -o app ./..."],
    "golang": ["go build -o app ./..."],
    "rust": ["cargo build --release"],
    "javascript": ["npm install", "npm run build || true"],
    "typescript": ["npm install", "npm run build"],
    "ruby": ["bundle install"],
    "php": ["composer install --no-dev"],
}

# Language -> SAST tool commands
LANGUAGE_SAST_COMMANDS = {
    "java": "mvn spotbugs:check -DskipTests || true\nmvn pmd:check -DskipTests || true",
    "python": "pip install bandit pylint\nbandit -r . || true\npylint **/*.py || true",
    "javascript": "npm audit || true\nnpx eslint . || true",
    "typescript": "npm audit || true\nnpx eslint . || true",
    "go": "go vet ./... || true",
    "rust": "rustup component add clippy || true\ncargo clippy --all-targets -- -D warnings || true",
    "ruby": "gem install brakeman || true\nbrakeman --no-pager || true",
    "php": "vendor/bin/phpstan analyse || true",
    "scala": "sbt scalafmtCheck || true",
}
