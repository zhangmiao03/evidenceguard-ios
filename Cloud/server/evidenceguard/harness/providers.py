from __future__ import annotations
import os
from typing import Protocol
import httpx
from ..ops import traced, model_post

class ProviderError(RuntimeError):
    pass

class ModelProvider(Protocol):
    name: str
    ready: bool
    async def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...

class OpenAICompatibleProvider:
    """Provider protocol only; credentials never enter tool arguments or events."""
    def __init__(self):
        self.base_url = os.getenv("EG_MODEL_BASE_URL", "").rstrip("/")
        self.model = os.getenv("EG_MODEL_ID", "")
        self.key = os.getenv("EG_MODEL_API_KEY", "")
        self.name = self.model or "not-configured"
        self.ready = bool(self.base_url and self.model and self.key)

    @traced('chat')
    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        return await self._request(messages, {"tools": tools, "tool_choice": "auto"} if tools else {})

    @traced('memory')
    async def extract_memory(self, messages: list[dict]) -> dict:
        # Bounded fact extraction does not need a reasoning transcript. Keep the
        # same configured model; ordinary conversation/tool settings are untouched.
        options = {"response_format": {"type": "json_object"}}
        if self.model.startswith('doubao-'):
            options['thinking'] = {"type": "disabled"}
        return await self._request(messages, options)

    async def _request(self, messages: list[dict], options: dict) -> dict:
        if not self.ready:
            raise ProviderError("模型 API 尚未配置，请在服务端填写地址、模型 ID 和密钥。")
        try:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                response = await model_post(client, self.base_url + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.key},
                    json={"model": self.model, "messages": messages, "stream": False,
                          **options})
            if response.status_code >= 400:
                raise ProviderError(f"模型服务返回 HTTP {response.status_code}，请检查服务端配置或额度。")
            value = response.json()["choices"][0]["message"]
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except ProviderError:
            raise
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as error:
            raise ProviderError("模型请求超时或响应格式不兼容，请重试。") from error
