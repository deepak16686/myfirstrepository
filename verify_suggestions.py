import sqlite3, json

conn = sqlite3.connect("/app/backend/data/webui.db")
c = conn.cursor()
c.execute('SELECT meta FROM model WHERE id="gitlab-pipeline-generator"')
row = c.fetchone()

if row:
    meta = json.loads(row[0])
    prompts = meta.get("suggestion_prompts", [])
    print("Current suggestion_prompts in database:")
    print(json.dumps(prompts, indent=2))
else:
    print("Model not found!")

conn.close()
