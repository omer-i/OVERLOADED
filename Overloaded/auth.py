import sqlite3
import os
import hashlib
import hmac


class AuthManager:
    """SQLite-backed AuthManager storing users with per-user salt and PBKDF2 keys.

    DB schema:
      users(username TEXT PRIMARY KEY, salt TEXT, key TEXT)
      meta(k TEXT PRIMARY KEY, v TEXT)
    """

    def __init__(self, path=None):
        if path is None:
            app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Overloaded')
            os.makedirs(app_dir, exist_ok=True)
            path = os.path.join(app_dir, 'users.db')
        self.path = path
        self._ensure_db()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _ensure_db(self):
        exists = os.path.exists(self.path)
        with self._conn() as c:
            cur = c.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    salt TEXT NOT NULL,
                    key TEXT NOT NULL
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS kills (
                    username TEXT PRIMARY KEY,
                    best_kills_in_game INTEGER DEFAULT 0
                )
            ''')
            c.commit()

    def _derive(self, password, salt_hex, iterations=100_000):
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return dk.hex()

    def register(self, username, password):
        username = username.strip()
        if not username:
            return False, 'Username invalid'
        with self._conn() as c:
            cur = c.cursor()
            cur.execute('SELECT 1 FROM users WHERE username=?', (username,))
            if cur.fetchone():
                return False, 'Username already exists'
            salt = os.urandom(16).hex()
            key = self._derive(password, salt)
            cur.execute('INSERT INTO users(username,salt,key) VALUES(?,?,?)', (username, salt, key))
            c.commit()
            return True, 'Registered'

    def authenticate(self, username, password):
        if not username:
            print(f"[DEBUG] Username empty")
            return False
        with self._conn() as c:
            cur = c.cursor()
            cur.execute('SELECT salt,key FROM users WHERE username=?', (username,))
            row = cur.fetchone()
            if not row:
                print(f"[DEBUG] User '{username}' not found in DB")
                return False
            salt, expected = row
            derived = self._derive(password, salt)
            print(f"[DEBUG] Stored key: {expected}")
            print(f"[DEBUG] Derived key: {derived}")
            print(f"[DEBUG] Keys match: {derived == expected}")
            try:
                result = hmac.compare_digest(derived, expected)
                print(f"[DEBUG] hmac.compare_digest result: {result}")
                return result
            except Exception as e:
                print(f"[DEBUG] Exception during comparison: {e}")
                return False

    def list_users(self):
        with self._conn() as c:
            cur = c.cursor()
            cur.execute('SELECT username FROM users')
            return [r[0] for r in cur.fetchall()]


    def record_game_kills(self, username, kills_in_game):
        """Record kills from a game session. Only updates if it's the best performance."""
        if not username or kills_in_game < 0:
            return
        with self._conn() as c:
            cur = c.cursor()
            # Only update if this is better than previous best
            cur.execute('SELECT best_kills_in_game FROM kills WHERE username=?', (username,))
            row = cur.fetchone()
            current_best = row[0] if row else 0
            
            if kills_in_game > current_best:
                cur.execute('REPLACE INTO kills(username, best_kills_in_game) VALUES(?, ?)', (username, kills_in_game))
                c.commit()
    

    def get_leaderboard(self, limit=10):
        """Get top users by kill count."""
        with self._conn() as c:
            cur = c.cursor()
            cur.execute('SELECT username, best_kills_in_game FROM kills ORDER BY best_kills_in_game DESC LIMIT ?', (limit,))
            return cur.fetchall()

    def print_db(self):
        """Print all users and metadata from the database."""
        with self._conn() as c:
            cur = c.cursor()
            print("\n=== USERS TABLE ===")
            cur.execute('SELECT * FROM users')
            users = cur.fetchall()
            if users:
                for username, salt, key in users:
                    print(f"Username: {username}")
                    print(f"  Salt: {salt}")
                    print(f"  Key: {key}")
            else:
                print("(No users)")
            
            print("\n=== META TABLE ===")
            cur.execute('SELECT * FROM meta')
            meta = cur.fetchall()
            if meta:
                for k, v in meta:
                    print(f"{k}: {v}")
            else:
                print("(No metadata)")


if __name__ == '__main__':
    auth = AuthManager()
    auth.print_db()

