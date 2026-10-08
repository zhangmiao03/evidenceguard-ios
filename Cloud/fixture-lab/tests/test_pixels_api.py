import time
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.domain import new_task
from backend.simulator import render
from backend.vision import analyze, read_stamp


@pytest.mark.parametrize('scene,camera,expected',[
    ('normal','cam-a','inside'),('normal','cam-b','inside'),
    ('moved','cam-a','outside'),('moved','cam-b','outside'),
    ('occluded_a','cam-a','unknown'),('occluded_a','cam-b','inside'),
    ('hidden_both','cam-a','unknown'),('hidden_both','cam-b','unknown'),
    ('lookalike','cam-a','unknown'),('lookalike','cam-b','unknown')])
def test_inference_from_actual_pixels(scene,camera,expected):
    now=time.time()
    image=render(camera,scene,now,12)
    observation=analyze(image,dict(frame_id='test',device_id=camera,captured_at=now,received_at=now,revision=1),new_task(now))
    assert observation.relation==expected
    t,g=read_stamp(image)
    assert abs(t-now)<.0011 and g==12


def test_api_validates_roi_and_revision_and_persists(tmp_path):
    with TestClient(create_app(tmp_path,False)) as client:
        state=client.get('/api/state').json()
        payload={'title':'箱子测试','roi':state['task']['roi'],'revision':1}
        assert client.post('/api/task',json=payload).status_code==200
        assert client.post('/api/task',json=payload).status_code==409
        payload['revision']=2
        payload['roi']['cam-a']=[0,0,4,1]
        assert client.post('/api/task',json=payload).status_code==422
        assert client.post('/api/simulation',json={'scenario':'made-up'}).status_code==422
        assert client.post('/api/task/action',json={'action':'pause'}).status_code==200
    with TestClient(create_app(tmp_path,False)) as client:
        task=client.get('/api/state').json()['task']
        assert task['title']=='箱子测试' and task['revision']==2 and task['lifecycle']=='paused'
        events=client.get('/api/events').json()
        assert len(events)==2
        assert len(client.get('/api/events?after='+str(events[-1]['sequence'])).json())==1


def test_cross_origin_mutation_rejected(tmp_path):
    with TestClient(create_app(tmp_path,False)) as client:
        assert client.post('/api/simulation',json={'scenario':'moved'},headers={'Origin':'https://unrelated.example'}).status_code==403
        assert client.get('/api/frames/not-a-frame.jpg').status_code==404
