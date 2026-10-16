import asyncio
import json
import socket
from unittest.mock import AsyncMock
from uuid import uuid4
import httpx
import pytest
from evidenceguard.external_sources import PublicSources, public_target
from evidenceguard.connectors import Connectors
from evidenceguard.feishu_cli import FeishuCLI, FeishuRead, command
from evidenceguard.harness.tools import ToolRegistry
from evidenceguard.store import Store


def test_public_url_rejects_private_mixed_and_credentials(monkeypatch):
    async def check():
        loop=asyncio.get_running_loop()
        for addresses in [['127.0.0.1'],['169.254.169.254'],['93.184.216.34','10.0.0.1'],['::1']]:
            monkeypatch.setattr(loop,'getaddrinfo',AsyncMock(return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in addresses]))
            with pytest.raises(ValueError): await public_target('https://example.com/a')
        for url in ['file:///etc/passwd','http://localhost/a','https://user:pass@example.com','https://example.com:22/a']:
            with pytest.raises(ValueError): await public_target(url)
    asyncio.run(check())


def test_public_read_pins_ip_and_rechecks_redirect(monkeypatch):
    async def check():
        resolver=AsyncMock(return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))])
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',resolver)
        s=PublicSources(); calls=[]
        def serve(req):
            calls.append(req)
            assert req.url.host=='93.184.216.34' and req.headers['host']=='example.com'
            assert req.extensions['sni_hostname']=='example.com'
            if req.url.path=='/bad': return httpx.Response(302,headers={'location':'http://127.0.0.1/secrets'})
            return httpx.Response(200,headers={'content-type':'text/html'},text='<p>预报日期：2026-10-16</p><script>do evil()</script><p>小雨</p>')
        s.transport=httpx.MockTransport(serve)
        result=await s.read('https://example.com/good')
        assert result['url']=='https://example.com/good' and '小雨' in result['text'] and 'evil' not in result['text']
        async def dns(host,*a,**k):
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(host if host=='127.0.0.1' else '93.184.216.34',443))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',dns)
        with pytest.raises(ValueError): await s.read('https://example.com/bad')
        assert len(calls)==2  # no redirected private request
    asyncio.run(check())


def test_search_failure_and_weather_do_not_invent_forecast():
    async def check():
        s=PublicSources()
        s.transport=httpx.MockTransport(lambda req:httpx.Response(429,json={'code':429}))
        with pytest.raises(ValueError): await s.search('天气')
        s.search=AsyncMock(return_value={'results':[{'url':'https://unrelated.test','title':'上海下雨','snippet':'雨'}]})
        s.read=AsyncMock()
        result=await s.weather('杭州','tomorrow','Asia/Shanghai')
        assert result['place']=='杭州' and result['status']=='unavailable' and not result['sources']
        s.read.assert_not_awaited()
        assert '杭州' in s.search.call_args.args[0]
        with pytest.raises(ValueError): await s.weather('杭州市1单元101室')
    asyncio.run(check())


def test_public_tools_do_not_require_camera_or_inherit_another_installation(tmp_path):
    s=Store(tmp_path/'sources.sqlite'); c=Connectors(s)
    tools=c.tools(ToolRegistry(),str(uuid4()))
    assert {'web_search','fetch_url','get_weather'} <= set(tools.names)
    assert 'read_feishu_context' not in tools.names
    assert 'send_message' not in tools.names
    s.close()


def test_cli_read_commands_cannot_choose_shell_or_write():
    from pydantic import ValidationError
    with pytest.raises(ValidationError): FeishuRead(area='send')
    with pytest.raises(ValidationError): FeishuRead(area='read_document',resource_id='../private')
    args=command(FeishuRead(area='search_messages',query='$(echo secret) --yes'), 'Asia/Shanghai')
    assert args[:2]==['im','+messages-search']
    assert '--query=$(echo secret) --yes' in args and '--yes' not in args


def test_cli_per_user_credentials_output_contract_and_limits(tmp_path,monkeypatch):
    from cryptography.fernet import Fernet
    import time
    async def check():
        monkeypatch.setenv('EG_CONNECTOR_ENCRYPTION_KEY',Fernet.generate_key().decode())
        monkeypatch.setenv('EG_FEISHU_CLIENT_ID','test-app')
        binary=tmp_path/'fake-cli'
        # A subprocess fixture verifies actual argv/env and bounded output behavior.
        binary.write_text('#!/usr/bin/env python3\nimport os,json,sys\nassert "--as=user" in sys.argv\nassert "EG_ACCESS_TOKEN" not in os.environ\nprint(json.dumps({"ok":True,"identity":"user","data":{"value":os.environ["LARKSUITE_CLI_USER_ACCESS_TOKEN"]}}))\n')
        binary.chmod(0o700); monkeypatch.setenv('EG_FEISHU_CLI_BINARY',str(binary))
        monkeypatch.setenv('EG_ACCESS_TOKEN','should-not-be-inherited')
        s=Store(tmp_path/'cli.sqlite'); c=Connectors(s)
        for client,token in [('a','account-a-token'),('b','account-b-token')]:
            with s.transaction(): s.db.execute('INSERT INTO connector_tokens VALUES (?,?,?)',(client,'feishu_cli',c.vault().encrypt(json.dumps({'access_token':token,'expires_at':time.time()+100}).encode()).decode()))
        for client in ['a','b']:
            result=await c.feishu_cli.run(client,'Asia/Shanghai',area='tasks')
            assert result['externalContent'] and 'account-' not in result['text']
        with pytest.raises(ValueError): await c.feishu_cli.run('other','Asia/Shanghai',area='tasks')
        binary.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"ok":True,"identity":"bot","data":{}}))\n')
        with pytest.raises(ValueError,match='用户身份'): await c.feishu_cli.run('a','Asia/Shanghai',area='tasks')
        binary.write_text('#!/usr/bin/env python3\nprint("x"*300000)\n')
        with pytest.raises(ValueError,match='资料过多'): await c.feishu_cli.run('a','Asia/Shanghai',area='tasks')
        s.close()
    asyncio.run(check())


def test_cli_oauth_is_separate_from_legacy_feishu_and_rejects_partial_scope(tmp_path,monkeypatch):
    import sys
    from cryptography.fernet import Fernet
    from evidenceguard.connectors import OAuthFinish
    from evidenceguard.feishu_cli import SCOPES
    from urllib.parse import parse_qs, urlsplit
    async def check():
        monkeypatch.setenv('EG_CONNECTOR_ENCRYPTION_KEY',Fernet.generate_key().decode())
        monkeypatch.setenv('EG_CONNECTOR_ORIGIN','https://example.test')
        monkeypatch.setenv('EG_FEISHU_CLIENT_ID','test-app')
        monkeypatch.setenv('EG_FEISHU_CLIENT_SECRET','private-test-secret')
        monkeypatch.setenv('EG_FEISHU_CLI_BINARY',sys.executable)
        s=Store(tmp_path/'oauth.sqlite'); c=Connectors(s); client=str(uuid4())
        request=c.begin(client,'feishu_cli')
        params=parse_qs(urlsplit(request['url']).query)
        assert params['redirect_uri']==['https://example.test/api/connectors/oauth/callback/feishu_cli']
        assert 'mail:user_mailbox.message.body:read' in params['scope'][0]
        assert not any(x in SCOPES for x in [':write',':send',':delete'])
        c.transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'code':0,'access_token':'private-access','scope':'offline_access','expires_in':3600}))
        with pytest.raises(ValueError): await c.finish(client,'feishu_cli',OAuthFinish(state=request['state'],code='code'))
        assert not any(p['connected'] for p in c.snapshot(client))
        request=c.begin(client,'feishu_cli')
        c.transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'code':0,'access_token':'private-access','scope':SCOPES,'expires_in':3600}))
        await c.finish(client,'feishu_cli',OAuthFinish(state=request['state'],code='code'))
        assert {p['id'] for p in c.snapshot(client) if p['connected']}=={'feishu_cli'}
        assert 'private-access' not in s.db.execute('SELECT cipher FROM connector_tokens').fetchone()[0]
        assert 'read_feishu_context' in c.tools(ToolRegistry(),client).names
        await c.disconnect(client,'feishu_cli')
        assert 'read_feishu_context' not in c.tools(ToolRegistry(),client).names
        s.close()
    asyncio.run(check())
