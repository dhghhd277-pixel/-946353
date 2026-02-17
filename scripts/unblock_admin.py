import sqlite3
import os

# Read .env
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
admin_id = None
db_path = None
try:
    with open(env_path, 'r', encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith('#'):
                continue
            if '=' not in ln:
                continue
            k, v = ln.split('=', 1)
            k = k.strip()
            v = v.strip()
            if k == 'ADMIN_ID':
                try:
                    admin_id = int(v)
                except Exception:
                    admin_id = None
            if k == 'DATABASE_PATH':
                db_path = v
except Exception as e:
    print('Failed to read .env:', e)

if admin_id is None:
    print('ADMIN_ID not found in .env')
    raise SystemExit(2)

if not db_path:
    db_path = 'bot.db'

# Resolve path relative to repo root
db_full = os.path.join(os.path.dirname(__file__), '..', db_path)
db_full = os.path.abspath(db_full)
if not os.path.exists(db_full):
    print('Database not found at', db_full)
    raise SystemExit(3)

print('Unblocking admin', admin_id, 'in DB:', db_full)
conn = sqlite3.connect(db_full)
cur = conn.cursor()
cur.execute('UPDATE users SET blocked = 0 WHERE user_id = ?', (int(admin_id),))
conn.commit()
print('Rows affected:', cur.rowcount)
cur.close()
conn.close()
print('Done')
