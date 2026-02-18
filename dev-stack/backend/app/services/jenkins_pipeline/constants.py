"""
File: constants.py
Purpose: Centralizes all module-level constants for the Jenkins pipeline generator, including
    ChromaDB collection names, the default LLM model, and language-to-image/command mappings
    for compile images, Dockerfile base images, runtime images, compile commands, and SAST tools.
When Used: Imported by nearly every other module in the package (generator, templates, validator,
    learning, image_seeder) whenever they need to look up the correct Docker image, compile
    command, or ChromaDB collection name for a given language.
Why Created: Consolidated scattered magic strings and lookup dictionaries into a single source
    of truth, making it easy to add new language support or update image versions in one place
    without modifying multiple files.
"""

FEEDBACK_COLLECTION = "jenkins_pipeline_feedback"
TEMPLATES_COLLECTION = "jenkins_pipeline_templates"
SUCCESSFUL_PIPELINES_COLLECTION = "jenkins_successful_pipelines"
DEFAULT_MODEL = "pipeline-generator-v5"

# Language -> correct compile/build image in Nexus (same as GitLab)
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

# Language -> SAST tool commands for Jenkins
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
