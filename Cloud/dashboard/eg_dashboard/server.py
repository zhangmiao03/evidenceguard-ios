"""Unprivileged HTTP view of snapshots. No command, model or admin endpoints."""
import json
import os
from pathlib import Path
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
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

    @app.api_route('/dashboard', methods=['GET', 'HEAD'])
    @app.api_route('/dashboard/', methods=['GET', 'HEAD'])
    def shell():return FileResponse(web/'index.html')

    app.mount('/dashboard/assets',StaticFiles(directory=web/'assets'),name='dashboard-assets')
    return app


if os.getenv('EG_DASHBOARD_DATA'):
    app=create_app()
