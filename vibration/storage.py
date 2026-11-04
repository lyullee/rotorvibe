import json
import sqlite3
import threading
from datetime import datetime, timezone
from .bootstrap import RUNTIME


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self):
        RUNTIME.mkdir(parents=True,exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(RUNTIME/'vibration.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, started TEXT, source TEXT, config TEXT);
        CREATE TABLE IF NOT EXISTS frames(id INTEGER PRIMARY KEY, session_id TEXT, timestamp TEXT, sample_end INTEGER, payload TEXT);
        CREATE INDEX IF NOT EXISTS frames_session ON frames(session_id,id);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, session_id TEXT, timestamp TEXT, level TEXT, kind TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS documents(kind TEXT, name TEXT, payload TEXT, updated TEXT, PRIMARY KEY(kind,name));
        ''')
        self.db.commit()

    def close(self):
        with self.lock: self.db.close()

    def start_session(self, id, source, config):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',
                            (id, utcnow(), json.dumps(source,ensure_ascii=False),json.dumps(config,ensure_ascii=False)))
            self.db.commit()

    def frame(self, session_id, frame):
        # Spectra and raw windows stay in memory or explicit recordings, not every database row.
        payload = {k:frame.get(k) for k in ['metrics','quality','diagnosis','baseline','alarm','rpm','rul','classification','analysis_ms']}
        with self.lock:
            self.db.execute('INSERT INTO frames(session_id,timestamp,sample_end,payload) VALUES(?,?,?,?)',
                            (session_id, frame['timestamp'], frame['sample_end'], json.dumps(payload,ensure_ascii=False)))
            self.db.commit()

    def event(self, session_id, level, kind, payload):
        with self.lock:
            self.db.execute('INSERT INTO events(session_id,timestamp,level,kind,payload) VALUES(?,?,?,?,?)',
                            (session_id,utcnow(),level,kind,json.dumps(payload,ensure_ascii=False)))
            self.db.commit()

    def save(self, kind, name, value):
        if not name or len(name)>120:
            raise ValueError('저장 이름은 1~120자여야 합니다.')
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?)',
                            (kind,name,json.dumps(value,ensure_ascii=False),utcnow()))
            self.db.commit()

    def get(self, kind, name):
        with self.lock:
            row=self.db.execute('SELECT payload FROM documents WHERE kind=? AND name=?',(kind,name)).fetchone()
        if not row:
            raise ValueError('저장된 항목을 찾을 수 없습니다.')
        return json.loads(row[0])

    def documents(self, kind):
        with self.lock:
            rows=self.db.execute('SELECT name,updated,payload FROM documents WHERE kind=? ORDER BY updated DESC',(kind,)).fetchall()
        return [{'name':n,'updated':t,'summary':json.loads(p).get('summary',{})} for n,t,p in rows]

    def history(self, kind='events', limit=200, session_id=None):
        if kind not in ['events','frames','sessions']:
            raise ValueError('지원하지 않는 이력입니다.')
        with self.lock:
            self.db.row_factory=sqlite3.Row
            if session_id and kind!='sessions':
                rows=self.db.execute(f'SELECT * FROM {kind} WHERE session_id=? ORDER BY rowid DESC LIMIT ?',
                                     (session_id,min(20000,max(1,limit)))).fetchall()
            else:
                rows=self.db.execute(f'SELECT * FROM {kind} ORDER BY rowid DESC LIMIT ?', (min(20000,max(1,limit)),)).fetchall()
            self.db.row_factory=None
        result=[]
        for row in rows:
            d=dict(row)
            for key in ['payload','source','config']:
                if key in d: d[key]=json.loads(d[key])
            result.append(d)
        return result

