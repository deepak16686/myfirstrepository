import sqlite3, json, textwrap
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"

# === UPDATE DOCKER IMAGES TOOL ===
TOOL_ID_1 = "nexus_docker_images"

content1 = replace_imports(textwrap.dedent(chr(39)*3
+chr(10)+"""
description: List Docker images and generate Dockerfiles from Nexus private registry
"""
+chr(10)+chr(39)*3+"""
import os, requests

REGISTRY = os.getenv("NEXUS_REGISTRY", "http://ai-nexus:5001").rstrip("/")
USER = os.getenv("NEXUS_USER", "admin")
PASS = os.getenv("NEXUS_PASS", "r")
PULL_REGISTRY = "localhost:5001"

DOCKERFILE_TEMPLATES = {
    "python": """FROM {image}

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]""",
"""
).strip())

print("done")
