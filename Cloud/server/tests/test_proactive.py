import asyncio
import json
import time
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.personal import PersonalAgent, Preferences
from evidenceguard.proactive import ProactiveEngine
from test_harness import ScriptedProvider, environment, tool


def setup(tmp_path):
    provider=ScriptedProvider([])
    store,runtime=environment(tmp_path,provider)
    personal=PersonalAgent(store); engine=ProactiveEngine(personal,runtime)
    client=str(uuid4()); engine.bind(client,'chat-demo')
    personal.preferences(client,Preferences(enabled=True,quietStart=0,quietEnd=0))
    skill=store.create_draft('测试箱子',['cam-b'])
    skill.update(status='active',alert='open',result='outside',resultReason='已存观察显示目标离区')
    store.save_skill(skill); store.event(skill['id'],'alert_opened',{})
    return provider,store,runtime,personal,engine,client,skill


def answers(provider,skill,action='send',before=None):
    items=iter([tool('read_proactive_context',{}),dict(role='assistant',content=json.dumps(dict(
        valueScore=85 if action=='send' else 20,title='包裹观察有变化',body='已有观察显示目标离区，请查看证据确认。',reason='检测到新事件，有待用户核对',sourceIds=['skill:'+skill['id']]),ensure_ascii=False))])
    async def complete(messages,schemas):
        result=next(items)
        if result.get('content') and before: before()
        return result
    provider.complete=AsyncMock(side_effect=complete)


def test_event_generates_independent_message_receipts_and_deduplicates(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path); answers(p,skill)
        before=s.skills(); personal.tick(); await e.step()
        message=e.messages(c)[0]
        assert message['role']=='assistant' and message['origin']=='proactive'
        assert s.runs('chat-demo')==[]  # no fabricated user turn
        assert s.skills()==before
        run=s.run(message['runId'])
        assert run['clientId']==c and run['initiator']=='agent'
        assert set(run['executionContract']['allowed_tools'])=={'read_proactive_context','read_observation_image'}
        assert run['toolReceipts'][0]['sourceIds']
        personal.tick(); await e.step()
        assert len(e.messages(c))==1 and p.complete.await_count==2
        assert e.messages(str(uuid4()))==[]
        s.close()
    asyncio.run(check())


@pytest.mark.parametrize('change',['disabled','resolved','new_episode','context'])
def test_changes_while_model_runs_revalidate_before_publication(tmp_path,change):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        def modify():
            if change=='disabled': personal.preferences(c,Preferences(enabled=False))
            elif change=='resolved': skill.update(alert='none',result='inside'); s.save_skill(skill)
            elif change=='new_episode': s.event(skill['id'],'alert_opened',{})
            else: personal.preferences(c,Preferences(enabled=True,quietStart=0,quietEnd=0,timezone='Asia/Shanghai'))
        answers(p,skill,before=modify); personal.tick(); await e.step()
        assert e.messages(c)==[]
        assert e.activity(c)[0]['status']==('retry' if change=='context' else 'cancelled')
        s.close()
    asyncio.run(check())


def test_quiet_and_rate_policy_do_not_wake_model(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        now=time.time(); e.enqueue(c,'manual','schedule','概况','已存任务记录',now)
        personal.preferences(c,Preferences(enabled=True,dailySummary=True,quietStart=0,quietEnd=23))
        # 12:00 UTC, a known quiet period
        quiet=1780315200
        with s.transaction(): s.db.execute('UPDATE proactive_jobs SET due=?',(quiet,))
        await e.step(quiet)
        assert e.activity(c)[0]['status']=='deferred'; p.complete.assert_not_awaited()
        s.close()
    asyncio.run(check())


def test_restart_recovers_read_only_job_without_double_publication(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path); personal.tick()
        with s.transaction(): s.db.execute("UPDATE proactive_jobs SET status='running'")
        recovered=ProactiveEngine(personal,r); answers(p,skill)
        await recovered.step(); assert len(recovered.messages(c))==1
        again=ProactiveEngine(personal,r); personal.tick(); await again.step()
        assert len(again.messages(c))==1 and p.complete.await_count==2
        s.close()
    asyncio.run(check())


def test_silent_decision_and_failure_have_visible_activity_without_message(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path); answers(p,skill,'silent')
        personal.tick(); await e.step()
        assert e.messages(c)==[] and e.activity(c)[0]['status']=='silent'
        now=time.time(); e.enqueue(c,'another','coverage','画面无法确认','需复查',now,skill['id'])
        skill.update(result='unknown'); s.save_skill(skill)
        p.complete=AsyncMock(side_effect=RuntimeError('provider secret must not leak'))
        for offset in [0,31,92]: await e.step(now+offset)
        assert e.activity(c)[0]['status']=='failed'
        assert 'secret' not in str(e.activity(c)) and e.messages(c)==[]
        s.close()
    asyncio.run(check())


def test_feedback_controls_followup_without_changing_camera_truth(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path); answers(p,skill)
        now=time.time(); personal.tick(now); await e.step(now)
        m=e.messages(c)[0]; e.feedback(c,m['id'],'handled')
        personal.tick(now+301); await e.step(now+301)
        assert len(e.messages(c))==1 and s.skill(skill['id'])['alert']=='open'
        with pytest.raises(KeyError): e.feedback(str(uuid4()),m['id'],'handled')
        e.feedback(c,m['id'],'snooze'); e.feedback(c,m['id'],'snooze')
        assert sum(a['kind']=='revisit' for a in e.activity(c))==1
        answers(p,skill); await e.step(now+3602)
        assert len(e.messages(c))==2
        s.close()
    asyncio.run(check())


def test_autonomous_coverage_trigger_waits_and_deduplicates(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        skill.update(alert='none',result='unknown'); s.save_skill(skill)
        event=s.event(skill['id'],'result_changed',{})
        personal.tick(event['at']+59); assert e.activity(c)==[]
        personal.tick(event['at']+61); assert e.activity(c)[0]['kind']=='coverage'
        answers(p,skill); await e.step(event['at']+61)
        personal.tick(event['at']+900)
        assert len(e.activity(c))==1
        s.close()
    asyncio.run(check())


def test_proactive_tools_reject_device_effects_and_unknown_image_sources(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        p.answers=iter([tool('request_camera_snapshot',{'device_id':'cam-b'}),tool('read_observation_image',{'source_id':'other-home'}),tool('read_proactive_context',{}),dict(role='assistant',content=json.dumps(dict(valueScore=20,reason='无新证据',sourceIds=[])))])
        before=s.skills(); personal.tick(); await e.step()
        run=s.runs()[-1]
        assert [x['status'] for x in run['toolReceipts']]==['failed','failed','completed']
        assert s.skills()==before and e.messages(c)==[]
        s.close()
    asyncio.run(check())


def test_conversation_and_explicit_reply_are_installation_scoped(tmp_path):
    p=ScriptedProvider([dict(role='assistant',content='我会先核对这条提醒。')])
    app=create_app(tmp_path/'api.sqlite',start_worker=False,provider=p)
    a,b=str(uuid4()),str(uuid4())
    with TestClient(app) as client:
        client.headers['X-EG-Installation-ID']=a
        assert client.put('/api/personal/conversation',json={'conversationId':'my-chat'}).status_code==200
        client.headers['X-EG-Installation-ID']=b
        assert client.get('/api/agent/conversations/my-chat').status_code==404
        assert client.put('/api/personal/conversation',json={'conversationId':'my-chat'}).status_code==409
        client.headers['X-EG-Installation-ID']=a
        response=client.post('/api/agent/runs',json={'conversationId':'my-chat','requestId':'r','message':'继续','replyToMessageId':'unknown'})
        assert response.status_code==404 and p.complete.await_count==0


def test_new_sampling_does_not_starve_message_but_state_change_does(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        def new_sample():
            skill['lastObservedAt']=time.time(); s.save_skill(skill)
        answers(p,skill,before=new_sample); personal.tick(); await e.step()
        assert len(e.messages(c))==1
        # Updating just sampling time must not invalidate an immutable old source.
        personal.read(c,e.messages(c)[0]['id'])
        assert e.messages(c)[0]['read'] is True
        s.close()
    asyncio.run(check())


def test_stored_image_receipt_and_multicall_protocol(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_MODEL_VISION','1')
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        key='a'*64
        from types import SimpleNamespace
        r.visual_review=SimpleNamespace(review=AsyncMock(return_value=dict(status='completed',review={'visible':'测试画面','uncertainties':'单帧'})))
        p.answers=iter([tool('read_proactive_context',{}),tool('read_observation_image',{'source_id':'evidence:test'}),
                        dict(role='assistant',content=json.dumps(dict(valueScore=90,title='测试',body='测试画面需核对',reason='读取图片完成',sourceIds=['evidence:test'])))])
        source=dict(clientId=c,sources=[dict(id='evidence:test',type='camera_evidence',observedAt=1,sourceType='fixture',imageUrl='/api/media/'+key)])
        decision=await r.proactive('image-run',source)
        assert decision.valueScore==90
        r.visual_review.review.assert_awaited_once()
        receipt=s.run('image-run')['toolReceipts'][-1]
        assert receipt==dict(tool='read_observation_image',status='completed',sourceIds=['evidence:test'],review={'visible':'测试画面','uncertainties':'单帧'})
        assert 'image bytes' not in json.dumps(s.run('image-run'))
        s.close()
    asyncio.run(check())


def test_positive_reply_preserves_proactive_context_without_fake_user_message(tmp_path):
    p=ScriptedProvider([dict(role='assistant',content='先查看该事件的已存证据。')])
    app=create_app(tmp_path/'reply.sqlite',start_worker=False,provider=p)
    client_id=str(uuid4())
    with TestClient(app) as client:
        client.headers['X-EG-Installation-ID']=client_id
        client.put('/api/personal/conversation',json={'conversationId':'main-chat'})
        message=dict(id='m1',jobId='j1',role='assistant',origin='proactive',createdAt=time.time(),body='包裹观察有变化，请核对',why='已有观察回执',sources=[],feedback=None)
        with app.state.store.transaction():
            app.state.store.db.execute('INSERT INTO assistant_messages VALUES (?,?,?,?,?)',('m1',client_id,'j1',time.time(),json.dumps(message)))
        response=client.post('/api/agent/runs',json={'conversationId':'main-chat','requestId':'follow','message':'下一步怎么做','replyToMessageId':'m1'})
        assert response.status_code==202
        run=app.state.store.run('follow')
        assert run['message']=='下一步怎么做'
        assert run['personalContext']['replyToMessage']['id']=='m1'
        assert len(app.state.store.runs('main-chat'))==1
        response=client.post('/api/agent/runs',json={'conversationId':'main-chat','requestId':'follow','message':'下一步怎么做'})
        assert response.status_code==409


def test_vision_review_normalizes_bounded_points_without_accepting_arbitrary_json():
    from evidenceguard.video.providers import ImageReview
    result=ImageReview.model_validate({'visible':['门口有纸箱','画面有行人'],'uncertainties':['不能确认拿走动作']})
    assert result.visible=='门口有纸箱；画面有行人'
    for bad in [{'visible':{'command':'activate'},'uncertainties':'unknown'},
                {'visible':['a']*13,'uncertainties':'unknown'},
                {'visible':['a',1],'uncertainties':'unknown'},
                {'visible':'x'*1001,'uncertainties':'unknown'}]:
        with pytest.raises(ValueError): ImageReview.model_validate(bad)


def test_model_cannot_select_delivery_or_bypass_score_policy(tmp_path):
    from evidenceguard.proactive import Decision
    for value in [dict(valueScore=100,reason='发送',action='send'),dict(valueScore='90',reason='高分'),dict(valueScore=101,reason='超范围')]:
        with pytest.raises(ValueError): Decision.model_validate(value)
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        p.answers=iter([tool('read_proactive_context',{}),dict(role='assistant',content=json.dumps(dict(valueScore=65,title='稍后汇总',body='已有记录',reason='非即时事项',sourceIds=['skill:'+skill['id']])))])
        personal.tick(); await e.step()
        assert not e.messages(c) and e.activity(c)[0]['status']=='digest'
        s.close()
    asyncio.run(check())


def test_same_skill_events_merge_without_extra_message_or_losing_evidence(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path); now=time.time()
        answers(p,skill); personal.tick(now); await e.step(now)
        first=e.messages(c)[0]
        s.event(skill['id'],'alert_opened',{})
        answers(p,skill); personal.tick(now+15); await e.step(now+15)
        messages=e.messages(c)
        assert len(messages)==1 and messages[0]['id']==first['id']
        assert messages[0]['mergedCount']==2 and messages[0]['createdAt']==first['createdAt']
        assert e.activity(c)[0]['status']=='merged'
        assert s.skill(skill['id'])['alert']=='open'
        s.close()
    asyncio.run(check())


def test_policy_rechecks_after_model_and_reuses_assessment_after_deferral(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        # A second task publishes while the model is running. It must enforce
        # the minimum gap, then reuse the saved assessment instead of paying again.
        now=time.time()
        def concurrent_message():
            message=dict(id='other',createdAt=now,read=False,sources=[],kind='event')
            with s.transaction(): s.db.execute('INSERT INTO assistant_messages VALUES (?,?,?,?,?)',('other',c,'other-job',now,json.dumps(message)))
        answers(p,skill,before=concurrent_message); personal.tick(now); await e.step(now)
        assert len(e.messages(c))==1 and e.activity(c)[0]['status']=='deferred'
        await e.step(now+301)
        assert len(e.messages(c))==2 and p.complete.await_count==2
        message=e.messages(c)[-1]; assert s.run(message['runId']) is not None
        s.close()
    asyncio.run(check())


def test_daily_cap_preserves_evidence_and_does_not_invoke_model(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path); now=time.time()
        with s.transaction():
            for n in range(6):
                m=dict(id=str(n),createdAt=now,read=False,sources=[],mergeKey='unrelated-'+str(n))
                s.db.execute('INSERT INTO assistant_messages VALUES (?,?,?,?,?)',(str(n),c,'job'+str(n),now,json.dumps(m)))
        p.complete=AsyncMock()
        personal.tick(now); await e.step(now+10)
        p.complete.assert_not_awaited()
        assert len(e.messages(c))==6 and e.activity(c)[0]['status']=='deferred'
        assert s.skill(skill['id'])['alert']=='open'
        s.close()
    asyncio.run(check())


def test_subscribed_daily_summary_can_deliver_midscore_digest(tmp_path):
    async def check():
        p,s,r,personal,e,c,skill=setup(tmp_path)
        personal.preferences(c,Preferences(enabled=True,dailySummary=True,quietStart=0,quietEnd=0))
        key=e.enqueue(c,'daily-test','schedule','每日概况','用户已订阅的每日概况',time.time())
        items=iter([tool('read_proactive_context',{}),dict(role='assistant',content=json.dumps(dict(valueScore=60,title='今日观察概况',body='已有任务记录需要核对，不能证明全天覆盖。',reason='用户订阅的定时概况，有中等价值的已记录变化',sourceIds=['skill:'+skill['id']]),ensure_ascii=False))])
        p.complete=AsyncMock(side_effect=lambda messages,schemas: next(items))
        await e.step()
        assert e.activity(c)[0]['status']=='sent'
        message=e.messages(c)[0]
        assert message['valueScore']==60 and message['kind']=='schedule'
        assert message['delivery']=='in_app'
        assert s.skill(skill['id'])['alert']=='open'  # A summary never acknowledges an alarm.
        s.close()
    asyncio.run(check())
