import json, sqlite3

conn = sqlite3.connect("/app/backend/data/webui.db")
cursor = conn.cursor()

AUTO_COMMIT_RULES = """
RULE 11: ZERO MANUAL COMMITS - CRITICAL RULE:
After you generate a Dockerfile and .gitlab-ci.yml, you MUST present both files to the user for review. Only after the user explicitly approves should you call the commit_and_deploy tool with ALL of these parameters:
- repo_url: the exact GitLab repository link provided by the user (preferred). If repo_url is set you may leave project_name blank.
- project_name: only used when no repo_url is provided. Derive it from the user request (lowercase with hyphens, e.g. "python-flask-app") so a repo can be created automatically.
- dockerfile_content: the FULL Dockerfile text you generated.
- gitlab_ci_content: the FULL .gitlab-ci.yml text you generated.
- commit_message: a descriptive summary of what you added.

NEVER write scripts that save files locally. NEVER tell the user to commit manually. The tool must do the commit for them after the user's verification.

RULE 12: REQUIRED WORKFLOW
1. Ask for the GitLab repo URL if it was not provided. If the user cannot share one, derive project_name from the request.
2. Use list_docker_images or get_pipeline_template if you need registry/pipeline context.
3. Generate the Dockerfile content and .gitlab-ci.yml content.
4. Share both files with the user, clearly ask "Do you approve committing these changes?" and wait for an explicit yes/approval.
5. Once approved, call commit_and_deploy(... repo_url or project_name ...).
6. Show the user both generated files AND the deployment result (repository + pipeline URLs).

RULE 13: HANDLING REPO LINKS VS PROJECT NAMES
- If the user shares a GitLab repository link, pass it EXACTLY via repo_url (e.g. repo_url="http://gitlab-server/group/project"). Do NOT invent a different project or ask them to commit manually.
- If no repository link exists, derive project_name from the request:
  * "Java Spring Boot app" -> project_name = "java-spring-boot-app"
  * "Python Flask API" -> project_name = "python-flask-api"
  * "containerize my golang service" -> project_name = "golang-service"
- When repo_url is used, project_name may be an empty string.

RULE 14: ABSOLUTELY NO manual git instructions, placeholder steps, or local file scripts. The commit_and_deploy tool handles repository creation (when needed), committing, and pipeline execution.
"""

rows = cursor.execute("SELECT id, params FROM model WHERE id IN ('qwen-mymodel', 'deepseek-mymodel', 'gitlab-pipeline-generator')").fetchall()

for row in rows:
    model_id = row[0]
    params = json.loads(row[1]) if row[1] else {}
    system = params.get("system", "")

    # Remove old RULE 11+ if any
    if "RULE 11:" in system:
        system = system[:system.index("RULE 11:")]

    system = system.rstrip() + "\n\n" + AUTO_COMMIT_RULES.strip()
    params["system"] = system

    cursor.execute("UPDATE model SET params = ? WHERE id = ?", (json.dumps(params), model_id))
    print(f"Updated: {model_id}")

conn.commit()
conn.close()
print("Done!")
