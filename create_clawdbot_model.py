import sqlite3, json, time

conn = sqlite3.connect("/app/backend/data/webui.db")
c = conn.cursor()

model_id = "clawdbot"
name = "Clawdbot - Personal Assistant"
base_model_id = "clawdbot:latest"

meta = {
    "profile_image_url": "/static/favicon.png",
    "description": "Your friendly personal assistant for everyday tasks",
    "capabilities": {
        "vision": False,
        "citations": True
    },
    "suggestion_prompts": [
        {"title": ["Help me write"], "content": "an email to my manager"},
        {"title": ["Explain"], "content": "a complex topic simply"},
        {"title": ["Brainstorm ideas"], "content": "for my project"}
    ],
    "tags": []
}

params = {
    "system": "You are Clawdbot, a friendly and helpful personal assistant."
}

c.execute("SELECT id FROM model WHERE id=?", (model_id,))
existing = c.fetchone()

if existing:
    c.execute("UPDATE model SET name=?, meta=?, params=?, base_model_id=?, updated_at=? WHERE id=?",
              (name, json.dumps(meta), json.dumps(params), base_model_id, int(time.time()), model_id))
    print(f"Updated existing model: {model_id}")
else:
    c.execute("INSERT INTO model (id, name, meta, params, base_model_id, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (model_id, name, json.dumps(meta), json.dumps(params), base_model_id, int(time.time()), int(time.time()), "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"))
    print(f"Created new model: {model_id}")

conn.commit()
conn.close()
print("Done! Clawdbot is now available in OpenWebUI.")
