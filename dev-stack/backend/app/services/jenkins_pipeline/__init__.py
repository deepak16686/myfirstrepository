"""
File: __init__.py
Purpose: Package initializer for the Jenkins pipeline generator service. Exposes the
    JenkinsPipelineGeneratorService facade class and a singleton instance for backward compatibility.
When Used: Imported by the Jenkins pipeline router (app/routers/jenkins_pipeline.py) and the chat
    endpoint whenever a user requests Jenkins pipeline generation. The singleton
    `jenkins_pipeline_generator` is the main entry point for all Jenkins pipeline operations.
Why Created: Provides a clean public API for the package after the monolithic pipeline generator
    was split into specialized modules (analyzer, committer, templates, validator, etc.), keeping
    import paths short and consistent with the GitLab/GitHub pipeline package conventions.
"""
from app.services.jenkins_pipeline.generator import JenkinsPipelineGeneratorService

# Singleton instance for backward compatibility
jenkins_pipeline_generator = JenkinsPipelineGeneratorService()

__all__ = ["JenkinsPipelineGeneratorService", "jenkins_pipeline_generator"]
