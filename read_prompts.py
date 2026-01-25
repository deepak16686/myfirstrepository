import json, sqlite3
conn = sqlite3.connect("/app/backend/data/webui.db")
rows = conn.execute("SELECT id, name, params FROM model").fetchall()
for row in rows:
    params = json.loads(row[2]) if row[2] else {}
    system = params.get("system", "")
    print(f"=== {row[0]} : {row[1]} ===")
    print(system)
    print("\n---END---\n")
conn.close()
