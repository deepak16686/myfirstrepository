"""
File: __init__.py
Purpose: Package initializer for the GitLab CI/CD pipeline generator service. Exposes the
    PipelineGeneratorService facade class and a singleton instance for backward compatibility.
When Used: Imported at application startup and by the pipeline router whenever any pipeline
    operation is requested (generation, commit, monitoring, learning, or template management).
Why Created: Serves as the entry point for the pipeline package after the original monolithic
    pipeline_generator.py (3291 lines) was refactored into 9+ focused modules. This file
    provides a clean public API so callers do not need to know about the internal module split.
"""
from app.services.pipeline.generator import PipelineGeneratorService

# Singleton instance for backward compatibility
pipeline_generator = PipelineGeneratorService()

__all__ = ["PipelineGeneratorService", "pipeline_generator"]
