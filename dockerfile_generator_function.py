"""
title: Dockerfile Generator
author: AI Platform Team
version: 1.0.0
required_open_webui_version: 0.3.0
"""

from pydantic import BaseModel, Field
import requests
from typing import Callable


class Tools:
    class Valves(BaseModel):
        API_URL: str = Field(
            default="http://host.docker.internal:8080",
            description="Generator API URL"
        )

    def __init__(self):
        self.valves = self.Valves()

    def generate_dockerfile(
        self,
        stack: str,
        port: int = 8080,
        __user__: dict = None,
        __event_emitter__: Callable = None,
    ) -> str:
        """
        Generate Dockerfile from RAG templates.
        
        :param stack: Technology stack (java, python, node)
        :param port: Application port
        :return: Generated Dockerfile
        """
        try:
            response = requests.post(
                f"{self.valves.API_URL}/generate/dockerfile",
                json={"stack": stack, "port": port},
                timeout=10
            )
            result = response.json()
            return f"```dockerfile\n{result['content']}\n```"
        except Exception as e:
            return f"Error: {str(e)}"
