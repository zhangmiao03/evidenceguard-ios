"""Unprivileged HTTP view of snapshots. No command, model or admin endpoints."""
import json
import os
from pathlib import Path
import time
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles


def create_app(data=None,web=None):
    data=Path(data or os.environ['EG_DASHBOARD_DATA'])
    web=Path(web or os.environ['EG_DASHBOARD_WEB'])
    app=FastAPI(title='EvidenceGuard competition dashboard',docs_url=None,redoc_url=None,openapi_url=None)
    labels={'demo':'手机演示','team':'团队联调','review':'Apple 审核'}

    @app.middleware('http')
    async def read_only(request:Request,call_next):
        if request.method not in {'GET','HEAD'}:
            return JSONResponse({'detail':'This dashboard is read-only'},status_code=405,headers={'Allow':'GET, HEAD'})
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'"})
        return response

    @app.api_route('/dashboard/api/info', methods=['GET', 'HEAD'])
    def info():
        return {'mode':'competition','readOnly':True,'pollSeconds':5,'defaultEnvironment':'demo',
                'environments':[{'id':k,'title':v} for k,v in labels.items()]}

    def snapshot_file(filename):
        try:
            p=data/filename
            if p.stat().st_size>10_000_000:raise HTTPException(503,'Snapshot exceeds size limit')
            value=json.loads(p.read_text(encoding='utf-8'))
        except (OSError,ValueError):raise HTTPException(503,'等待服务器采样')
        at=value.get('dataset',{}).get('exportedAt',value.get('at',0))
        age=max(0,time.time()-at)
        if value.get('error'):raise HTTPException(503,'服务器采样暂不可用')
        value.setdefault('coverage',{}).update(ageSeconds=round(age,2),stale=age>20)
        return value

    @app.api_route('/dashboard/api/snapshot', methods=['GET', 'HEAD'])
    def snapshot(environment:str='demo'):
        if environment not in labels:raise HTTPException(422,'Unknown environment')
        return snapshot_file(environment+'.json')

    @app.api_route('/dashboard/api/server', methods=['GET', 'HEAD'])
    def server():return snapshot_file('server.json')

    def archive_path(environment, section):
        if environment not in labels or section not in {'images','replies'}: raise HTTPException(422,'Unknown archive')
        path=data/(environment+'-archive.sqlite3')
        if not path.is_file() or path.is_symlink(): raise HTTPException(503,'全量台账等待采集')
        return path

    @app.get('/dashboard/api/archive/{section}')
    def archive(section:str, environment:str='demo', limit:int=Query(24,ge=1,le=50), cursor:str=Query('',max_length=500),
                query:str=Query('',max_length=200), platform:str=Query('',max_length=20), source:str=Query('',max_length=40),
                device:str=Query('',max_length=120), since:float=Query(0,ge=0,allow_inf_nan=False)):
        import sqlite3
        from .archive import read_page
        path=archive_path(environment,section)
        try: return read_page(path,section,limit=limit,cursor=cursor,query=query,platform=platform,source=source,device=device,since=since)
        except ValueError: raise HTTPException(422,'Invalid page cursor')
        except (OSError,sqlite3.Error): raise HTTPException(503,'台账正在更新，请重试')

    @app.get('/dashboard/api/archive/{section}/export')
    def archive_export(section:str, environment:str='demo', query:str=Query('',max_length=200), platform:str=Query('',max_length=20),
                       source:str=Query('',max_length=40),device:str=Query('',max_length=120),since:float=Query(0,ge=0,allow_inf_nan=False)):
        from .archive import filters, encode
        from .collector import readonly
        path=archive_path(environment,section)
        where, values=filters(section,query=query,platform=platform,source=source,device=device,since=since)
        def lines():
            with readonly(path) as db:
                db.execute('BEGIN')
                for raw, in db.execute('SELECT payload FROM entries WHERE '+where+' ORDER BY at DESC,id DESC',values):
                    yield raw+'\n'
        return StreamingResponse(lines(),media_type='application/x-ndjson',headers={
            'Content-Disposition':f'attachment; filename="{environment}-{section}.jsonl"'})

    @app.get('/dashboard/api/archive-trace/{trace_id}')
    def archive_trace(trace_id:str, environment:str='demo', after:float=Query(0,ge=0,allow_inf_nan=False),
                      after_id:str=Query('',max_length=200), limit:int=Query(50,ge=1,le=100)):
        import re
        from .collector import readonly
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',trace_id): raise HTTPException(422,'Invalid trace')
        path=archive_path(environment,'replies')
        with readonly(path) as db:
            db.execute('BEGIN')
            count=db.execute('SELECT count(*) FROM steps WHERE trace_id=?',(trace_id,)).fetchone()[0]
            rows=db.execute('SELECT at,id,payload FROM steps WHERE trace_id=? AND (at>? OR (at=? AND id>?)) ORDER BY at,id LIMIT ?',
                (trace_id,after,after,after_id,limit+1)).fetchall()
            return {'records':[json.loads(r[2]) for r in rows[:limit]],'total':count,
                'next':{'after':rows[limit-1][0],'after_id':rows[limit-1][1]} if len(rows)>limit else None,
                'historyStatus':'retained_steps_only' if count else 'steps_not_retained_or_not_captured'}

    @app.api_route('/dashboard/api/media/{environment}/{asset_id}', methods=['GET', 'HEAD'])
    def media(environment:str, asset_id:str):
        from .media_assets import ID, MIMES
        if environment not in labels or not ID.fullmatch(asset_id):raise HTTPException(404,'Media unavailable')
        root=data/'media'/environment
        try:
            item=json.loads((root/'manifest.json').read_text())['items'][asset_id]
            mime=item['mime'];extension=MIMES[mime]
            path=root/(asset_id+'.'+extension)
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=item['bytes']:raise ValueError()
        except (OSError,ValueError,KeyError):raise HTTPException(404,'Media no longer in current snapshot')
        return FileResponse(path,media_type=mime,filename='evidence.'+extension,content_disposition_type='inline')

    @app.api_route('/dashboard', methods=['GET', 'HEAD'])
    @app.api_route('/dashboard/', methods=['GET', 'HEAD'])
    @app.api_route('/dashboard/index.html', methods=['GET', 'HEAD'])
    def shell():return FileResponse(web/'index.html')

    @app.api_route('/dashboard/downloads/evidenceguard-website.zip', methods=['GET', 'HEAD'])
    def website():
        path=web/'downloads/evidenceguard-website.zip'
        if not path.is_file():raise HTTPException(404,'Website package not present in this release')
        return FileResponse(path,media_type='application/zip',filename='evidenceguard-website.zip')

    app.mount('/dashboard/assets',StaticFiles(directory=web/'assets'),name='dashboard-assets')
    return app


if os.getenv('EG_DASHBOARD_DATA'):
    app=create_app()
