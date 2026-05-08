"""
GitLab Pipeline Generator Service - Compatibility Shim.

Historically this module contained the entire monolithic implementation. It now
re-exports the package-based singleton at `app.services.pipeline.pipeline_generator`
so the package is the single source of truth (templates, generator, validator,
committer, monitor, learning, image_seeder).

The legacy 2386-line implementation has been preserved at
`pipeline_generator.py.bak-20260429-1043` should a rollback be needed.

Existing callers of `from app.services.pipeline_generator import pipeline_generator`
continue to work unchanged because the singleton instance is identical.
"""
from app.services.pipeline import (  # noqa: F401  (re-exports for backward compat)
    PipelineGeneratorService,
    pipeline_generator,
)

__all__ = ["PipelineGeneratorService", "pipeline_generator"]
