"""
File: app/models/__init__.py
Purpose: Package initializer for Pydantic request/response models used across all API routers.
When Used: Imported when any module references 'app.models.schemas' or 'app.models.pipeline_schemas'.
Why Created: Organizes data models into a dedicated package, separating API contract definitions
    (schemas.py for tool/GitLab/SonarQube/Trivy/Nexus/connectivity models, pipeline_schemas.py
    for pipeline generation/commit/self-healing models) from business logic in routers and services.
"""
# Models
