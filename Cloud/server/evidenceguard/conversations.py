"""Persistent mobile conversation navigation; a new topic never rebinds the main inbox.

The installation namespace is for the internal household demo, not account auth.
Live and history tool scopes retain separate streams under the same visible topic.
"""
import hashlib
import time
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class NewConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    requestId: UUID


class ConversationTitle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=80)


class Conversations:
    def __init__(self, store, proactive):
        self.store, self.proactive = store, proactive
        with store.transaction():
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, client TEXT NOT NULL, kind TEXT NOT NULL,
                    title TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS conversations_client ON conversations(client,updated_at);
                CREATE INDEX IF NOT EXISTS runs_conversation ON runs(conversation_id,created_at);
            ''')

    @staticmethod
    def root(key): return key.removesuffix('-history')

    def owner(self, key):
        key = self.root(key)
        with self.store.lock:
            row = self.store.db.execute('SELECT client FROM conversations WHERE id=?', (key,)).fetchone()
        return row[0] if row else self.proactive.owner(key)

    def check(self, key, client):
        owner = self.owner(key)
        if (owner and owner != client) or (self.root(key).startswith('topic-') and not owner):
            raise KeyError(key)

    def bind_main(self, client, key):
        # A topic or history stream cannot become the destination for proactive notices.
        if key.startswith('topic-') or key.endswith('-history'):
            raise ValueError('主对话与独立话题不能互相替换')
        with self.store.transaction():
            if self.owner(key) not in {None,client}: raise ValueError('此对话属于另一客户端')
            prior = self.store.db.execute('SELECT conversation FROM personal_conversations WHERE client=?', (client,)).fetchone()
            if prior and prior[0] != key:
                raise ValueError('此客户端已有助手主对话，请继续使用原对话')
            # Refuse to claim another installation's previously unindexed transcript.
            if any(r.get('clientId') not in {None, client} for stream in (key, key+'-history') for r in self.store.runs(stream)):
                raise KeyError(key)
            result = self.proactive.bind(client, key)
            now = time.time()
            self.store.db.execute('INSERT OR IGNORE INTO conversations VALUES (?,?,?,?,?,?)',
                                  (key, client, 'main', '助手主对话', now, now))
        return result

    def create(self, client, request_id):
        key = 'topic-' + hashlib.sha256((client+':'+str(request_id)).encode()).hexdigest()[:32]
        now = time.time()
        with self.store.transaction():
            self.store.db.execute('INSERT OR IGNORE INTO conversations VALUES (?,?,?,?,?,?)',
                                  (key, client, 'topic', None, now, now))
        return self.item(key, client)

    def item(self, key, client):
        with self.store.lock:
            row = self.store.db.execute('SELECT id,kind,title,created_at,updated_at FROM conversations WHERE id=? AND client=?', (key,client)).fetchone()
            if not row: raise KeyError(key)
            runs = sorted((r for stream in (key,key+'-history') for r in self.store.runs(stream)
                           if r.get('clientId') in {None,client}), key=lambda r:r['createdAt'])
            latest = runs[-1] if runs else None
            first = runs[0] if runs else None
            title = row[2] or (' '.join(first['message'].split())[:36] if first else '新对话')
            preview = (latest.get('text') or latest.get('message') or '') if latest else '开始一个独立话题'
            updated = max(row[4], latest['createdAt'] if latest else 0)
            unread = 0
            if row[1] == 'main':
                notices = self.proactive.messages(client)
                unread = sum(not m.get('read') for m in notices)
                if notices and notices[-1].get('updatedAt',notices[-1]['createdAt']) > updated:
                    preview = notices[-1]['body']; updated = notices[-1].get('updatedAt',notices[-1]['createdAt'])
        return dict(id=key, kind=row[1], title=title, preview=' '.join(preview.split())[:140],
                    createdAt=row[3], updatedAt=updated, unreadCount=unread,
                    hasActiveRun=any(r['status'] in {'queued','running'} for r in runs),
                    lastMode=latest.get('executionMode','live') if latest else 'live')

    def listing(self, client):
        with self.store.lock:
            keys = self.store.db.execute('SELECT id FROM conversations WHERE client=?', (client,)).fetchall()
            items = [self.item(r[0], client) for r in keys]
        return sorted(items, key=lambda v:(v['kind']!='main',-v['updatedAt']))

    def rename(self, key, client, title):
        title = title.strip()
        if not title: raise ValueError('请输入对话名称')
        with self.store.transaction():
            item = self.item(key,client)
            if item['kind']=='main': raise ValueError('助手主对话保留固定名称')
            self.store.db.execute('UPDATE conversations SET title=?,updated_at=? WHERE id=? AND client=?',
                                  (title,time.time(),key,client))
        return self.item(key,client)
