"""
Pipeline Generator Constants

Module-level constants extracted from PipelineGeneratorService class.
"""

FEEDBACK_COLLECTION = "gitlab_successful_template"
TEMPLATES_COLLECTION = "Generic_template"
SUCCESSFUL_PIPELINES_COLLECTION = "gitlab_successful_template"  # Verified RL templates only
GENERIC_TEMPLATE_COLLECTION = "Generic_template"  # Generic stage reference for LLM fallback
DEFAULT_MODEL = "pipeline-generator-v5"  # Custom model with auto-commit workflow + Nexus rules

# Language -> correct compile/build image in Nexus
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
    "elixir": "hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1",
    "phoenix": "hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1",
    "rust": "rust:1.93-slim",
    "javascript": "node:20-alpine",
    "typescript": "node:20-alpine",
    "nodejs": "node:20-alpine",
    "node": "node:20-alpine",
    "ruby": "ruby:3.3-alpine",
    "php": "php:8.3-fpm-alpine",
    "csharp": "dotnet-aspnet:8.0-alpine",
    "dotnet": "dotnet-aspnet:8.0-alpine",
    "perl": "perl:5.32-slim",
}

# Language -> correct Dockerfile base image in Nexus
LANGUAGE_DOCKERFILE_IMAGES = {
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
    "elixir": "hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1",
    "phoenix": "hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1",
    "rust": "rust:1.93-slim",
    "javascript": "node:20-alpine",
    "typescript": "node:20-alpine",
    "nodejs": "node:20-alpine",
    "node": "node:20-alpine",
    "ruby": "ruby:3.3-alpine",
    "php": "php:8.3-fpm-alpine",
    "csharp": "dotnet-aspnet:8.0-alpine",
    "dotnet": "dotnet-aspnet:8.0-alpine",
    "perl": "perl:5.32-slim",
}

# Language -> correct runtime image in Nexus (for Dockerfile FROM runtime stage)
LANGUAGE_RUNTIME_IMAGES = {
    "java": "eclipse-temurin:17-jre",
    "kotlin": "eclipse-temurin:17-jre",
    "scala": "eclipse-temurin:17-jre",
    "spring-boot": "eclipse-temurin:17-jre",
    "quarkus": "eclipse-temurin:17-jre",
    "python": "python:3.11-slim",
    "django": "python:3.11-slim",
    "flask": "python:3.11-slim",
    "fastapi": "python:3.11-slim",
    "streamlit": "python:3.12-slim",
    "celery": "python:3.11-slim",
    "go": "alpine:3.18",
    "golang": "alpine:3.18",
    "elixir": "alpine:3.18",
    "phoenix": "alpine:3.18",
    "rust": "alpine:3.18",
    "javascript": "nginx:alpine",
    "typescript": "nginx:alpine",
    "nodejs": "node:20-alpine",
    "node": "node:20-alpine",
    "ruby": "ruby:3.3-alpine",
    "php": "php:8.3-fpm-alpine",
    "csharp": "dotnet-aspnet:8.0-alpine",
    "dotnet": "dotnet-aspnet:8.0-alpine",
    "perl": "perl:5.32-slim",
}

# Language -> correct compile commands
LANGUAGE_COMPILE_COMMANDS = {
    "java": ["mvn clean package -DskipTests"],
    "kotlin": ["gradle build -x test || ./gradlew build -x test"],
    "scala": ["sbt assembly || sbt package"],
    "python": ["pip install -r requirements.txt"],
    "django": ["pip install -r requirements.txt", "python manage.py collectstatic --noinput || true"],
    "flask": ["pip install -r requirements.txt"],
    "fastapi": ["pip install -r requirements.txt"],
    "streamlit": ["pip install -r requirements.txt"],
    "celery": ["pip install -r requirements.txt"],
    "go": ["go build -o app ./..."],
    "golang": ["go build -o app ./..."],
    "elixir": [
        "mix local.hex --force",
        "mix local.rebar --force",
        "mix deps.get --only ${MIX_ENV:-prod}",
        "mix deps.compile",
        "mix compile",
    ],
    "phoenix": [
        "mix local.hex --force",
        "mix local.rebar --force",
        "mix deps.get --only ${MIX_ENV:-prod}",
        "mix deps.compile",
        "mix compile",
    ],
    "rust": ["cargo build --release"],
    "javascript": ["npm install", "npm run build || true"],
    "typescript": ["npm install", "npm run build"],
    "nodejs": ["npm install", "npm run build || true"],
    "node": ["npm install", "npm run build || true"],
    "ruby": ["bundle install"],
    "php": ["composer install --no-dev"],
    "perl": [
        '[ -f Makefile.PL ] && perl Makefile.PL && make || echo "no Makefile.PL"'
    ],
}
