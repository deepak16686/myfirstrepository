"""
title: Dockerfile Generator
author: AI Platform Team
version: 1.0.0
description: Generate Dockerfiles using RAG templates and private Nexus registry
"""

import requests
from typing import Optional
from pydantic import BaseModel, Field

class Tools:
    class Valves(BaseModel):
        GENERATOR_API_URL: str = Field(
            default="http://host.docker.internal:8080",
            description="URL of the Generator API"
        )

    def __init__(self):
        self.valves = self.Valves()

    def generate_dockerfile(
        self,
        stack: str,
        framework: Optional[str] = None,
        port: int = 8080,
        workdir: str = "/app"
    ) -> str:
        """
        Generate a Dockerfile using golden templates and private Nexus registry.
        
        :param stack: Technology stack (java, python, node)
        :param framework: Optional framework (spring-boot, fastapi, express)
        :param port: Application port (default: 8080)
        :param workdir: Container working directory (default: /app)
        :return: Generated Dockerfile content
        """
        
        try:
            response = requests.post(
                f"{self.valves.GENERATOR_API_URL}/generate/dockerfile",
                json={
                    "stack": stack,
                    "framework": framework,
                    "port": port,
                    "workdir": workdir
                },
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            dockerfile = result["content"]
            audit = result["audit"]
            
            return f"""Generated Dockerfile:
```dockerfile
{dockerfile}
```

**Audit Info:**
- Template: {audit['template_id']}
- Base Image: {audit['base_image']}
- Stack: {audit['stack']}
"""
        except Exception as e:
            return f"Error generating Dockerfile: {str(e)}"

    def generate_gitlab_ci(
        self,
        stack: str,
        build_tool: Optional[str] = None
    ) -> str:
        """
        Generate .gitlab-ci.yml using golden templates.
        
        :param stack: Technology stack (java, python, node)
        :param build_tool: Build tool (maven, gradle, npm, pip)
        :return: Generated GitLab CI content
        """
        
        try:
            response = requests.post(
                f"{self.valves.GENERATOR_API_URL}/generate/gitlabci",
                json={
                    "stack": stack,
                    "build_tool": build_tool
                },
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            gitlab_ci = result["content"]
            audit = result["audit"]
            
            return f"""Generated .gitlab-ci.yml:
```yaml
{gitlab_ci}
```

**Audit Info:**
- Template: {audit['template_id']}
- Stack: {audit['stack']}
- Build Tool: {audit.get('build_tool', 'N/A')}
"""
        except Exception as e:
            return f"Error generating GitLab CI: {str(e)}"
