import json
import sqlite3
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.images = root / 'frames'
        self.images.mkdir(exist_ok=True)
        self.db = sqlite3.connect(root / 'evidenceguard.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS frames (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        ''')

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def save(self, task, settings, events=()):
        # State and events commit together; process crashes cannot create a duplicate episode.
        with self.db:
            for key, value in [('task', task), ('settings', settings)]:
                self.db.execute('INSERT OR REPLACE INTO state VALUES (?, ?)', (key, json.dumps(value)))
            for event in events:
                self.db.execute('INSERT INTO events(payload) VALUES (?)', (json.dumps(event),))

    def append(self, event):
        with self.db:
            cursor = self.db.execute('INSERT INTO events(payload) VALUES (?)', (json.dumps(event),))
        return cursor.lastrowid

    def events(self, limit=60, after=0):
        rows = self.db.execute('SELECT sequence,payload FROM events WHERE sequence>? ORDER BY sequence DESC LIMIT ?',
                               (after, min(limit, 500))).fetchall()
        return [dict(sequence=r[0], **json.loads(r[1])) for r in rows]

    def frame(self, frame_id, payload):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO frames VALUES (?,?)', (frame_id, json.dumps(payload)))

    def close(self):
        self.db.close()

    def prune_unreferenced(self, before: float, current_ids: set[str]):
        protected = set(current_ids)
        for row in self.db.execute('SELECT payload FROM events'):
            event = json.loads(row[0])
            protected.update(o['frame_id'] for o in event.get('evidence', []))
        rows = self.db.execute('SELECT id,payload FROM frames').fetchall()
        obsolete = [frame_id for frame_id, payload in rows if frame_id not in protected
                    and json.loads(payload)['captured_at'] < before]
        with self.db:
            for frame_id in obsolete:
                (self.images / f'{frame_id}.jpg').unlink(missing_ok=True)
                self.db.execute('DELETE FROM frames WHERE id=?', (frame_id,))
