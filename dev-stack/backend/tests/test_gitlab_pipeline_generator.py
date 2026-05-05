import unittest

from app.services.gitlab_dry_run_validator import GitLabDryRunValidator
from app.services.pipeline.analyzer import parse_gitlab_url
from app.services.pipeline.default_templates import (
    _get_default_dockerfile,
    _get_default_gitlab_ci,
)
from app.services.pipeline.validator import _ensure_learn_stage


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


if __name__ == "__main__":
    unittest.main()
