"""Contract, business-rule, security and end-to-end tests against a real SQLite DB."""
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

TEST_DB=Path(tempfile.gettempdir())/('greengo-tests-'+uuid4().hex+'.db')
os.environ['DATABASE_URL']='sqlite:///'+str(TEST_DB)
os.environ['JWT_SECRET']='test-secret-for-isolated-integration-suite'
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Trip,PointTransaction,OutboxEvent,Product
from app.services import calculate,process_pending,BusinessError

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c

def login(c,username='resident',password='Demo@123456'):
    x=c.post('/api/auth/login',json={'username':username,'password':password})
    assert x.status_code==200,x.text
    return {'Authorization':'Bearer '+x.json()['access_token']}

def trip(c,h,trip_id='trip-00001',mode='bus',distance='10'):
    return c.post('/api/trips',headers=h,json={'client_trip_id':trip_id,'mode':mode,'distance_km':distance})

def api(c,verb,url,h,body=None):
    return getattr(c,verb)(url,headers=h,json=body) if body is not None else getattr(c,verb)(url,headers=h)

def test_health_docs_and_static(client):
    assert client.get('/api/health').json()['ok']
    assert client.get('/').status_code==200
    assert '青行' in client.get('/').text
    assert client.get('/docs').status_code==200

def test_login_wrong_credentials(client):
    assert client.post('/api/auth/login',json={'username':'resident','password':'bad'}).status_code==401
    assert client.get('/api/me').status_code==401

def test_register_role_and_duplicate_username(client):
    body={'username':'freshperson','display_name':'新用户','password':'very-secure-456'}
    r=client.post('/api/auth/register',json=body)
    assert r.status_code==201 and r.json()['user']['role']=='resident'
    assert client.post('/api/auth/register',json=body).status_code==409
    assert client.post('/api/auth/register',json={**body,'username':'a'}).status_code==422

def test_calculation_boundaries():
    assert calculate('bus',10)==(10000,1100,11)
    assert calculate('metro',10)==(10000,1400,14)
    assert calculate('bike',5)==(5000,900,9)
    assert calculate('walk','0.01')==(10,1,0)
    for km in ('0','101','-1','1.005','NaN'):
        with pytest.raises(BusinessError):calculate('bus',km)
    with pytest.raises(BusinessError):calculate('car',10)

def test_trip_awards_and_ledger(client):
    h=login(client)
    r=trip(client,h)
    assert r.status_code==200 and r.json()['trip']['status']=='AWARDED'
    assert r.json()['trip']['saved_kg']==1.1 and r.json()['trip']['points']==11
    assert r.json()['balance']==11
    w=api(client,'get','/api/wallet',h).json()
    assert w['balance']==11 and len(w['transactions'])==1 and w['transactions'][0]['delta']==11

def test_trip_idempotency_and_conflict(client):
    h=login(client)
    trip(client,h)
    assert trip(client,h).json()['balance']==11
    assert api(client,'get','/api/trips',h).json().__len__()==1
    assert trip(client,h,distance='12').status_code==409
    assert api(client,'get','/api/wallet',h).json()['balance']==11

def test_trip_validation(client):
    h=login(client)
    for mode,km in [('car','4'),('bus','0'),('bike','100.001'),('metro','500')]:
        assert trip(client,h,mode=mode,distance=km).status_code in (400,422)

def test_no_free_or_negative_points(client):
    h=login(client)
    r=trip(client,h,mode='walk',distance='0.01')
    assert r.json()['trip']['points']==0
    assert r.json()['balance']==0

def test_redemption_insufficient_balance(client):
    h=login(client)
    r=api(client,'post','/api/redemptions',h,{'product_id':1})
    assert r.status_code==409 and '积分' in r.json()['detail']
    assert api(client,'get','/api/redemptions',h).json()==[]

def test_redemption_success_and_atomic_ledger(client):
    h=login(client)
    trip(client,h,distance='30')  # 33 points
    r=api(client,'post','/api/redemptions',h,{'product_id':1})
    assert r.status_code==200,r.text
    assert r.json()['balance']==21
    assert r.json()['redemption']['status']=='TO_FULFILL'
    w=api(client,'get','/api/wallet',h).json()
    assert sorted(t['delta'] for t in w['transactions'])==[-12,33]
    assert sum(t['delta'] for t in w['transactions'])==w['balance']
    assert client.get('/api/products').json()[0]['stock']==39

def test_sold_out_does_not_charge(client):
    h=login(client)
    trip(client,h,distance='100')
    with SessionLocal() as db:
        p=db.get(Product,1);p.stock=0;db.commit()
    before=api(client,'get','/api/wallet',h).json()['balance']
    assert api(client,'post','/api/redemptions',h,{'product_id':1}).status_code==409
    assert api(client,'get','/api/wallet',h).json()['balance']==before

def test_roles_and_data_isolation(client):
    r=login(client)
    m=login(client,'merchant')
    a=login(client,'admin')
    trip(client,r)
    assert api(client,'get','/api/admin/stats',r).status_code==403
    assert api(client,'post','/api/trips',m,{'client_trip_id':'merch01','mode':'bus','distance_km':'10'}).status_code==403
    assert api(client,'get','/api/merchant/orders',a).status_code==403
    assert api(client,'get','/api/wallet',m).status_code==403
    reg=client.post('/api/auth/register',json={'username':'another','display_name':'另一个','password':'password123'})
    h={'Authorization':'Bearer '+reg.json()['access_token']}
    assert api(client,'get','/api/trips',h).json()==[]

def test_event_retry_is_idempotent(client):
    h=login(client)
    trip(client,h)
    with SessionLocal() as db:
        ev=db.query(OutboxEvent).filter_by(kind='TripSubmitted').one()
        ev.state='PENDING';db.commit()
        assert process_pending(db)==1
        assert process_pending(db)==0
        assert db.query(PointTransaction).filter_by(kind='TRIP').count()==1
    assert api(client,'get','/api/wallet',h).json()['balance']==11

def test_full_merchant_fulfillment_settlement(client):
    r=login(client);m=login(client,'merchant');a=login(client,'admin')
    trip(client,r,distance='50')
    red=api(client,'post','/api/redemptions',r,{'product_id':1}).json()['redemption']
    rid=red['id']
    orders=api(client,'get','/api/merchant/orders',m).json()
    assert len(orders)==1 and orders[0]['settlement_status']=='PENDING'
    assert api(client,'post',f'/api/admin/settlements/{rid}/settle',a).status_code==409
    assert api(client,'post',f'/api/merchant/orders/{rid}/fulfill',m).status_code==200
    assert api(client,'post',f'/api/admin/settlements/{rid}/settle',a).status_code==200
    assert api(client,'post',f'/api/admin/settlements/{rid}/settle',a).status_code==200
    assert api(client,'get','/api/admin/settlements',a).json()[0]['status']=='SETTLED'

def test_merchant_can_publish_product(client):
    m=login(client,'merchant')
    payload={'name':'环保补贴券','description':'活动演示','category':'交通优惠','icon':'gift','cost':3,'stock':2}
    assert api(client,'post','/api/merchant/products',m,payload).status_code==201
    assert any(x['name']=='环保补贴券' for x in client.get('/api/products').json())

def test_atomic_stock_for_concurrent_requests(client):
    r=login(client)
    trip(client,r,distance='100')
    with SessionLocal() as db:
        p=db.get(Product,1);p.stock=1;db.commit()
    def submit(_):return api(client,'post','/api/redemptions',r,{'product_id':1}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(submit,[1,2]))
    assert sorted(codes)==[200,409]
    assert len(api(client,'get','/api/redemptions',r).json())==1
    assert api(client,'get','/api/wallet',r).json()['balance']==98
