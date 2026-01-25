import sqlite3, json, uuid, time

DB_PATH = "/app/backend/data/webui.db"
conn = sqlite3.connect(DB_PATH)

# Check existing knowledge tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%knowledge%'").fetchall()
print("Knowledge tables:", tables)

# Check table structure
for t in tables:
    cols = conn.execute(f"PRAGMA table_info({t[0]})").fetchall()
    print(f"  {t[0]} columns: {[(c[1], c[2]) for c in cols]}")

# Check existing knowledge entries
rows = conn.execute("SELECT * FROM knowledge LIMIT 5").fetchall()
print(f"Existing knowledge entries: {len(rows)}")
for r in rows:
    print(f"  {r[:3]}")

conn.close()
