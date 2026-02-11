"""Jenkins Pipeline Generator Service Package.

Generates Jenkinsfile (Declarative Pipeline) and Dockerfile for projects.
Mirrors the GitLab pipeline generator architecture with Jenkins-specific syntax.
"""
from app.services.jenkins_pipeline.generator import JenkinsPipelineGeneratorService

# Singleton instance for backward compatibility
jenkins_pipeline_generator = JenkinsPipelineGeneratorService()

__all__ = ["JenkinsPipelineGeneratorService", "jenkins_pipeline_generator"]
