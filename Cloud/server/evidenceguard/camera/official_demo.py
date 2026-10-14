"""Fixed official Demo AI proxy. Never put the competition model key in Vite."""
from __future__ import annotations

import json
import os
import re

import httpx
from fastapi import HTTPException, Request
from ..ops import model_post, OPERATION

OFFICIAL_AI_URL = 'https://ai-router-cn-pub.anker-in.com/chat/completions'
OFFICIAL_AI_MODEL = 'hackathon/v_model/nova-pro'


def validate_demo_request(data):
    """Accept only the original Demo's ten-frame, single-user vision request."""
    def require(condition):
        if not condition:
            raise ValueError('invalid official Demo request')
    try:
        require(isinstance(data, dict) and set(data) <= {'model', 'messages', 'max_tokens'})
        require(data['model'] == OFFICIAL_AI_MODEL)
        require(type(data.get('max_tokens', 1024)) is int and 1 <= data.get('max_tokens', 1024) <= 2048)
        require(isinstance(data['messages'], list) and len(data['messages']) == 1)
        message = data['messages'][0]
        require(set(message) == {'role', 'content'} and message['role'] == 'user')
        content = message['content']
        require(isinstance(content, list) and 2 <= len(content) <= 11)
        images = texts = 0
        for item in content:
            if item['type'] == 'image_url':
                require(set(item) == {'type', 'image_url'} and set(item['image_url']) == {'url'})
                url = item['image_url']['url']
                require(isinstance(url, str) and len(url) <= 7_000_000)
                require(re.fullmatch(r'data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}', url))
                images += 1
            else:
                require(item['type'] == 'text' and set(item) == {'type', 'text'})
                require(isinstance(item['text'], str) and 1 <= len(item['text']) <= 4000)
                texts += 1
        require(1 <= images <= 10 and texts == 1)
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, '只接受官方 Demo 的 1–10 帧图片与一段分析文字')
    return data


def install_official_demo_routes(app):
    @app.post('/api/sdk/official-ai/chat/completions')
    async def analyze(request: Request):
        key = os.getenv('EG_OFFICIAL_AI_KEY', '')
        if not key:
            raise HTTPException(503, '服务端尚未配置 EG_OFFICIAL_AI_KEY；官方直播和取帧仍可单独检查')
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > 20_000_000:
                raise HTTPException(413, '本次官方 AI 图片请求超过 20 MB')
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, '请求格式不正确')
        data = validate_demo_request(data)
        operation_token = OPERATION.set('official_demo_vision')
        try:
            async with httpx.AsyncClient(timeout=80, follow_redirects=False) as client:
                response = await model_post(client, OFFICIAL_AI_URL, json=data,
                                             headers={'Authorization': f'Bearer {key}'})
                if response.status_code != 200:
                    raise HTTPException(502, f'官方 AI 网关返回 {response.status_code}，请核对赛事模型权限')
                result = response.json()
                # Return only the field consumed by the original Demo. Never
                # forward upstream headers, debug context or model credentials.
                text = result['choices'][0]['message']['content']
                if not isinstance(text, str):
                    raise ValueError('unexpected content')
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise HTTPException(502, '官方 AI 暂不可用，请检查服务端配置与网络')
        finally:
            OPERATION.reset(operation_token)
        return {'choices': [{'message': {'role': 'assistant', 'content': text}}]}
