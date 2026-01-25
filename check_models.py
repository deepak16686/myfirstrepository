import sqlite3, json

conn = sqlite3.connect('/app/backend/data/webui.db')
cursor = conn.cursor()
cursor.execute('SELECT id, params, meta FROM model')
rows = cursor.fetchall()
for row in rows:
    params = json.loads(row[1]) if row[1] else {}
    meta = json.loads(row[2]) if row[2] else {}
    print('Model:', row[0])
    print('Params keys:', list(params.keys()))
    print('Meta keys:', list(meta.keys()))
    if 'system' in params:
        print('params.system:', params['system'][:500])
    if 'system_prompt' in meta:
        print('meta.system_prompt:', meta['system_prompt'][:500])
    if 'tool_ids' in meta:
        print('meta.tool_ids:', meta['tool_ids'])
    print()
conn.close()
