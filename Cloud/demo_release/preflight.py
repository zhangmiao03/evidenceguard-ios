"""Run on the demo host; credentials and workers are disabled before imports."""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

RELEASE=Path(__file__).resolve().parent
DATABASE=Path('/var/lib/evidenceguard-demo/evidenceguard.sqlite3')
PRESERVED=('skills','media','evidence','runs','recordings','personal_profiles','personal_memories','push_devices','connector_tokens','private_clients')


def count(db):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in PRESERVED if t in tables}


def main():
    with tempfile.TemporaryDirectory(prefix='eg-demo-preflight-') as temp:
        for key in list(os.environ):
            if key.startswith(('EG_','EVIDENCEGUARD_')): del os.environ[key]
        os.environ.update(EG_DISABLE_WORKERS='1',EG_OPS_ENABLED='0',EG_DATABASE=temp+'/global.sqlite3',
            EG_VIDEO_ROOT=temp+'/recordings',PYTHONPATH=str(RELEASE/'Cloud/server'))
        # Existing credentials, hardware and live production database are never used by tests.
        subprocess.run([sys.executable,'-m','pytest','-q',str(RELEASE/'Cloud/server/tests')],check=True,cwd=temp)
        copy=Path(temp)/'migration.sqlite3'
        with sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(copy) as target:
            source.backup(target); before=count(target)
        sys.path.insert(0,str(RELEASE/'Cloud/server'))
        from evidenceguard.app import create_app, app as global_app
        app=create_app(copy,start_worker=False)
        assert count(app.state.store.db)==before, 'Migration changed preserved business row counts'
        assert app.state.store.db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        async def close():
            for instance in (app,global_app):
                await instance.state.hardware.close();instance.state.store.close()
        asyncio.run(close())
        print(json.dumps({'preflight':'passed','preservedRowCounts':before,'migration':'isolated copy only'}))


if __name__=='__main__':main()
