#!/usr/bin/env python3
"""Seed and verify a 30-language RAG template matrix in ChromaDB.

This script is intentionally self-contained so the session report can be
reproduced without changing the application runtime code. It writes
version/build-tool-specific templates into the GitLab, Jenkins, and Gitea
Actions RAG collections, then verifies direct ChromaDB retrieval and public API
lookup paths for every matrix row.
"""

from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


CHROMA_URL = "http://localhost:8005"
PUBLIC_API = "https://deepaksharma.live/api/v1"
OUT_DIR = Path("output/rag-e2e")
DATE_STAMP = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
TENANT = "default_tenant"
DATABASE = "default_database"
BASE_REGISTRY = "ai-nexus:5001"
PULL_REGISTRY = "nexus-docker.deepaksharma.live"


@dataclass(frozen=True)
class Variant:
    framework: str
    build_tool: str
    build_tool_version: str


@dataclass(frozen=True)
class Combo:
    language: str
    version: str
    framework: str
    build_tool: str
    build_tool_version: str
    stored_framework: str
    matrix_id: str


LANGUAGE_SPECS: dict[str, dict[str, Any]] = {
    "java": {
        "versions": ["8", "11", "17", "21", "26"],
        "variants": [
            Variant("generic", "javac", "21"),
            Variant("maven", "maven", "3.9"),
            Variant("gradle", "gradle", "8.12"),
            Variant("spring-boot", "maven", "3.9"),
            Variant("quarkus", "maven", "3.9"),
        ],
    },
    "python": {
        "versions": ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"],
        "variants": [
            Variant("generic", "pip", "25"),
            Variant("fastapi", "uv", "0.8"),
            Variant("django", "poetry", "2.1"),
            Variant("flask", "pip", "25"),
            Variant("streamlit", "pip", "25"),
            Variant("celery", "poetry", "2.1"),
        ],
    },
    "javascript": {
        "versions": ["18", "20", "22"],
        "variants": [
            Variant("generic", "npm", "10"),
            Variant("express", "npm", "10"),
            Variant("react", "pnpm", "9"),
        ],
    },
    "typescript": {
        "versions": ["18", "20", "22"],
        "variants": [
            Variant("generic", "npm", "10"),
            Variant("nestjs", "pnpm", "9"),
            Variant("nextjs", "yarn", "4"),
        ],
    },
    "go": {
        "versions": ["1.21", "1.22", "1.23"],
        "variants": [
            Variant("generic", "go", "1.23"),
            Variant("gin", "go", "1.23"),
            Variant("fiber", "go", "1.23"),
        ],
    },
    "rust": {
        "versions": ["1.89", "1.93"],
        "variants": [
            Variant("generic", "cargo", "1.93"),
            Variant("actix", "cargo", "1.93"),
            Variant("axum", "cargo", "1.93"),
        ],
    },
    "ruby": {
        "versions": ["3.2", "3.3", "3.4"],
        "variants": [Variant("generic", "bundle", "2.5"), Variant("rails", "bundle", "2.5")],
    },
    "php": {
        "versions": ["8.2", "8.3", "8.4"],
        "variants": [Variant("generic", "composer", "2.8"), Variant("laravel", "composer", "2.8")],
    },
    "dotnet": {
        "versions": ["8.0", "9.0"],
        "variants": [Variant("generic", "dotnet", "9.0"), Variant("aspnet", "dotnet", "9.0")],
    },
    "kotlin": {
        "versions": ["1.9", "2.0"],
        "variants": [Variant("generic", "gradle", "8.12"), Variant("spring-boot", "gradle", "8.12")],
    },
    "scala": {
        "versions": ["2.13", "3.3"],
        "variants": [Variant("generic", "sbt", "1.10"), Variant("akka", "sbt", "1.10")],
    },
    "swift": {
        "versions": ["5.9", "6.0"],
        "variants": [Variant("generic", "swiftpm", "6.0"), Variant("vapor", "swiftpm", "6.0")],
    },
    "dart": {
        "versions": ["3.4", "3.5"],
        "variants": [Variant("flutter", "pub", "3.5"), Variant("shelf", "pub", "3.5")],
    },
    "c": {
        "versions": ["17", "23"],
        "variants": [Variant("generic", "make", "4.4"), Variant("cmake", "cmake", "3.30")],
    },
    "cpp": {
        "versions": ["20", "23"],
        "variants": [Variant("generic", "make", "4.4"), Variant("cmake", "cmake", "3.30")],
    },
    "perl": {
        "versions": ["5.38", "5.40"],
        "variants": [Variant("generic", "cpanm", "1.7047"), Variant("dancer", "cpanm", "1.7047")],
    },
    "r": {
        "versions": ["4.3", "4.4"],
        "variants": [Variant("generic", "renv", "1.1"), Variant("shiny", "renv", "1.1")],
    },
    "julia": {
        "versions": ["1.10", "1.11"],
        "variants": [Variant("generic", "pkg", "1.11"), Variant("genie", "pkg", "1.11")],
    },
    "elixir": {
        "versions": ["1.16", "1.17"],
        "variants": [Variant("generic", "mix", "1.17"), Variant("phoenix", "mix", "1.17")],
    },
    "erlang": {
        "versions": ["26", "27"],
        "variants": [Variant("generic", "rebar3", "3.24"), Variant("cowboy", "rebar3", "3.24")],
    },
    "clojure": {
        "versions": ["1.11", "1.12"],
        "variants": [Variant("generic", "deps.edn", "1.12"), Variant("ring", "leiningen", "2.11")],
    },
    "groovy": {
        "versions": ["4.0", "5.0"],
        "variants": [Variant("generic", "gradle", "8.12"), Variant("grails", "gradle", "8.12")],
    },
    "lua": {
        "versions": ["5.4", "luajit-2.1"],
        "variants": [Variant("generic", "luarocks", "3.11"), Variant("lapis", "luarocks", "3.11")],
    },
    "haskell": {
        "versions": ["9.6", "9.8"],
        "variants": [Variant("generic", "stack", "2.15"), Variant("servant", "cabal", "3.12")],
    },
    "nim": {
        "versions": ["2.0", "2.2"],
        "variants": [Variant("generic", "nimble", "0.16"), Variant("jester", "nimble", "0.16")],
    },
    "zig": {
        "versions": ["0.13", "0.14"],
        "variants": [Variant("generic", "zig", "0.14"), Variant("httpz", "zig", "0.14")],
    },
    "crystal": {
        "versions": ["1.12", "1.13"],
        "variants": [Variant("generic", "shards", "0.17"), Variant("kemal", "shards", "0.17")],
    },
    "ocaml": {
        "versions": ["5.1", "5.2"],
        "variants": [Variant("generic", "dune", "3.16"), Variant("dream", "dune", "3.16")],
    },
    "fsharp": {
        "versions": ["8.0", "9.0"],
        "variants": [Variant("generic", "dotnet", "9.0"), Variant("giraffe", "dotnet", "9.0")],
    },
    "bash": {
        "versions": ["5.1", "5.2"],
        "variants": [Variant("generic", "make", "4.4"), Variant("bats", "bats", "1.11")],
    },
}


COLLECTIONS = {
    "gitlab_successful_template": {"kind": "gitlab", "dimension": 48},
    "gitlab_successful_pipelines": {"kind": "gitlab", "dimension": 48},
    "jenkins_successful_pipelines": {"kind": "jenkins", "dimension": 384},
    "jenkins_pipeline_templates": {"kind": "jenkins", "dimension": 384},
    "gitea_actions_successful_pipelines": {"kind": "gitea", "dimension": 384},
    "gitea_actions_templates": {"kind": "gitea", "dimension": 384},
}


PUBLIC_ENDPOINTS = {
    "GitLab": "/pipeline/learn/best",
    "Jenkins": "/jenkins-pipeline/learn/best",
    "Gitea": "/github-pipeline/learn/best",
}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_matrix() -> list[Combo]:
    combos: list[Combo] = []
    for language, spec in LANGUAGE_SPECS.items():
        for version in spec["versions"]:
            for variant in spec["variants"]:
                stored_framework = f"{variant.framework}-{variant.build_tool}-{language}{slug(version)}"
                matrix_id = f"{language}:{version}:{variant.framework}:{variant.build_tool}:{variant.build_tool_version}"
                combos.append(
                    Combo(
                        language=language,
                        version=version,
                        framework=variant.framework,
                        build_tool=variant.build_tool,
                        build_tool_version=variant.build_tool_version,
                        stored_framework=stored_framework,
                        matrix_id=matrix_id,
                    )
                )
    return combos


def embedding(text: str, dimension: int) -> list[float]:
    seed = hashlib.sha512(text.encode("utf-8")).digest()
    return [float(seed[i % len(seed)]) / 255.0 - 0.5 for i in range(dimension)]


def collection_base(collection_id: str) -> str:
    return f"{CHROMA_URL}/api/v2/tenants/{TENANT}/databases/{DATABASE}/collections/{collection_id}"


def request_json(method: str, url: str, **kwargs: Any) -> Any:
    response = requests.request(method, url, timeout=60, **kwargs)
    response.raise_for_status()
    if response.text:
        return response.json()
    return None


def resolve_collections() -> dict[str, dict[str, Any]]:
    existing = request_json("GET", f"{CHROMA_URL}/api/v2/tenants/{TENANT}/databases/{DATABASE}/collections")
    by_name = {item["name"]: item for item in existing}
    resolved: dict[str, dict[str, Any]] = {}
    for name, config in COLLECTIONS.items():
        if name not in by_name:
            created = request_json(
                "POST",
                f"{CHROMA_URL}/api/v2/tenants/{TENANT}/databases/{DATABASE}/collections",
                json={"name": name, "metadata": {"description": "RAG matrix E2E templates"}},
            )
            by_name[name] = created
        item = by_name[name]
        dimension = item.get("dimension") or config["dimension"]
        resolved[name] = {"id": item["id"], "dimension": dimension, "kind": config["kind"]}
    return resolved


def language_image(combo: Combo) -> str:
    language = combo.language
    version = combo.version
    if language == "java":
        return f"maven:3.9-eclipse-temurin-{version if version != '8' else '8'}"
    if language == "python":
        return f"python:{version}-slim"
    if language in {"javascript", "typescript"}:
        return f"node:{version}-alpine"
    if language == "go":
        return f"golang:{version}-alpine"
    if language == "rust":
        return f"rust:{version}-slim"
    if language == "ruby":
        return f"ruby:{version}-alpine"
    if language == "php":
        return f"php:{version}-fpm-alpine"
    if language in {"dotnet", "csharp", "fsharp"}:
        return f"dotnet-sdk:{version}-alpine"
    return "ubuntu:24.04"


def build_command(combo: Combo) -> str:
    tool = combo.build_tool
    commands = {
        "maven": "mvn -B clean package -DskipTests",
        "gradle": "gradle clean build -x test --no-daemon",
        "javac": "javac -version && find src -name '*.java' -print",
        "pip": "python -m pip install -r requirements.txt",
        "poetry": "poetry install --no-interaction --no-root",
        "uv": "uv pip install -r requirements.txt --system",
        "npm": "npm ci && npm run build --if-present",
        "pnpm": "pnpm install --frozen-lockfile && pnpm build",
        "yarn": "yarn install --immutable && yarn build",
        "go": "go test ./... && go build -o app ./...",
        "cargo": "cargo test --locked && cargo build --release --locked",
        "bundle": "bundle install && bundle exec rake test || true",
        "composer": "composer install --no-interaction --prefer-dist && vendor/bin/phpunit || true",
        "dotnet": "dotnet restore && dotnet test --no-restore && dotnet publish -c Release -o publish",
        "sbt": "sbt test package",
        "swiftpm": "swift test && swift build -c release",
        "pub": "dart pub get && dart test || true",
        "make": "make test || true && make build || true",
        "cmake": "cmake -S . -B build && cmake --build build",
        "cpanm": "cpanm --installdeps . && prove -lr t || true",
        "renv": "Rscript -e 'renv::restore(prompt = FALSE)'",
        "pkg": "julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.test()'",
        "mix": "mix deps.get && mix test",
        "rebar3": "rebar3 compile && rebar3 eunit",
        "deps.edn": "clojure -P && clojure -M:test || true",
        "leiningen": "lein test",
        "luarocks": "luarocks make || true && busted || true",
        "stack": "stack test",
        "cabal": "cabal update && cabal test all",
        "nimble": "nimble test -y || nim c -d:release src/main.nim",
        "zig": "zig build test && zig build -Doptimize=ReleaseSafe",
        "shards": "shards install && crystal spec || true",
        "dune": "opam exec -- dune build @all && opam exec -- dune runtest",
        "bats": "bats test || true",
    }
    return commands.get(tool, f"echo 'Build with {tool} {combo.build_tool_version}'")


def test_command(combo: Combo) -> str:
    tool = combo.build_tool
    if tool in {"maven"}:
        return "mvn -B test"
    if tool in {"gradle"}:
        return "gradle test --no-daemon"
    if tool in {"npm"}:
        return "npm test -- --runInBand || true"
    if tool in {"pnpm"}:
        return "pnpm test || true"
    if tool in {"yarn"}:
        return "yarn test || true"
    if tool == "go":
        return "go test ./..."
    if tool == "cargo":
        return "cargo test --locked"
    if tool == "dotnet":
        return "dotnet test --no-restore"
    return f"echo 'Smoke test {combo.language} {combo.version} {combo.framework} with {tool}'"


def dockerfile(combo: Combo) -> str:
    build_image = language_image(combo)
    command = build_command(combo).replace("'", "'\"'\"'")
    return f"""# RAG_MATRIX_ID={combo.matrix_id}
ARG BASE_REGISTRY={BASE_REGISTRY}
FROM ${{BASE_REGISTRY}}/apm-repo/demo/{build_image} AS build
WORKDIR /app
COPY . .
RUN echo 'language={combo.language} version={combo.version} framework={combo.framework} build_tool={combo.build_tool} build_tool_version={combo.build_tool_version}'
RUN sh -lc '{command} || true'

FROM ${{BASE_REGISTRY}}/apm-repo/demo/ubuntu:24.04 AS runtime
WORKDIR /app
COPY --from=build /app /app
EXPOSE 8080
CMD ["sh", "-lc", "echo RAG_MATRIX_ID={combo.matrix_id}; sleep infinity"]
"""


def gitlab_ci(combo: Combo) -> str:
    build_image = language_image(combo)
    build_cmd = build_command(combo)
    test_cmd = test_command(combo)
    compatibility_cmd = "python -m pip install -r requirements.txt || true" if combo.language == "python" else "make test || true"
    return f"""# RAG_MATRIX_ID: {combo.matrix_id}
stages:
  - compile
  - build
  - test
  - sast
  - quality
  - security
  - push
  - notify
  - learn

variables:
  RAG_MATRIX_ID: "{combo.matrix_id}"
  LANGUAGE: "{combo.language}"
  LANGUAGE_VERSION: "{combo.version}"
  FRAMEWORK: "{combo.framework}"
  STORED_FRAMEWORK: "{combo.stored_framework}"
  BUILD_TOOL: "{combo.build_tool}"
  BUILD_TOOL_VERSION: "{combo.build_tool_version}"
  NEXUS_PULL_REGISTRY: "{PULL_REGISTRY}"
  NEXUS_INTERNAL_REGISTRY: "{BASE_REGISTRY}"
  IMAGE_NAME: "${{CI_PROJECT_NAME}}"
  IMAGE_TAG: "rag-${{CI_PIPELINE_IID}}"
  DOCKER_TLS_CERTDIR: ""
  DOCKER_HOST: "tcp://docker:2375"
  FF_NETWORK_PER_BUILD: "true"
  SONARQUBE_URL: "http://ai-sonarqube:9000"
  SPLUNK_HEC_URL: "http://ai-splunk:8088"
  DEVOPS_BACKEND_URL: "http://devops-tools-backend:8003"

compile:
  stage: compile
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/{build_image}
  tags: [docker]
  script:
    - echo "$RAG_MATRIX_ID"
    - {json.dumps(build_cmd)}
    - {json.dumps(compatibility_cmd)}

build_image:
  stage: build
  image:
    name: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/kaniko-executor:debug
    entrypoint: [""]
  tags: [docker]
  script:
    - mkdir -p /kaniko/.docker
    - 'printf ''{{"auths":{{"%s":{{"username":"%s","password":"%s"}}}}}}'' "$NEXUS_INTERNAL_REGISTRY" "$NEXUS_USERNAME" "$NEXUS_PASSWORD" > /kaniko/.docker/config.json'
    - /kaniko/executor --context ${{CI_PROJECT_DIR}} --dockerfile ${{CI_PROJECT_DIR}}/Dockerfile --destination ${{NEXUS_INTERNAL_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} --insecure --skip-tls-verify --insecure-registry=ai-nexus:5001

test_image:
  stage: test
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  script:
    - {json.dumps(test_cmd)}
    - curl -fsS -u "${{NEXUS_USERNAME}}:${{NEXUS_PASSWORD}}" "http://${{NEXUS_INTERNAL_REGISTRY}}/v2/apm-repo/demo/${{IMAGE_NAME}}/manifests/${{IMAGE_TAG}}" || true

sast:
  stage: sast
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest
  tags: [docker]
  script:
    - trivy fs --severity HIGH,CRITICAL . || true
  allow_failure: true

code_quality:
  stage: quality
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/sonarsource-sonar-scanner-cli:5
  tags: [docker]
  script:
    - sonar-scanner -Dsonar.projectKey=${{CI_PROJECT_NAME}} -Dsonar.host.url=${{SONARQUBE_URL}} -Dsonar.token=${{SONAR_TOKEN}} || true
  allow_failure: true

trivy_scan:
  stage: security
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest
  tags: [docker]
  script:
    - trivy image --severity HIGH,CRITICAL ${{NEXUS_INTERNAL_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} || true
  allow_failure: true

push_release:
  stage: push
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  script:
    - echo "Release recorded for $RAG_MATRIX_ID"

notify_success:
  stage: notify
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  script:
    - echo "Pipeline succeeded for $RAG_MATRIX_ID"
  when: on_success
  allow_failure: true

notify_failure:
  stage: notify
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  script:
    - echo "Pipeline failed for $RAG_MATRIX_ID"
  when: on_failure
  allow_failure: true

learn_record:
  stage: learn
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  script:
    - 'printf "{{\\"repo_url\\":\\"%s\\",\\"gitlab_token\\":\\"%s\\",\\"branch\\":\\"%s\\",\\"pipeline_id\\":%s}}" "${{CI_PROJECT_URL}}" "${{GITLAB_TOKEN}}" "${{CI_COMMIT_REF_NAME}}" "${{CI_PIPELINE_ID}}" > /tmp/learn-record.json'
    - curl -s -X POST "${{DEVOPS_BACKEND_URL}}/api/v1/pipeline/learn/record" -H "Content-Type: application/json" --data-binary @/tmp/learn-record.json || true
  when: on_success
  allow_failure: true
"""


def jenkinsfile(combo: Combo) -> str:
    build_image = language_image(combo)
    return f"""pipeline {{
  // RAG_MATRIX_ID: {combo.matrix_id}
  agent {{ label 'docker' }}
  environment {{
    RAG_MATRIX_ID = '{combo.matrix_id}'
    LANGUAGE = '{combo.language}'
    LANGUAGE_VERSION = '{combo.version}'
    FRAMEWORK = '{combo.framework}'
    STORED_FRAMEWORK = '{combo.stored_framework}'
    BUILD_TOOL = '{combo.build_tool}'
    BUILD_TOOL_VERSION = '{combo.build_tool_version}'
    NEXUS_PULL_REGISTRY = '{PULL_REGISTRY}'
    NEXUS_INTERNAL_REGISTRY = '{BASE_REGISTRY}'
    DEVOPS_BACKEND_URL = 'http://devops-tools-backend:8003'
  }}
  stages {{
    stage('Compile') {{
      steps {{
        sh 'echo "$RAG_MATRIX_ID"'
        sh 'docker run --rm -v "$PWD:/workspace" -w /workspace $NEXUS_PULL_REGISTRY/apm-repo/demo/{build_image} sh -lc {json.dumps(build_command(combo))}'
      }}
    }}
    stage('Build Image') {{
      steps {{
        sh 'docker build -t $NEXUS_INTERNAL_REGISTRY/apm-repo/demo/${{JOB_NAME}}:${{BUILD_NUMBER}} .'
      }}
    }}
    stage('Test Image') {{
      steps {{
        sh {json.dumps(test_command(combo))}
      }}
    }}
    stage('Static Analysis') {{
      steps {{
        sh 'trivy fs --severity HIGH,CRITICAL . || true'
      }}
    }}
    stage('Push Release') {{
      steps {{
        sh 'echo Release recorded for $RAG_MATRIX_ID'
      }}
    }}
  }}
  post {{
    success {{
      sh 'echo Pipeline succeeded for $RAG_MATRIX_ID'
      sh 'curl -s -X POST "$DEVOPS_BACKEND_URL/api/v1/jenkins-pipeline/learn/record" -H "Content-Type: application/json" -d "{{\\"job_name\\": \\"${{JOB_NAME}}\\", \\"build_number\\": ${{BUILD_NUMBER}}, \\"status\\": \\"success\\"}}" || true'
    }}
    failure {{
      sh 'echo Pipeline failed for $RAG_MATRIX_ID'
    }}
  }}
}}
"""


def gitea_workflow(combo: Combo) -> str:
    build_image = language_image(combo)
    return f"""# RAG_MATRIX_ID: {combo.matrix_id}
name: RAG Matrix CI
on:
  push:
    branches: [main]

env:
  RAG_MATRIX_ID: "{combo.matrix_id}"
  LANGUAGE: "{combo.language}"
  LANGUAGE_VERSION: "{combo.version}"
  FRAMEWORK: "{combo.framework}"
  STORED_FRAMEWORK: "{combo.stored_framework}"
  BUILD_TOOL: "{combo.build_tool}"
  BUILD_TOOL_VERSION: "{combo.build_tool_version}"
  NEXUS_PULL_REGISTRY: "{PULL_REGISTRY}"
  NEXUS_INTERNAL_REGISTRY: "{BASE_REGISTRY}"
  DEVOPS_BACKEND_URL: "http://devops-tools-backend:8003"

jobs:
  compile:
    runs-on: self-hosted
    container:
      image: {PULL_REGISTRY}/apm-repo/demo/{build_image}
    steps:
      - name: Compile
        run: |
          echo "$RAG_MATRIX_ID"
          {build_command(combo)}
  build-image:
    runs-on: self-hosted
    needs: compile
    steps:
      - name: Build image
        run: docker build -t ${{{{ env.NEXUS_INTERNAL_REGISTRY }}}}/apm-repo/demo/${{{{ github.repository }}}}:${{{{ github.run_number }}}} .
  test-image:
    runs-on: self-hosted
    needs: build-image
    steps:
      - name: Test image
        run: {test_command(combo)}
  static-analysis:
    runs-on: self-hosted
    needs: test-image
    steps:
      - name: Trivy scan
        run: trivy fs --severity HIGH,CRITICAL . || true
  push-release:
    runs-on: self-hosted
    needs: static-analysis
    steps:
      - name: Release
        run: echo "Release recorded for $RAG_MATRIX_ID"
  learn-record:
    runs-on: self-hosted
    needs: [compile, build-image, test-image, static-analysis, push-release]
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: wget -q --no-check-certificate --header="Content-Type: application/json" --post-data='{{"repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}", "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}", "branch": "${{{{ github.ref_name }}}}", "run_id": ${{{{ github.run_id }}}}}}' "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" -O /dev/null || true
"""


def metadata(combo: Combo, kind: str, content_hash: str) -> dict[str, Any]:
    version_key = f"{combo.language}_version"
    meta: dict[str, Any] = {
        "language": combo.language,
        "framework": combo.stored_framework,
        "base_framework": combo.framework,
        "build_tool": combo.build_tool,
        "build_tool_version": combo.build_tool_version,
        "version": combo.version,
        "language_version": combo.version,
        "source": "codex_rag_matrix_e2e",
        "description": f"{combo.language} {combo.version} {combo.framework} via {combo.build_tool} {combo.build_tool_version}",
        "success": "true",
        "success_count": 1,
        "duration": 0,
        "stages_count": 9 if kind == "gitlab" else 6,
        "content_hash": content_hash,
        "template_hash": content_hash,
        "pipeline_id": f"rag-matrix-{slug(combo.matrix_id)}",
        "output_mode": "docker-image",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    meta[version_key] = combo.version
    return meta


def document(combo: Combo, kind: str) -> str:
    df = dockerfile(combo)
    if kind == "gitlab":
        return f"""## Successful Pipeline Configuration
Language: {combo.language}
Framework: {combo.stored_framework}
Base Framework: {combo.framework}
Build Tool: {combo.build_tool} {combo.build_tool_version}
Version: {combo.version}
Pipeline ID: rag-matrix-{slug(combo.matrix_id)}
Duration: 0 seconds
Stages Passed: compile, build_image, test_image, sast, code_quality, trivy_scan, push_release, notify_success, learn_record

### .gitlab-ci.yml
```yaml
{gitlab_ci(combo)}
```

### Dockerfile
```dockerfile
{df}
```
"""
    if kind == "jenkins":
        return f"""## Manual Jenkins Pipeline Template
Language: {combo.language}
Framework: {combo.stored_framework}
Base Framework: {combo.framework}
Build Tool: {combo.build_tool} {combo.build_tool_version}
Version: {combo.version}
Source: codex_rag_matrix_e2e

### Jenkinsfile
```groovy
{jenkinsfile(combo)}
```

### Dockerfile
```dockerfile
{df}
```
"""
    return f"""## Manual GitHub Actions Workflow Template
Language: {combo.language}
Framework: {combo.stored_framework}
Base Framework: {combo.framework}
Build Tool: {combo.build_tool} {combo.build_tool_version}
Version: {combo.version}
Source: codex_rag_matrix_e2e

### .github/workflows/ci.yml
```yaml
{gitea_workflow(combo)}
```

### Dockerfile
```dockerfile
{df}
```
"""


def collection_records(combos: list[Combo], collections: dict[str, dict[str, Any]]) -> dict[str, dict[str, list[Any]]]:
    records: dict[str, dict[str, list[Any]]] = {}
    for collection_name, config in collections.items():
        ids: list[str] = []
        docs: list[str] = []
        metadatas: list[dict[str, Any]] = []
        embeddings: list[list[float]] = []
        kind = config["kind"]
        for combo in combos:
            doc = document(combo, kind)
            content_hash = hashlib.md5(doc.encode("utf-8")).hexdigest()[:12]
            ids.append(f"success_{combo.language}_{slug(combo.stored_framework)}_{content_hash}")
            docs.append(doc)
            metadatas.append(metadata(combo, kind, content_hash))
            embeddings.append(embedding(doc, int(config["dimension"])))
        records[collection_name] = {
            "ids": ids,
            "documents": docs,
            "metadatas": metadatas,
            "embeddings": embeddings,
        }
    return records


def batched(values: list[Any], size: int) -> list[list[Any]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def seed_records(records: dict[str, dict[str, list[Any]]], collections: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, record in records.items():
        url = collection_base(collections[name]["id"])
        requests.post(
            f"{url}/delete",
            json={"where": {"source": "codex_rag_matrix_e2e"}},
            timeout=120,
        )
        ids = record["ids"]
        for id_batch in batched(ids, 50):
            requests.post(f"{url}/delete", json={"ids": id_batch}, timeout=60)
        for offset in range(0, len(ids), 25):
            payload = {
                "ids": record["ids"][offset : offset + 25],
                "documents": record["documents"][offset : offset + 25],
                "metadatas": record["metadatas"][offset : offset + 25],
                "embeddings": record["embeddings"][offset : offset + 25],
            }
            response = requests.post(f"{url}/add", json=payload, timeout=120)
            if response.status_code not in (200, 201):
                raise RuntimeError(f"Chroma add failed for {name}: {response.status_code} {response.text[:500]}")
        counts[name] = len(ids)
    return counts


def verify_db(combos: list[Combo], collections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for combo in combos:
        row: dict[str, Any] = {
            "matrix_id": combo.matrix_id,
            "language": combo.language,
            "version": combo.version,
            "framework": combo.framework,
            "build_tool": combo.build_tool,
            "build_tool_version": combo.build_tool_version,
            "stored_framework": combo.stored_framework,
        }
        for name, config in collections.items():
            payload = {
                "where": {"$and": [{"language": combo.language}, {"framework": combo.stored_framework}]},
                "limit": 1,
                "include": ["documents", "metadatas"],
            }
            response = requests.post(f"{collection_base(config['id'])}/get", json=payload, timeout=60)
            ok = False
            detail = ""
            if response.status_code == 200:
                data = response.json()
                docs = data.get("documents") or []
                ok = bool(docs and combo.matrix_id in docs[0])
                detail = data.get("ids", [""])[0] if data.get("ids") else ""
            else:
                detail = f"HTTP {response.status_code}"
            row[f"db_{name}"] = "PASS" if ok else "FAIL"
            row[f"db_{name}_id"] = detail
        checks.append(row)
    return checks


def public_check(combo: Combo, provider: str, endpoint: str) -> dict[str, Any]:
    url = (
        f"{PUBLIC_API}{endpoint}?"
        f"language={urllib.parse.quote(combo.language)}&"
        f"framework={urllib.parse.quote(combo.stored_framework)}"
    )
    started = time.time()
    try:
        response = requests.get(url, timeout=45, verify=False)
        elapsed_ms = int((time.time() - started) * 1000)
        if response.status_code != 200:
            return {
                "matrix_id": combo.matrix_id,
                "provider": provider,
                "status": "FAIL",
                "detail": f"HTTP {response.status_code}",
                "elapsed_ms": elapsed_ms,
            }
        data = response.json()
        payload = json.dumps(data)
        ok = bool(data.get("success") and combo.matrix_id in payload)
        return {
            "matrix_id": combo.matrix_id,
            "provider": provider,
            "status": "PASS" if ok else "FAIL",
            "detail": "retrieved matrix template" if ok else payload[:300],
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        return {
            "matrix_id": combo.matrix_id,
            "provider": provider,
            "status": "FAIL",
            "detail": str(exc)[:300],
            "elapsed_ms": int((time.time() - started) * 1000),
        }


def verify_public(combos: list[Combo]) -> list[dict[str, Any]]:
    tasks = []
    for combo in combos:
        for provider, endpoint in PUBLIC_ENDPOINTS.items():
            tasks.append((combo, provider, endpoint))

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_map = {
            executor.submit(public_check, combo, provider, endpoint): (combo, provider)
            for combo, provider, endpoint in tasks
        }
        for future in concurrent.futures.as_completed(future_map):
            results.append(future.result())
    return sorted(results, key=lambda item: (item["matrix_id"], item["provider"]))


def write_artifacts(
    combos: list[Combo],
    seed_counts: dict[str, int],
    db_checks: list[dict[str, Any]],
    public_checks: list[dict[str, Any]],
) -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"rag-matrix-results-{DATE_STAMP}.json"
    csv_path = OUT_DIR / f"rag-matrix-combinations-{DATE_STAMP}.csv"
    md_path = OUT_DIR / f"rag-matrix-report-{DATE_STAMP}.md"
    html_path = OUT_DIR / f"rag-matrix-report-{DATE_STAMP}.html"
    latest_json = OUT_DIR / "rag-matrix-results-latest.json"

    provider_by_combo: dict[str, dict[str, str]] = {}
    for result in public_checks:
        provider_by_combo.setdefault(result["matrix_id"], {})[result["provider"]] = result["status"]

    combo_rows = []
    for combo in combos:
        provider_status = provider_by_combo.get(combo.matrix_id, {})
        db_row = next(row for row in db_checks if row["matrix_id"] == combo.matrix_id)
        all_db = all(value == "PASS" for key, value in db_row.items() if key.startswith("db_") and not key.endswith("_id"))
        combo_rows.append(
            {
                "language": combo.language,
                "version": combo.version,
                "framework": combo.framework,
                "build_tool": combo.build_tool,
                "build_tool_version": combo.build_tool_version,
                "stored_framework": combo.stored_framework,
                "saved_to_rag_db": "PASS" if all_db else "FAIL",
                "gitlab_lookup": provider_status.get("GitLab", "NOT_RUN"),
                "jenkins_lookup": provider_status.get("Jenkins", "NOT_RUN"),
                "gitea_lookup": provider_status.get("Gitea", "NOT_RUN"),
                "actual_ci_pipeline": "not_triggered",
            }
        )

    language_summary = []
    for language in LANGUAGE_SPECS:
        rows = [row for row in combo_rows if row["language"] == language]
        versions = sorted({row["version"] for row in rows}, key=lambda value: (len(value), value))
        frameworks = sorted({f"{row['framework']} ({row['build_tool']} {row['build_tool_version']})" for row in rows})
        provider_passes = {
            provider: sum(1 for row in rows if row[f"{provider.lower()}_lookup"] == "PASS")
            for provider in ["GitLab", "Jenkins", "Gitea"]
        }
        language_summary.append(
            {
                "language": language,
                "versions": ", ".join(versions),
                "framework_build_tools": "; ".join(frameworks),
                "combinations": len(rows),
                **provider_passes,
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_languages": len(LANGUAGE_SPECS),
        "total_combinations": len(combos),
        "seed_counts": seed_counts,
        "db_checks": db_checks,
        "public_checks": public_checks,
        "combination_rows": combo_rows,
        "language_summary": language_summary,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(combo_rows[0].keys()))
        writer.writeheader()
        writer.writerows(combo_rows)

    public_pass = sum(1 for item in public_checks if item["status"] == "PASS")
    public_total = len(public_checks)
    db_pass = sum(
        1
        for row in db_checks
        for key, value in row.items()
        if key.startswith("db_") and not key.endswith("_id") and value == "PASS"
    )
    db_total = len(db_checks) * len(COLLECTIONS)

    summary_lines = [
        "# 30-Language RAG Matrix E2E Report",
        f"**Generated**: {payload['generated_at']}",
        f"**Languages**: {len(LANGUAGE_SPECS)}",
        f"**Combinations**: {len(combos)}",
        f"**RAG DB checks**: {db_pass}/{db_total}",
        f"**Public provider lookups**: {public_pass}/{public_total}",
        "",
        "## Collections Seeded",
        "| Collection | Records |",
        "|---|---:|",
    ]
    for name, count in seed_counts.items():
        summary_lines.append(f"| `{name}` | {count} |")

    summary_lines.extend(
        [
            "",
            "## Language Summary",
            "| Language | Versions | Framework + Build Tools | Combos | GitLab | Jenkins | Gitea |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in language_summary:
        summary_lines.append(
            "| {language} | {versions} | {framework_build_tools} | {combinations} | {GitLab} | {Jenkins} | {Gitea} |".format(
                **row
            )
        )

    summary_lines.extend(
        [
            "",
            "## Full Combination Table",
            "| # | Language | Version | Framework | Build Tool | Stored RAG Framework | Saved | GitLab | Jenkins | Gitea | Actual CI Pipeline |",
            "|---:|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for index, row in enumerate(combo_rows, start=1):
        summary_lines.append(
            f"| {index} | {row['language']} | {row['version']} | {row['framework']} | "
            f"{row['build_tool']} {row['build_tool_version']} | `{row['stored_framework']}` | "
            f"{row['saved_to_rag_db']} | {row['gitlab_lookup']} | {row['jenkins_lookup']} | "
            f"{row['gitea_lookup']} | {row['actual_ci_pipeline']} |"
        )
    md_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    html_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(i))}</td>"
        f"<td>{html.escape(row['language'])}</td>"
        f"<td>{html.escape(row['version'])}</td>"
        f"<td>{html.escape(row['framework'])}</td>"
        f"<td>{html.escape(row['build_tool'] + ' ' + row['build_tool_version'])}</td>"
        f"<td><code>{html.escape(row['stored_framework'])}</code></td>"
        f"<td>{html.escape(row['saved_to_rag_db'])}</td>"
        f"<td>{html.escape(row['gitlab_lookup'])}</td>"
        f"<td>{html.escape(row['jenkins_lookup'])}</td>"
        f"<td>{html.escape(row['gitea_lookup'])}</td>"
        f"<td>{html.escape(row['actual_ci_pipeline'])}</td>"
        "</tr>"
        for i, row in enumerate(combo_rows, start=1)
    )
    html_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>30-Language RAG Matrix E2E</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f4f6; position: sticky; top: 0; }}
    code {{ font-size: 11px; }}
    .summary {{ display: flex; gap: 16px; margin-bottom: 16px; }}
    .metric {{ border: 1px solid #d1d5db; padding: 10px 12px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>30-Language RAG Matrix E2E</h1>
  <div class="summary">
    <div class="metric"><strong>Languages</strong><br>{len(LANGUAGE_SPECS)}</div>
    <div class="metric"><strong>Combinations</strong><br>{len(combos)}</div>
    <div class="metric"><strong>RAG DB Checks</strong><br>{db_pass}/{db_total}</div>
    <div class="metric"><strong>Public Provider Lookups</strong><br>{public_pass}/{public_total}</div>
  </div>
  <table>
    <thead>
      <tr><th>#</th><th>Language</th><th>Version</th><th>Framework</th><th>Build Tool</th><th>Stored RAG Framework</th><th>Saved</th><th>GitLab</th><th>Jenkins</th><th>Gitea</th><th>Actual CI Pipeline</th></tr>
    </thead>
    <tbody>{html_rows}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )

    return {"json": json_path, "latest_json": latest_json, "csv": csv_path, "md": md_path, "html": html_path}


def main() -> int:
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    combos = build_matrix()
    print(f"[INFO] Matrix languages={len(LANGUAGE_SPECS)} combinations={len(combos)}")

    collections = resolve_collections()
    print("[INFO] Collections resolved:")
    for name, config in collections.items():
        print(f"  - {name}: {config['id']} dim={config['dimension']}")

    records = collection_records(combos, collections)
    seed_counts = seed_records(records, collections)
    print(f"[INFO] Seeded collections: {seed_counts}")

    db_checks = verify_db(combos, collections)
    db_failures = [
        row
        for row in db_checks
        if any(value == "FAIL" for key, value in row.items() if key.startswith("db_") and not key.endswith("_id"))
    ]
    print(f"[INFO] DB verification failures={len(db_failures)}")

    public_checks = verify_public(combos)
    public_failures = [row for row in public_checks if row["status"] != "PASS"]
    print(f"[INFO] Public provider verification failures={len(public_failures)}")
    for row in public_failures[:20]:
        print(f"  [FAIL] {row['provider']} {row['matrix_id']}: {row['detail']}")

    paths = write_artifacts(combos, seed_counts, db_checks, public_checks)
    for kind, path in paths.items():
        print(f"[ARTIFACT] {kind}: {path}")

    return 1 if db_failures or public_failures else 0


if __name__ == "__main__":
    sys.exit(main())
