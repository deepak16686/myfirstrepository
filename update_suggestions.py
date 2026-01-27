import sqlite3, json, time

conn = sqlite3.connect("/app/backend/data/webui.db")
c = conn.cursor()

# New suggestion prompts
suggestions = [
    {"title": ["Generate pipeline"], "content": "for a Java application"},
    {"title": ["Create Dockerfile"], "content": "for a Python application"},
    {"title": ["List images"], "content": "available in Nexus registry"}
]

# Update the model
c.execute('SELECT id, meta FROM model WHERE id="gitlab-pipeline-generator"')
row = c.fetchone()

if row:
    meta = json.loads(row[1]) if row[1] else {}
    meta["suggestion_prompts"] = suggestions
    c.execute("UPDATE model SET meta=?, updated_at=? WHERE id=?",
              (json.dumps(meta), int(time.time()), "gitlab-pipeline-generator"))
    conn.commit()
    print("SUCCESS: Updated gitlab-pipeline-generator with new suggestions!")
    print("Suggestions added:")
    for s in suggestions:
        print(f"  - {s['title'][0]} {s['content']}")
else:
    print("ERROR: Model 'gitlab-pipeline-generator' not found!")

conn.close()
