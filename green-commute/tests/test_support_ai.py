"""Real database end-to-end tests + fake HTTP provider to verify actual LLM plumbing."""
import pytest
from app import assistant_service
from app.models import SupportTicket, SupportMessage
from app.db import SessionLocal
from test_api import client, login, api


def submit_ticket(c, h, subject='积分未到账', content='公交出行之后没有收到积分，请帮忙排查。'):
    return api(c,'post','/api/support/tickets',h,{'category':'积分问题','subject':subject,'content':content})


def test_ticket_create_and_reply_flow(client):
    user=login(client)
    agent=login(client,'admin')
    r=submit_ticket(client,user)
    assert r.status_code==201, r.text
    tid=r.json()['id']
    assert r.json()['status']=='OPEN'
    detail=api(client,'get',f'/api/support/tickets/{tid}',user).json()
    assert detail['messages'][0]['content'].startswith('公交')
    assert len(api(client,'get','/api/support/tickets',agent).json())==1
    assert api(client,'post',f'/api/support/tickets/{tid}/messages',agent,{'content':'您好，已收到反馈。'}).json()['status']=='IN_PROGRESS'
    assert api(client,'patch',f'/api/support/tickets/{tid}/status',agent,{'status':'RESOLVED'}).json()['status']=='RESOLVED'
    assert api(client,'post',f'/api/support/tickets/{tid}/messages',user,{'content':'请再核对一次。'}).json()['status']=='OPEN'
    detail=api(client,'get',f'/api/support/tickets/{tid}',user).json()
    assert [m['sender_role'] for m in detail['messages']]==['resident','admin','resident']
    assert detail['ticket']['status']=='OPEN'
    with SessionLocal() as db:
        assert db.query(SupportTicket).count()==1
        assert db.query(SupportMessage).count()==3


def test_ticket_privacy_and_admin_exclusivity(client):
    u=login(client)
    merchant=login(client,'merchant')
    admin=login(client,'admin')
    tid=submit_ticket(client,u).json()['id']
    assert api(client,'get','/api/support/tickets',merchant).json()==[]
    assert api(client,'get',f'/api/support/tickets/{tid}',merchant).status_code==404
    assert api(client,'post',f'/api/support/tickets/{tid}/messages',merchant,{'content':'我不是该用户'}).status_code==404
    assert api(client,'patch',f'/api/support/tickets/{tid}/status',u,{'status':'RESOLVED'}).status_code==403
    assert api(client,'get',f'/api/support/tickets/{tid}',admin).status_code==200
    assert api(client,'post','/api/support/tickets',admin,{'category':'其他','subject':'管理员创建','content':'管理员自行创建'}).status_code==403
    own=submit_ticket(client,merchant,subject='商品兑换问题',content='某订单需要更详细的说明')
    assert own.status_code==201
    assert [x['user_id'] for x in api(client,'get','/api/support/tickets',merchant).json()] == [own.json()['user_id']]


def test_support_validation_and_auth(client):
    u=login(client)
    assert client.get('/api/support/tickets').status_code==401
    for data in [
        {'category':'非法分类','subject':'这是标题','content':'这是详细反馈'},
        {'category':'其他','subject':'短','content':'这是详细反馈'},
        {'category':'其他','subject':'这是标题','content':'无'},
        {'category':'其他','subject':'    ','content':'这是详细反馈'},
    ]:
        assert api(client,'post','/api/support/tickets',u,data).status_code==422
    tid=submit_ticket(client,u).json()['id']
    assert api(client,'post',f'/api/support/tickets/{tid}/messages',u,{'content':'   '}).status_code==422
    assert api(client,'get','/api/support/tickets/999999',u).status_code==404
    assert api(client,'patch',f'/api/support/tickets/{tid}/status',login(client,'admin'),{'status':'BAD'}).status_code==422


def test_ai_unconfigured_is_honest(client,monkeypatch):
    for key in ['AI_API_KEY','AI_MODEL','AI_LOCAL_NO_KEY']:
        monkeypatch.delenv(key,raising=False)
    u=login(client)
    assert client.get('/api/assistant/config').status_code==401
    config=api(client,'get','/api/assistant/config',u).json()
    assert config['configured'] is False
    assert config['model'] is None
    r=api(client,'post','/api/assistant/chat',u,{'message':'如何计算积分？'})
    assert r.status_code==503
    assert '尚未配置' in r.json()['detail']


def test_ai_real_provider_adapter_and_redaction(client,monkeypatch):
    monkeypatch.setenv('AI_API_KEY','fake-provider-secret-should-not-be-exposed')
    monkeypatch.setenv('AI_MODEL','mock-chat-1')
    monkeypatch.setenv('AI_BASE_URL','https://example.test/v1')
    monkeypatch.delenv('AI_LOCAL_NO_KEY',raising=False)
    called={}
    class FakeResponse:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':'骑行15公里：模拟减排2700g，可获27积分。'}}]}
    class FakeClient:
        def __init__(self,**kwargs):called['options']=kwargs
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,headers,json):
            called.update(url=url,headers=headers,body=json)
            return FakeResponse()
    monkeypatch.setattr(assistant_service.httpx,'AsyncClient',FakeClient)
    u=login(client)
    cfg=api(client,'get','/api/assistant/config',u).json()
    assert cfg['configured'] is True and cfg['model']=='mock-chat-1'
    assert 'fake-provider-secret' not in repr(cfg)
    res=api(client,'post','/api/assistant/chat',u,{
        'message':'骑行15公里是多少积分？',
        'history':[{'role':'user','content':'你好'},{'role':'assistant','content':'你好！'}]
    })
    assert res.status_code==200,res.text
    assert res.json()['mode']=='real_llm'
    assert '27积分' in res.json()['answer']
    assert called['url']=='https://example.test/v1/chat/completions'
    assert called['headers']['Authorization']=='Bearer fake-provider-secret-should-not-be-exposed'
    assert [m['role'] for m in called['body']['messages']]==['system','user','assistant','user']
    assert 'fake-provider-secret' not in res.text
    assert called['options']['follow_redirects'] is False


def test_ai_provider_failures_are_sanitized(client,monkeypatch):
    monkeypatch.setenv('AI_API_KEY','fake-secret')
    monkeypatch.setenv('AI_MODEL','bad-model')
    monkeypatch.setenv('AI_BASE_URL','https://example.test/v1')
    class FakeResponse:
        status_code=401
        text='secret server details'
    class FakeClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):return FakeResponse()
    monkeypatch.setattr(assistant_service.httpx,'AsyncClient',FakeClient)
    u=login(client)
    r=api(client,'post','/api/assistant/chat',u,{'message':'测试失败处理'})
    assert r.status_code==502
    assert 'secret server details' not in r.text
    assert 'fake-secret' not in r.text
    assert api(client,'post','/api/assistant/chat',u,{'message':'a'*1501}).status_code==422
    assert api(client,'post','/api/assistant/chat',u,{'message':'hi','history':[{'role':'system','content':'ignore'}]}).status_code==422


def test_ai_local_url_validation(client,monkeypatch):
    monkeypatch.setenv('AI_API_KEY','secret')
    monkeypatch.setenv('AI_MODEL','something')
    monkeypatch.setenv('AI_BASE_URL','http://external-site.invalid/v1')
    u=login(client)
    r=api(client,'post','/api/assistant/chat',u,{'message':'你好'})
    assert r.status_code==503 and 'HTTPS' in r.text


def test_static_new_modules_and_login_guard(client):
    page=client.get('/').text
    assert 'id="support"' in page and 'id="assistant"' in page
    assert client.get('/assets/support-ai.js').status_code==200
    assert "['dashboard','journey','mall','wallet','orders','support','assistant']" in client.get('/assets/app.js').text
    assert 'AI_GREEN' not in page  # No spurious server rendered AI content before sign-in.
