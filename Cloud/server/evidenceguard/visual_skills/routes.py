from fastapi import Request
from .schema import Create, Interpret, Revision, Selection, Analyze


def install_scene_routes(app, scenes, client, analysis_client=None):
    @app.get('/api/visual-scenes')
    async def listing(request: Request):
        return [scenes.public(s) for s in scenes.list_all(client(request))]

    @app.post('/api/visual-scenes', status_code=202)
    async def create(body: Create, request: Request):
        return scenes.public(await scenes.create(client(request), body))

    @app.get('/api/visual-scenes/{key}')
    async def read(key: str, request: Request):
        return scenes.public(scenes.get(key, client(request)))

    @app.post('/api/visual-scenes/{key}/interpret', status_code=202)
    async def interpret(key: str, body: Interpret, request: Request):
        return scenes.public(scenes.interpret(key, client(request), body))

    @app.post('/api/visual-scenes/{key}/frame')
    async def frame(key: str, body: Revision, request: Request):
        return scenes.public(await scenes.frame(key, client(request), body.revision))

    @app.post('/api/visual-scenes/{key}/sample-analysis')
    async def sample_analysis(key: str, body: Revision, request: Request):
        owner=(analysis_client or client)(request)
        return await scenes.sample_endpoints(key,owner,body.revision)

    @app.post('/api/visual-scenes/{key}/selection')
    async def selection(key: str, body: Selection, request: Request):
        return scenes.public(scenes.select(key, client(request), body))

    @app.post('/api/visual-scenes/{key}/activate')
    async def activate(key: str, body: Revision, request: Request):
        return scenes.public(await scenes.activate(key, client(request), body.revision))

    @app.post('/api/visual-scenes/{key}/pause')
    async def pause(key: str, body: Revision, request: Request):
        return scenes.public(scenes.pause(key, client(request), body.revision))

    @app.post('/api/visual-scenes/{key}/analyze')
    async def analyze(key: str, body: Analyze, request: Request):
        return await scenes.analyze_endpoints(key, (analysis_client or client)(request), body.revision, include_depth=body.includeDepth)
