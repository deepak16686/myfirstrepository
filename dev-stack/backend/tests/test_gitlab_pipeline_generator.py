import asyncio
import unittest
from types import SimpleNamespace

from app.services.gitlab_dry_run_validator import GitLabDryRunValidator
from app.services.chat_service import ChatService
from app.services.pipeline.analyzer import parse_gitlab_url
from app.services.pipeline.default_templates import (
    _get_default_dockerfile,
    _get_default_gitlab_ci,
)
from app.services.pipeline.generator import PipelineGeneratorService
from app.services.pipeline.templates import _document_has_dockerfile, _infer_output_mode
from app.services.pipeline.validator import _ensure_learn_stage, validate_and_fix_pipeline_images
from app.services.shared.deep_analyzer import resolve_compile_image


class ParseGitLabUrlTests(unittest.TestCase):
    def test_custom_domain_with_gitlab_relative_root(self):
        parsed = parse_gitlab_url(
            "https://gitlab.deepaksharma.live/gitlab/ai-pipeline-projects/java-springboot-api"
        )

        self.assertEqual(parsed["host"], "https://gitlab.deepaksharma.live/gitlab")
        self.assertEqual(parsed["path"], "ai-pipeline-projects/java-springboot-api")
        self.assertEqual(
            parsed["project_path"],
            "ai-pipeline-projects%2Fjava-springboot-api",
        )

    def test_localhost_url_without_relative_root(self):
        parsed = parse_gitlab_url("http://localhost:8929/root/sample-repo")

        self.assertEqual(parsed["host"], "http://localhost:8929")
        self.assertEqual(parsed["path"], "root/sample-repo")
        self.assertEqual(parsed["project_path"], "root%2Fsample-repo")

    def test_ssh_url(self):
        parsed = parse_gitlab_url("git@gitlab.deepaksharma.live:team/backend-service.git")

        self.assertEqual(parsed["host"], "https://gitlab.deepaksharma.live")
        self.assertEqual(parsed["path"], "team/backend-service")
        self.assertEqual(parsed["project_path"], "team%2Fbackend-service")


class DefaultJavaTemplateTests(unittest.TestCase):
    def setUp(self):
        self.analysis = {"language": "java", "framework": "spring"}
        self.gitlab_ci = _get_default_gitlab_ci(self.analysis)
        self.dockerfile = _get_default_dockerfile(self.analysis)

    def test_java_template_contains_required_release_flow_stages(self):
        for stage in (
            "compile",
            "build",
            "test",
            "sast",
            "quality",
            "security",
            "push",
            "notify",
            "learn",
        ):
            self.assertIn(f"- {stage}", self.gitlab_ci)

    def test_java_template_uses_private_registry_variables(self):
        self.assertIn('NEXUS_PULL_REGISTRY: "localhost:5001"', self.gitlab_ci)
        self.assertIn('NEXUS_INTERNAL_REGISTRY: "ai-nexus:5001"', self.gitlab_ci)
        self.assertIn("${NEXUS_PULL_REGISTRY}/apm-repo/demo/maven:3.9-eclipse-temurin-17", self.gitlab_ci)
        self.assertIn("${NEXUS_PULL_REGISTRY}/apm-repo/demo/kaniko-executor:debug", self.gitlab_ci)

    def test_java_dockerfile_is_multi_stage_and_nexus_based(self):
        self.assertIn("ARG BASE_REGISTRY=ai-nexus:5001", self.dockerfile)
        self.assertIn("FROM ${BASE_REGISTRY}/apm-repo/demo/maven:3.9-eclipse-temurin-17 AS builder", self.dockerfile)
        self.assertIn("FROM ${BASE_REGISTRY}/apm-repo/demo/amazoncorretto:17-alpine-jdk", self.dockerfile)
        self.assertIn('ENTRYPOINT ["java", "-jar", "app.jar"]', self.dockerfile)

    def test_ensure_learn_stage_is_idempotent_for_default_template(self):
        ensured = _ensure_learn_stage(self.gitlab_ci)
        self.assertEqual(self.gitlab_ci, ensured)

    def test_ensure_learn_stage_adds_missing_job_and_variable(self):
        pipeline_without_learning = """stages:
  - compile
  - build
  - test
  - sast
  - quality
  - security
  - push
  - notify

variables:
  SPLUNK_HEC_URL: "http://ai-splunk:8088"
"""

        ensured = _ensure_learn_stage(pipeline_without_learning)

        self.assertIn("- learn", ensured)
        self.assertIn('DEVOPS_BACKEND_URL: "http://devops-tools-backend:8003"', ensured)
        self.assertIn("learn_record:", ensured)
        self.assertIn("/api/v1/pipeline/learn/record", ensured)


class GitLabDryRunValidatorTests(unittest.TestCase):
    def setUp(self):
        analysis = {"language": "java", "framework": "spring"}
        self.gitlab_ci = _get_default_gitlab_ci(analysis)
        self.dockerfile = _get_default_dockerfile(analysis)
        self.validator = GitLabDryRunValidator()

    def test_default_java_pipeline_structure_is_valid(self):
        result = self.validator.validate_pipeline_structure(self.gitlab_ci)

        self.assertTrue(result.valid)
        self.assertEqual(result.errors, [])

    def test_default_java_pipeline_has_valid_stage_dependencies(self):
        result = self.validator.validate_stage_dependencies(self.gitlab_ci)

        self.assertTrue(result.valid)
        self.assertEqual(result.errors, [])

    def test_default_java_pipeline_uses_nexus_only(self):
        result = self.validator.validate_nexus_images(self.gitlab_ci, self.dockerfile)

        self.assertTrue(result.valid)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])

    def test_public_registry_warning_is_reported(self):
        bad_dockerfile = "FROM docker.io/library/node:20-alpine\nCMD [\"node\", \"server.js\"]\n"

        result = self.validator.validate_nexus_images(self.gitlab_ci, bad_dockerfile)

        self.assertTrue(result.valid)
        self.assertTrue(
            any("public registry 'docker.io'" in warning for warning in result.warnings)
        )


class PipelineImageResolutionTests(unittest.TestCase):
    def test_java17_gradle_resolves_to_gradle_jdk17_image(self):
        image = resolve_compile_image({
            "language": "java",
            "build_tool": "gradle",
            "java_version": "17",
        })

        self.assertEqual(image, "gradle:8.12-jdk17")

    def test_gradle_project_rejects_apk_installed_gradle_image(self):
        gitlab_ci = """stages:
  - compile

compile:
  stage: compile
  image: ${NEXUS_PULL_REGISTRY}/apm-repo/demo/amazoncorretto:17-alpine-jdk
  tags: [docker]
  script:
    - apk add --no-cache gradle
    - if [ -f ./gradlew ]; then chmod +x ./gradlew && ./gradlew clean build -x test --no-daemon; else gradle clean build -x test --no-daemon; fi
"""
        dockerfile = """ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/amazoncorretto:17-alpine-jdk AS build
WORKDIR /app
RUN apk add --no-cache gradle
COPY build.gradle settings.gradle gradle.properties* ./
COPY gradle/ gradle/
COPY gradlew* ./
RUN if [ -f ./gradlew ]; then chmod +x ./gradlew && ./gradlew clean build -x test --no-daemon; else gradle clean build -x test --no-daemon; fi
FROM ${BASE_REGISTRY}/apm-repo/demo/eclipse-temurin:17-jre
CMD ["java", "-jar", "app.jar"]
"""
        analysis = {
            "language": "java",
            "build_tool": "gradle",
            "java_version": "17",
            "resolved_compile_image": "gradle:8.12-jdk17",
            "resolved_runtime_image": "eclipse-temurin:17-jre",
            "files": ["build.gradle", "settings.gradle"],
            "all_paths": ["build.gradle", "settings.gradle", "src/main/java/App.java"],
        }

        fixed_ci, fixed_dockerfile, corrections = validate_and_fix_pipeline_images(
            gitlab_ci, dockerfile, "java", analysis
        )

        self.assertIn("${NEXUS_PULL_REGISTRY}/apm-repo/demo/gradle:8.12-jdk17", fixed_ci)
        self.assertNotIn("apk add --no-cache gradle", fixed_ci)
        self.assertIn("FROM ${BASE_REGISTRY}/apm-repo/demo/gradle:8.12-jdk17 AS build", fixed_dockerfile)
        self.assertIn("FROM ${BASE_REGISTRY}/apm-repo/demo/eclipse-temurin:17-jre", fixed_dockerfile)
        self.assertNotIn("apk add --no-cache gradle", fixed_dockerfile)
        self.assertNotIn("COPY gradle/ gradle/", fixed_dockerfile)
        self.assertNotIn("COPY gradlew* ./", fixed_dockerfile)
        self.assertTrue(corrections)


class PipelineRequirementsChatTests(unittest.TestCase):
    def setUp(self):
        self.chat = ChatService(SimpleNamespace(ollama_url="http://ollama", gitlab_token="token"))

    def test_java_requirements_ask_for_missing_generation_decisions(self):
        values, sources = self.chat._build_initial_requirement_values({
            "language": "java",
            "framework": "gradle",
            "build_tool": "gradle",
            "files": ["build.gradle"],
            "all_paths": ["build.gradle", "src/main/java/App.java"],
            "has_dockerfile": False,
        })
        session = {"values": values, "sources": sources, "analysis": {"has_dockerfile": False}}

        questions = self.chat._missing_requirement_questions(session)
        question_fields = {item["field"] for item in questions}

        self.assertIn("output_mode", question_fields)
        self.assertIn("language_version", question_fields)
        self.assertIn("framework", question_fields)
        self.assertIn("packaging", question_fields)

    def test_java_answers_resolve_to_confirmable_template_values(self):
        values, sources = self.chat._build_initial_requirement_values({
            "language": "java",
            "framework": "generic",
            "build_tool": "gradle",
            "files": ["build.gradle"],
            "all_paths": ["build.gradle"],
            "has_dockerfile": False,
        })
        session = {"values": values, "sources": sources, "analysis": {"has_dockerfile": False}}

        self.chat._apply_user_requirement_answers(
            session,
            "Use Java 21, Gradle, generic Java, JAR, Docker image"
        )

        self.assertEqual(session["values"]["language_version"], "21")
        self.assertEqual(session["values"]["build_tool"], "gradle")
        self.assertEqual(session["values"]["framework"], "generic")
        self.assertEqual(session["values"]["packaging"], "jar")
        self.assertEqual(session["values"]["output_mode"], "docker-image")
        self.assertEqual(session["values"]["artifact_pattern"], "build/libs/*.jar")
        self.assertEqual(self.chat._missing_requirement_questions(session), [])


class DirectArtifactPipelineTests(unittest.TestCase):
    def test_direct_artifact_pipeline_skips_dockerfile_validation(self):
        service = PipelineGeneratorService()
        validator = GitLabDryRunValidator()
        validator.gitlab_token = ""
        gitlab_ci = service._get_direct_artifact_gitlab_ci({
            "language": "java",
            "framework": "generic",
            "build_tool": "gradle",
            "java_version": "21",
            "packaging": "jar",
            "artifact_pattern": "build/libs/*.jar",
            "output_mode": "direct-artifact",
            "artifact_publish_target": "gitlab-artifacts",
            "resolved_compile_image": "gradle:8.7-jdk21-alpine",
        })

        self.assertTrue(validator.validate_yaml_syntax(gitlab_ci).valid)
        self.assertNotIn("Dockerfile", gitlab_ci)
        structure = validator.validate_pipeline_structure(gitlab_ci, require_dockerfile=False)
        self.assertTrue(structure.valid)
        self.assertNotIn("Missing recommended stage: 'build'", structure.warnings)
        self.assertNotIn("Missing recommended stage: 'push'", structure.warnings)
        self.assertNotIn(
            "dockerfile_syntax",
            asyncio.run(validator.validate_all(gitlab_ci, "", require_dockerfile=False)),
        )

    def test_template_identity_infers_direct_artifact_without_dockerfile(self):
        document = """## Successful Pipeline Configuration
### .gitlab-ci.yml
```yaml
stages: [compile]
```

### Dockerfile
```dockerfile

```
"""

        self.assertFalse(_document_has_dockerfile(document))
        self.assertEqual(_infer_output_mode(document, {}), "direct-artifact")


if __name__ == "__main__":
    unittest.main()
