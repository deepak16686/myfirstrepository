import sqlite3, json
conn = sqlite3.connect("/app/backend/data/webui.db")
c = conn.cursor()
c.execute("SELECT id, name, base_model_id FROM model")
for row in c.fetchall():
    print(f"{row[0]} | {row[1]} | base: {row[2]}")
conn.close()
