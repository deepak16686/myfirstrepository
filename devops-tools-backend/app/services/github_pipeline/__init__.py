"""GitHub Actions Pipeline Generator Service Package.

Provides AI-powered GitHub Actions workflow generation for Gitea/GitHub.
"""
from app.services.github_pipeline.generator import GitHubPipelineGeneratorService

# Singleton instance for backward compatibility
github_pipeline_generator = GitHubPipelineGeneratorService()

__all__ = ["GitHubPipelineGeneratorService", "github_pipeline_generator"]
