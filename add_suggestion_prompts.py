import sqlite3
import json
import time

# Connect to OpenWeb UI database
conn = sqlite3.connect("/app/backend/data/webui.db")
cursor = conn.cursor()

# Define suggestion prompts for the chat interface
SUGGESTION_PROMPTS = [
    {
        "title": ["Generate GitLab Pipeline"],
        "content": "Generate a GitLab CI/CD pipeline for my project"
    },
    {
        "title": ["Create Dockerfile"],
        "content": "Create a Dockerfile for my application"
    },
    {
        "title": ["Test Tool Connection"],
        "content": "Test the connection to available tools and verify they are working"
    },
    {
        "title": ["Pipeline + Dockerfile"],
        "content": "Generate both GitLab pipeline and Dockerfile for my project"
    }
]

# Get all relevant models
models_to_update = [
    'qwen-mymodel',
    'deepseek-mymodel',
    'gitlab-pipeline-generator'
]

for model_id in models_to_update:
    cursor.execute("SELECT id, meta FROM model WHERE id = ?", (model_id,))
    row = cursor.fetchone()

    if row:
        meta = json.loads(row[1]) if row[1] else {}

        # Add suggestion prompts
        meta["suggestion_prompts"] = SUGGESTION_PROMPTS

        # Update the model
        cursor.execute(
            "UPDATE model SET meta = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), int(time.time()), model_id)
        )
        print(f"Updated suggestion prompts for: {model_id}")
    else:
        print(f"Model not found: {model_id}")

conn.commit()
conn.close()
print("\nDone! Suggestion prompts have been added to all models.")
print("Prompts added:")
for prompt in SUGGESTION_PROMPTS:
    print(f"  - {prompt['title'][0]}: {prompt['content']}")
