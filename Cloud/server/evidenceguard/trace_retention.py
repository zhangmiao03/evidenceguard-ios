"""Separate bounded retention for real Agent steps; never archive polling traffic.

Used by the app recorder and the additive dashboard observer on older releases.
Only the recorder's already-filtered payload is written. No business DB changes.
"""
import json
import os


def important(row):
    name = row.get('name', '')
    return (row.get('kind') in {'model', 'prompt'} or
            name.startswith(('agent.', 'tool.', 'codex.', 'context.', 'model.')) or
            name in {'camera_completed', 'camera_failed', 'vector.search'})


def limits():
    def bounded(name, default, low, high):
        try: return min(high, max(low, int(os.getenv(name, default))))
        except ValueError: return default
    return bounded('EG_OPS_CRITICAL_RECORDS', 10000, 100, 50000), bounded('EG_OPS_CRITICAL_BYTES', 128_000_000, 1_000_000, 512_000_000)


def write_records(recorder):
    """Single existing writer/queue; neither business calls nor camera uploads wait."""
    db = recorder.db
    record_limit, byte_limit = limits()
    critical = False
    def keep(row, raw):
        if important(row):
            db.execute('INSERT OR REPLACE INTO critical_records VALUES (?,?,?,?,?)',
                       (row['id'], row['traceId'], row['at'], raw, len(raw.encode('utf-8'))))

    def trim():
        count, size = db.execute('SELECT count(*),coalesce(sum(bytes),0) FROM critical_records').fetchone()
        # Evict complete oldest traces, not arbitrary middle steps. A single
        # oversized trace can also expire; retention is bounded, not permanent.
        while count > record_limit or size > byte_limit:
            trace, n, b = db.execute('SELECT trace_id,count(*),sum(bytes) FROM critical_records GROUP BY trace_id ORDER BY max(at),max(rowid) LIMIT 1').fetchone()
            db.execute('DELETE FROM critical_records WHERE trace_id=?', (trace,))
            count -= n; size -= b
            db.execute("INSERT INTO metadata VALUES ('criticalEvicted',?) ON CONFLICT(key) DO UPDATE SET value=cast(value AS INTEGER)+excluded.value", (str(n),))

    try:
        with recorder.lock, db:
            db.execute('CREATE TABLE IF NOT EXISTS critical_records(id TEXT PRIMARY KEY,trace_id TEXT NOT NULL,at REAL NOT NULL,payload TEXT NOT NULL,bytes INTEGER NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS critical_trace ON critical_records(trace_id,at)')
            if not db.execute("SELECT 1 FROM metadata WHERE key='criticalRetentionVersion'").fetchone():
                for raw, in db.execute('SELECT payload FROM records').fetchall():
                    try: keep(json.loads(raw), raw)
                    except (ValueError, KeyError, TypeError): pass
                trim()
                db.execute("INSERT INTO metadata VALUES ('criticalRetentionVersion','1')")
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('criticalPolicy',?)", (json.dumps({'recordLimit':record_limit,'byteLimit':byte_limit,'eviction':'oldest_complete_trace'}),))
        critical = True
    except Exception:
        recorder.write_errors += 1
    while True:
        row = recorder.q.get()
        try:
            if row is None: return
            raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
            with recorder.lock, db:
                db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', (row['id'], row['at'], raw))
                if critical:
                    keep(row, raw)
                    if important(row): trim()
                count = db.execute('SELECT count(*) FROM records').fetchone()[0]
                if count > recorder.retention:
                    n = count - recorder.retention
                    db.execute('DELETE FROM records WHERE id IN (SELECT id FROM records ORDER BY at LIMIT ?)', (n,))
                    recorder.evicted += n
        except Exception:
            recorder.write_errors += 1
        finally:
            recorder.q.task_done()


def install(ops):
    # Installed before app construction, so there is still exactly one writer.
    ops.Recorder._write = write_records
