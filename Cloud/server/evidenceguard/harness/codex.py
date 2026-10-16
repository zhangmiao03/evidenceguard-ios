"""Official Codex App Server turns, with host-owned tools and durable app history.

One isolated stdio process/thread per run. Codex owns the Responses/tool loop;
the host receives dynamic-tool requests and supplies its existing scoped receipts.
No shell, filesystem, web, plugins, goals or subagents are available to the model.
The small complete() adapter preserves the host's deadlines, step budget and
receipt validation; it never makes a model request itself or falls back silently.
"""
from __future__ import annotations

import asyncio
import ast
from collections import deque
import json
import os
from pathlib import Path
import signal
import tempfile

from .providers import ProviderError

EXECUTOR = 'codex-app-server-v1'
PINNED_VERSION = '0.162.1'


def toml_value(value):
    if isinstance(value, dict):
        return '{' + ', '.join(k + ' = ' + toml_value(v) for k, v in value.items()) + '}'
    return json.dumps(value, ensure_ascii=False)


def structured_text(text):
    """Normalize representation only; the host still validates the full schema.

    Some custom Responses gateways ignore strict output format. Accept a whole
    JSON object, one JSON fence, or a data-only Python literal. Never execute
    code, extract a convenient substring, or invent missing decision fields.
    """
    if len(text)>16000: raise ProviderError('主动评估输出超出长度限制。')
    text=text.strip()
    if text.startswith('```json\n') and text.endswith('\n```'): text=text[8:-4]
    try:
        try: value=json.loads(text)
        except ValueError: value=ast.literal_eval(text)
        def data_only(v):
            if isinstance(v,dict):return all(isinstance(k,str) and data_only(x) for k,x in v.items())
            if isinstance(v,list):return all(data_only(x) for x in v)
            return type(v) in {str,int,float,bool,type(None)}
        if not isinstance(value,dict) or not data_only(value): raise ValueError()
        return json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError,SyntaxError,RecursionError) as error:
        raise ProviderError('主动评估格式无效，未发布消息。') from error


class CodexTurn:
    def __init__(self, provider, *, event=lambda kind, value: None, binary=None, runtime_root=None, output_schema=None):
        self.provider = provider
        self.binary = binary or os.getenv('EG_CODEX_BINARY', '')
        self.runtime_root = runtime_root or os.getenv('EG_CODEX_RUNTIME_DIR', '')
        self.event = event
        self.output_schema = output_schema
        self.process = None
        self.directory = None
        self.pending = None
        self.offset = 0
        self.sequence = 0
        self.queue = deque()
        self.thread_id = None
        self.turn_id = None
        self.final_text = ''
        self.finished = False

    async def __aenter__(self):
        if not self.binary or not Path(self.binary).is_file() or not self.runtime_root:
            raise ProviderError('Codex 执行器尚未配置，请联系团队。')
        Path(self.runtime_root).mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory = tempfile.TemporaryDirectory(prefix='turn-', dir=self.runtime_root)
        root = self.directory.name
        config = {
            'model': self.provider.model,
            'model_provider': 'doubao',
            'model_providers.doubao': dict(name='Doubao', base_url=self.provider.base_url,
                env_key='EG_CODEX_MODEL_KEY', wire_api='responses', requires_openai_auth=False,
                supports_websockets=False, request_max_retries=0, stream_max_retries=0),
            'web_search': 'disabled',
            'model_reasoning_summary': 'none',
            'features.skip_host_skill_discovery': True,
        }
        for name in ('shell_tool', 'shell_snapshot', 'apps', 'hooks', 'multi_agent',
                     'image_generation', 'view_image', 'skill_search', 'skill_mcp_dependency_install',
                     'code_mode', 'code_mode_host', 'goals', 'default_mode_request_user_input'):
            config['features.' + name] = False
        command = [self.binary]
        for key, value in config.items():
            command.extend(['-c', key + '=' + toml_value(value)])
        command.append('app-server')
        # Never inherit cloud credentials, APNs secrets, the host's Codex login,
        # project files, user config, MCP servers or shell startup environment.
        env = dict(PATH='/usr/bin:/bin', HOME=root, CODEX_HOME=root,
                   EG_CODEX_MODEL_KEY=self.provider.key, RUST_LOG='error')
        try:
            self.process = await asyncio.create_subprocess_exec(*command, cwd=root, env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=True, limit=4*1024*1024)
            await self.request('initialize', dict(clientInfo=dict(name='evidenceguard',
                title='anker cloud runtime', version='1'), capabilities=dict(experimentalApi=True)))
            await self.send(dict(method='initialized'))
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except asyncio.TimeoutError:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await self.process.wait()
        if self.directory:
            self.directory.cleanup()
            self.directory = None

    async def send(self, value):
        self.process.stdin.write((json.dumps(value, ensure_ascii=False) + '\n').encode())
        await self.process.stdin.drain()

    async def read(self):
        line = await self.process.stdout.readline()
        if not line:
            raise ProviderError('Codex 执行进程中断，请重试；没有自动启用任务。')
        try:
            return json.loads(line)
        except (ValueError, TypeError) as error:
            raise ProviderError('Codex 执行器响应格式异常，请重试。') from error

    async def request(self, method, params):
        self.sequence += 1
        rid = self.sequence
        await self.send(dict(id=rid, method=method, params=params))
        while True:
            value = await self.read()
            if value.get('id') == rid and 'method' not in value:
                if 'error' in value:
                    # Upstream error bodies can contain request data or credentials.
                    raise ProviderError('Codex 执行器请求失败，请联系团队或稍后重试。')
                return value['result']
            self.queue.append(value)

    async def complete(self, messages, tools):
        if self.finished:
            raise ProviderError('Codex 本轮已结束，请重新发送。')
        if not self.thread_id:
            instructions = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
            instructions += '\n只使用本轮提供的业务工具。需要澄清时直接用普通中文回复，不使用 request_user_input。不要创建目标、计划或编程任务。'
            result = await self.request('thread/start', dict(
                model=self.provider.model, modelProvider='doubao', allowProviderModelFallback=False,
                cwd=self.directory.name, approvalPolicy='never', sandbox='read-only',
                ephemeral=True, environments=[], baseInstructions=instructions,
                dynamicTools=[dict(type='function', name=t['function']['name'],
                    description=t['function']['description'], inputSchema=t['function']['parameters'],
                    deferLoading=False) for t in tools]))
            self.thread_id = result['thread']['id']
            # Preserve message roles. User/assistant history is never promoted to
            # system instructions, and only the host's scoped history is injected.
            history = [m for m in messages if m['role'] in {'user', 'assistant'}]
            if history and messages[-1]['role'] == 'user':
                latest = history.pop()['content']
            else:
                latest = '请依据本轮授权来源完成评估。'
            if history:
                await self.request('thread/inject_items', dict(threadId=self.thread_id,
                    items=[dict(type='message', role=m['role'], content=[dict(
                        type='output_text' if m['role']=='assistant' else 'input_text',
                        text=m['content'])]) for m in history]))
            if not isinstance(latest, str):
                raise ProviderError('本轮输入格式不支持。')
            params=dict(threadId=self.thread_id, input=[dict(type='text', text=latest)], environments=[])
            if self.output_schema is not None: params['outputSchema']=self.output_schema
            result = await self.request('turn/start', params)
            self.turn_id = result['turn']['id']
            self.event('executor_started', dict(executor=EXECUTOR, version=PINNED_VERSION,
                       threadId=self.thread_id, turnId=self.turn_id))
        elif self.pending:
            callback = self.pending
            additions = messages[self.offset:]
            receipt = next((m for m in additions if m['role']=='tool'
                            and m['tool_call_id']==callback['params']['callId']), None)
            if receipt is None:
                raise ProviderError('Codex 工具回执缺失，已停止本轮。')
            content = [dict(type='inputText', text=receipt['content'])]
            for message in additions:
                if message['role']=='system':
                    content.append(dict(type='inputText', text=message['content']))
                if message['role']=='user' and isinstance(message['content'], list):
                    for part in message['content']:
                        if part['type']=='text': content.append(dict(type='inputText', text=part['text']))
                        elif part['type']=='image_url': content.append(dict(type='inputImage', imageUrl=part['image_url']['url']))
            try:
                payload=json.loads(receipt['content'])
                failed=isinstance(payload,dict) and (bool(payload.get('error')) or payload.get('status') in {'failed','unsupported'})
            except ValueError:
                failed=False
            await self.send(dict(id=callback['id'], result=dict(success=not failed, contentItems=content)))
            self.pending = None
        else:
            raise ProviderError('Codex 本轮状态异常，已停止。')
        self.offset = len(messages)
        while True:
            value = self.queue.popleft() if self.queue else await self.read()
            method = value.get('method')
            params = value.get('params', {})
            if 'id' in value and method:
                if method != 'item/tool/call':
                    await self.send(dict(id=value['id'], error=dict(code=-32601, message='Unsupported host operation')))
                    raise ProviderError('本轮请求了未开放的操作，已停止；请直接描述你的需求。')
                names = {t['function']['name'] for t in tools}
                if (params.get('threadId')!=self.thread_id or params.get('turnId')!=self.turn_id
                        or params.get('tool') not in names or params.get('namespace')
                        or not isinstance(params.get('arguments'), dict)):
                    await self.send(dict(id=value['id'], result=dict(success=False,
                        contentItems=[dict(type='inputText', text='Tool is outside the frozen run scope')])) )
                    raise ProviderError('Codex 请求超出了本轮工具权限，已停止。')
                self.pending = value
                return dict(role='assistant', content=None, tool_calls=[dict(id=params['callId'],
                    type='function', function=dict(name=params['tool'],
                    arguments=json.dumps(params['arguments'], ensure_ascii=False)))])
            if method == 'item/completed' and params.get('item', {}).get('type')=='agentMessage':
                item = params['item']
                if item.get('phase') != 'commentary': self.final_text = item.get('text', '')
            if method == 'thread/tokenUsage/updated':
                usage = params.get('tokenUsage', {}).get('last', {})
                self.event('executor_usage', {k:v for k,v in usage.items() if isinstance(v, (int,float))})
            if method == 'turn/completed':
                self.finished = True
                if params.get('turn', {}).get('status') != 'completed' or not self.final_text:
                    raise ProviderError('Codex 本轮执行未完成，请重试；没有自动启用任务。')
                self.event('executor_completed', dict(executor=EXECUTOR, version=PINNED_VERSION))
                return dict(role='assistant', content=structured_text(self.final_text) if self.output_schema is not None else self.final_text)
