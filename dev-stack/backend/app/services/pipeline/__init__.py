"""GitLab Pipeline Generator Service Package.

Provides AI-powered CI/CD pipeline generation with reinforcement learning.
"""
from app.services.pipeline.generator import PipelineGeneratorService

# Singleton instance for backward compatibility
pipeline_generator = PipelineGeneratorService()

__all__ = ["PipelineGeneratorService", "pipeline_generator"]
