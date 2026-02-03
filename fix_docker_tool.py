import textwrap, os
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR
from pathlib import Path

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"
TOOL_ID = "nexus_docker_images"

content = replace_imports(textwrap.dedent('''
"""
description: List Docker images and generate Dockerfiles from Nexus private registry
"""
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

    "node": """FROM {image}

WORKDIR /usr/src/app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "app.js"]""",

    "golang": """FROM {image} AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

FROM {alpine_image}
WORKDIR /app
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]""",

    "php": """FROM {image}

WORKDIR /var/www/html
COPY . .
RUN docker-php-ext-install pdo pdo_mysql
EXPOSE 9000
CMD ["php-fpm"]""",

    "maven": """FROM {image} AS builder

WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn clean package -DskipTests

FROM {eclipse_image}
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]""",

    "java": """FROM {image} AS builder

WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn clean package -DskipTests

FROM {eclipse_image}
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]""",

    "rust": """FROM {image} AS builder

WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM {alpine_image}
WORKDIR /app
COPY --from=builder /app/target/release/app .
EXPOSE 8080
CMD ["./app"]""",

    "nginx": """FROM {image}

COPY nginx.conf /etc/nginx/nginx.conf
COPY . /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]""",

    "dotnet": """FROM {image}

WORKDIR /app
COPY . .
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
CMD ["dotnet", "app.dll"]""",

    "mongo": """FROM {image}

EXPOSE 27017
VOLUME /data/db
CMD ["mongod"]""",

    "redis": """FROM {image}

EXPOSE 6379
CMD ["redis-server"]""",

    "postgres": """FROM {image}

ENV POSTGRES_DB=mydb
ENV POSTGRES_USER=user
ENV POSTGRES_PASSWORD=password
EXPOSE 5432""",

    "ruby": """FROM {image}

WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install --without development test
COPY . .
EXPOSE 3000
CMD ["ruby", "app.rb"]""",

    "gradle": """FROM {image} AS builder

WORKDIR /app
COPY build.gradle settings.gradle ./
COPY gradle ./gradle
RUN gradle dependencies --no-daemon
COPY src ./src
RUN gradle build --no-daemon -x test

FROM {eclipse_image}
WORKDIR /app
COPY --from=builder /app/build/libs/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]"""
}

class Tools:
    def list_docker_images(self, query: str = "") -> str:
        """List available Docker images from Nexus and generate a Dockerfile. Pass a simple keyword: python, node, nginx, java, golang, mongo, redis, php, maven, postgres, alpine, rust, dotnet, ruby, gradle, etc."""
        auth = (USER, PASS)
        try:
            catalog = requests.get(f"{REGISTRY}/v2/_catalog", auth=auth, timeout=10)
            catalog.raise_for_status()
            catalog_data = catalog.json() or {}
            repos = catalog_data.get("repositories", [])

            if query:
                query_words = [w.lower().strip() for w in query.replace(",", " ").split() if len(w.strip()) > 1]
                matched_repos = []
                for repo in repos:
                    repo_lower = repo.lower()
                    for word in query_words:
                        if word in repo_lower:
                            matched_repos.append(repo)
                            break
                repos = matched_repos

            if not repos:
                tech = query.strip()
                return f"{tech} image is not available in your private Nexus registry.\\nPlease upload the required image first:\\n\\ndocker pull {tech}:<tag>\\ndocker tag {tech}:<tag> {PULL_REGISTRY}/apm-repo/demo/{tech}:<tag>\\ndocker push {PULL_REGISTRY}/apm-repo/demo/{tech}:<tag>"

            results = []
            for repo in repos:
                resp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=10)
                resp.raise_for_status()
                data = resp.json() or {}
                tags = data.get("tags", []) or []
                if tags:  # Only add repos with tags
                    results.append({
                        "repository": data.get("name", repo),
                        "tags": tags
                    })

            # Build image list
            image_list = "Available images in private Nexus registry:\\n"
            for r in results:
                for tag in r["tags"]:
                    image_list += f"  - {PULL_REGISTRY}/{r['repository']}:{tag}\\n"

            # Find alpine image for multi-stage builds
            alpine_image = f"{PULL_REGISTRY}/apm-repo/demo/alpine:latest"
            all_repos = catalog_data.get("repositories", [])
            for repo in all_repos:
                if "alpine" in repo.lower() and "curl" not in repo.lower():
                    try:
                        aresp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=5)
                        aresp_data = aresp.json() or {}
                        atags = aresp_data.get("tags", []) or []
                        if atags:
                            alpine_image = f"{PULL_REGISTRY}/{repo}:{atags[0]}"
                            break
                    except:
                        pass

            # Find eclipse-temurin for java
            eclipse_image = f"{PULL_REGISTRY}/apm-repo/demo/eclipse-temurin:latest"
            for repo in all_repos:
                if "eclipse-temurin" in repo.lower() or "amazoncorretto" in repo.lower():
                    try:
                        eresp = requests.get(f"{REGISTRY}/v2/{repo}/tags/list", auth=auth, timeout=5)
                        eresp_data = eresp.json() or {}
                        etags = eresp_data.get("tags", []) or []
                        if etags:
                            eclipse_image = f"{PULL_REGISTRY}/{repo}:{etags[0]}"
                            break
                    except:
                        pass

            # Generate Dockerfile if template exists
            tech_key = query.lower().strip()
            if not results or not results[0].get('tags'):
                return f"No images with tags found for '{query}' in Nexus registry."
            best_image = f"{PULL_REGISTRY}/{results[0]['repository']}:{results[0]['tags'][0]}"

            if tech_key in DOCKERFILE_TEMPLATES:
                dockerfile = DOCKERFILE_TEMPLATES[tech_key].format(
                    image=best_image,
                    alpine_image=alpine_image,
                    eclipse_image=eclipse_image
                )
                return f"{image_list}\\n---\\nDockerfile using private Nexus registry:\\n\\n{dockerfile}\\n\\nIMPORTANT: All FROM images above use the private Nexus registry ({PULL_REGISTRY}). NEVER replace them with public Docker Hub images."
            else:
                return f"{image_list}\\nUse these images with format: FROM {PULL_REGISTRY}/<repository>:<tag>\\nNEVER use public Docker Hub images."

        except Exception as e:
            return f"Error connecting to Nexus registry: {str(e)}"
''').strip())

meta = ToolMeta(description="List Docker images and generate Dockerfiles from Nexus private registry")
form = ToolForm(id=TOOL_ID, name="Nexus Docker Images", content=content, meta=meta, access_control=None)

existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)

module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
