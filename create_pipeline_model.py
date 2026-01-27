import sqlite3, json, time

conn = sqlite3.connect("/app/backend/data/webui.db")
c = conn.cursor()

model_id = "gitlab-pipeline-generator"
name = "Gitlab Pipeline Generator"
base_model_id = "qwen2.5-coder:32b-instruct-q4_K_M"
meta = '{"profile_image_url": "/static/favicon.png", "description": "Generate GitLab CI/CD pipelines using private Nexus registry images", "capabilities": {"file_context": true, "vision": true, "file_upload": true, "web_search": false, "image_generation": false, "code_interpreter": true, "citations": true, "status_updates": true, "builtin_tools": true}, "suggestion_prompts": [{"title": ["Generate pipeline"], "content": "for a Java application"}, {"title": ["Create Dockerfile"], "content": "for a Python application"}, {"title": ["List images"], "content": "available in Nexus registry"}], "tags": [], "toolIds": ["nexus_docker_images", "gitlab_pipeline_generator"], "defaultFeatureIds": ["code_interpreter"]}'
params = '{"system": "You are a GitLab CI/CD pipeline generator assistant. You generate pipelines using ONLY images from the private Nexus registry. You have NO knowledge of public Docker Hub.\\n\\nABSOLUTE RULES - VIOLATION IS NOT ALLOWED:\\n\\nRULE 1: Before answering ANY question about CI/CD pipelines, you MUST call get_pipeline_template FIRST. No exceptions.\\n\\nRULE 2: For pipeline requests, call get_pipeline_template with technology and stages.\\n- User says gitlab pipeline for golang -> call with technology=golang, stages=all\\n- User says sonarqube scanning -> call with technology=sonarqube, stages=all\\n- User says ruby pipeline -> call with technology=ruby, stages=all\\n- User says just the build stage for java -> call with technology=java, stages=build\\n- User says compile and test for python -> call with technology=python, stages=compile,test\\n\\nRULE 3: When the user asks for BOTH pipeline AND Dockerfile, you MUST call BOTH tools:\\n- Call get_pipeline_template for the pipeline YAML\\n- Call list_docker_images for the Dockerfile\\n\\nRULE 4: ALWAYS display the COMPLETE output from tools in your response. Show the FULL content returned by the tool in a code block. NEVER summarize, NEVER skip content, NEVER just mention sources. The user MUST see the full YAML text.\\n\\nRULE 5: Format your response like this:\\n- Show the pipeline YAML in a yaml code block\\n- Show the Dockerfile in a dockerfile code block if requested\\n- Add brief explanation if needed\\n\\nRULE 6: If the tool returns an error or image not available, show ONLY the error message. NEVER generate your own pipeline.\\n\\nRULE 7: You do NOT know about Docker Hub, ghcr.io, quay.io, or any public registry. You ONLY know about the private Nexus registry at localhost:5001.\\n\\nRULE 8: NEVER modify, edit, or rewrite the output from tools. Present it EXACTLY as returned by the tool.\\n\\nRULE 9: If someone asks for a Dockerfile along with pipeline, call list_docker_images with a SINGLE keyword (golang, python, ruby, java, node, etc).\\n\\nRULE 10: All images in generated pipelines MUST come from the private Nexus registry. Never suggest public images."}'

c.execute("SELECT id FROM model WHERE id=?", (model_id,))
existing = c.fetchone()

if existing:
    c.execute("UPDATE model SET name=?, meta=?, params=?, base_model_id=?, updated_at=? WHERE id=?",
              (name, meta, params, base_model_id, int(time.time()), model_id))
    print(f"Updated existing model: {model_id}")
else:
    c.execute("INSERT INTO model (id, name, meta, params, base_model_id, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (model_id, name, meta, params, base_model_id, int(time.time()), int(time.time()), "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"))
    print(f"Created new model: {model_id}")

conn.commit()
conn.close()
print("Done!")
