import sqlite3
import os
import sys

name = sys.argv[1] if len(sys.argv) > 1 else '@MatveiMatveiiiii'
q = name.lstrip('@').strip()
if not q:
    print('Provide a username')
    raise SystemExit(2)

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bot.db'))
if not os.path.exists(db_path):
    print('Database not found at', db_path)
    raise SystemExit(3)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
print('Searching for exact username match:', q)
row = cur.execute('SELECT user_id, username, blocked FROM users WHERE LOWER(username)=LOWER(?) LIMIT 1', (q,)).fetchone()
if row:
    uid, username, blocked = row
    print('Found exact match:')
    print('user_id:', uid)
    print('username:', username)
    print('blocked:', bool(blocked))
else:
    print('No exact match. Searching partial matches...')
    rows = cur.execute('SELECT user_id, username, blocked FROM users WHERE LOWER(username) LIKE LOWER(?) LIMIT 50', (f'%{q}%',)).fetchall()
    if not rows:
        print('No users found matching pattern')
    else:
        print('Partial matches:')
        for uid, username, blocked in rows:
            print(uid, username or '', 'blocked=' + str(bool(blocked)))
cur.close()
conn.close()
