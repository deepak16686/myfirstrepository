"""
File: __init__.py
Purpose: Package initializer for the GitHub Actions pipeline generator service. Exposes the
    GitHubPipelineGeneratorService facade class and creates a singleton instance used by the router.
When Used: Imported by the router (app/routers/github_pipeline.py) and the self-healing workflow
    whenever any GitHub Actions pipeline operation is requested (generate, commit, monitor, learn).
Why Created: Provides a clean public API for the package, hiding the internal module structure and
    offering a singleton instance (github_pipeline_generator) for backward-compatible usage across
    the codebase.
"""
from app.services.github_pipeline.generator import GitHubPipelineGeneratorService

# Singleton instance for backward compatibility
github_pipeline_generator = GitHubPipelineGeneratorService()

__all__ = ["GitHubPipelineGeneratorService", "github_pipeline_generator"]
