import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'bot.db')
db_path = os.path.abspath(db_path)
if not os.path.exists(db_path):
    print('Database not found at', db_path)
    raise SystemExit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
rows = cur.execute("SELECT user_id, username FROM users ORDER BY user_id").fetchall()
print('Total users:', len(rows))
for uid, username in rows:
    print(uid, username or '')
cur.close()
conn.close()
