"""
File: __init__.py
Purpose: Root package initializer for the services layer. Imports and re-exports the core GitLab pipeline services (pipeline_generator, dry_run_validator, llm_fixer, self_healing_workflow) for convenient access.
When Used: Imported by other modules that need the primary GitLab pipeline services without specifying the full subpackage path.
Why Created: Provides backward-compatible top-level imports for the original GitLab pipeline services that existed before the codebase was reorganized into subpackages.
"""
from app.services.pipeline import pipeline_generator
from app.services.dry_run_validator import dry_run_validator
from app.services.llm_fixer import llm_fixer
from app.services.self_healing_workflow import self_healing_workflow

__all__ = [
    'pipeline_generator',
    'dry_run_validator',
    'llm_fixer',
    'self_healing_workflow'
]
