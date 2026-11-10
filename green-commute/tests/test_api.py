"""Contract, business-rule, security and end-to-end tests against a real SQLite DB."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient

from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Trip,PointTransaction,InventoryMovement,OutboxEvent,Product
from app.services import calculate,process_pending,BusinessError

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ENVIRONMENT','test')
    monkeypatch.setenv('SEED_DEMO_DATA','1')
    monkeypatch.setenv('DEMO_PASSWORD','Demo@123456')
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
    body={'username':'freshperson','password':'very-secure-456'}
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

def test_server_carbon_calculation_contract(client):
    for mode, expected in [('bus', 1100), ('metro', 1400), ('bike', 1800), ('walk', 1800)]:
        r=client.get('/api/carbon/calculate',params={'mode':mode,'distance_km':'10'})
        assert r.status_code==200
        assert r.json()['saved_g']==expected
        assert r.json()['points']==expected//100
    assert client.get('/api/carbon/calculate',params={'mode':'car','distance_km':'10'}).status_code==400

def test_trip_awards_and_ledger(client):
    h=login(client)
    r=trip(client,h)
    assert r.status_code==200 and r.json()['trip']['status']=='AWARDED'
    assert r.json()['trip']['saved_kg']==1.1 and r.json()['trip']['points']==11
    assert r.json()['balance']==11
    w=api(client,'get','/api/wallet',h).json()
    assert w['balance']==11 and len(w['transactions'])==1 and w['transactions'][0]['delta']==11

def test_wallet_summary_snapshots_and_cursor_pagination(client):
    h=login(client)
    trip(client,h,distance='30')  # 33 points
    first=api(client,'get','/api/wallet',h).json()
    assert first['total_earned']==33 and first['total_spent']==0
    assert first['net_change']==33 and first['transaction_count']==1
    assert first['consistent'] is True
    assert first['transactions'][0]['balance_after']==33
    red=api(client,'post','/api/redemptions',h,{'product_id':1})
    assert red.status_code==200
    full=api(client,'get','/api/wallet',h).json()
    assert full['balance']==21 and full['total_earned']==33 and full['total_spent']==12
    assert full['net_change']==21 and full['transaction_count']==2 and full['consistent'] is True
    assert full['transactions'][0]['delta']==-12 and full['transactions'][0]['balance_after']==21
    page=client.get('/api/wallet',headers=h,params={'limit':1}).json()
    assert len(page['transactions'])==1 and page['next_before_id'] is not None
    older=client.get('/api/wallet',headers=h,params={'limit':1,'before_id':page['next_before_id']}).json()
    assert len(older['transactions'])==1 and older['transactions'][0]['delta']==33

def test_redemption_refund_returns_points_stock_and_auditable_entry(client):
    h=login(client)
    trip(client,h,distance='30')  # 33 points
    before_stock=client.get('/api/products',headers=h).json()[0]['stock']
    red=api(client,'post','/api/redemptions',h,{'product_id':1}).json()['redemption']
    assert api(client,'get','/api/wallet',h).json()['balance']==21
    refund=api(client,'post',f"/api/redemptions/{red['id']}/refund",h)
    assert refund.status_code==200 and refund.json()['redemption']['status']=='REFUNDED'
    assert refund.json()['redemption']['refunded_at'] is not None
    assert refund.json()['balance']==33
    assert client.get('/api/products',headers=h).json()[0]['stock']==before_stock
    wallet=api(client,'get','/api/wallet',h).json()
    assert wallet['total_earned']==45 and wallet['total_spent']==12
    assert wallet['transactions'][0]['kind']=='REFUND'
    assert wallet['transactions'][0]['delta']==12 and wallet['transactions'][0]['balance_after']==33
    assert wallet['consistent'] is True
    with SessionLocal() as db:
        movements=db.query(InventoryMovement).filter_by(product_id=1).order_by(InventoryMovement.id).all()
        assert [m.kind for m in movements[-2:]]==['REDEMPTION','REFUND']
        assert movements[-2].quantity==-1 and movements[-1].quantity==1
    again=api(client,'post',f"/api/redemptions/{red['id']}/refund",h)
    assert again.status_code==200 and again.json()['balance']==33
    assert api(client,'get','/api/wallet',h).json()['transaction_count']==3

def test_refund_is_closed_after_merchant_fulfillment(client):
    resident=login(client);merchant=login(client,'merchant')
    trip(client,resident,distance='50')
    red=api(client,'post','/api/redemptions',resident,{'product_id':1}).json()['redemption']
    assert api(client,'post',f"/api/merchant/orders/{red['id']}/fulfill",merchant).status_code==200
    assert api(client,'post',f"/api/redemptions/{red['id']}/refund",resident).status_code==409

def test_zero_point_trip_does_not_create_fake_ledger_entry(client):
    h=login(client)
    r=trip(client,h,mode='walk',distance='0.01')
    assert r.json()['trip']['status']=='AWARDED'
    wallet=api(client,'get','/api/wallet',h).json()
    assert wallet['balance']==0 and wallet['transaction_count']==0
    assert wallet['transactions']==[] and wallet['consistent'] is True

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
    assert client.get('/api/products',headers=h).json()[0]['stock']==39

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
    assert red['can_refund'] is True and red['updated_at'] is not None
    orders=api(client,'get','/api/merchant/orders',m).json()
    assert len(orders)==1 and orders[0]['settlement_status']=='PENDING'
    assert api(client,'post',f'/api/admin/settlements/{rid}/settle',a).status_code==409
    fulfilled=api(client,'post',f'/api/merchant/orders/{rid}/fulfill',m)
    assert fulfilled.status_code==200 and fulfilled.json()['fulfilled_at'] is not None
    assert api(client,'post',f'/api/admin/settlements/{rid}/settle',a).status_code==200
    assert api(client,'post',f'/api/admin/settlements/{rid}/settle',a).status_code==200
    assert api(client,'get','/api/admin/settlements',a).json()[0]['status']=='SETTLED'
    order=api(client,'get','/api/redemptions',r).json()[0]
    assert order['status']=='FULFILLED' and order['fulfilled_at'] is not None and order['can_refund'] is False

def test_merchant_can_publish_product(client):
    m=login(client,'merchant')
    payload={'name':'环保补贴券','description':'活动演示','category':'交通优惠','icon':'gift','cost':3,'stock':2}
    assert api(client,'post','/api/merchant/products',m,payload).status_code==201
    assert any(x['name']=='环保补贴券' for x in client.get('/api/products',headers=login(client)).json())

def test_inventory_module_tracks_opening_adjustment_and_product_lifecycle(client):
    merchant=login(client,'merchant')
    products=api(client,'get','/api/merchant/products',merchant).json()
    product=next(x for x in products if x['id']==1)
    history=api(client,'get','/api/merchant/products/1/inventory',merchant).json()
    assert history['product']['stock']==40
    assert history['movements'][0]['kind']=='OPENING'
    adjust=api(client,'post','/api/merchant/products/1/inventory',merchant,{
        'operation_id':'restock-product-1','quantity':5,'note':'补充演示库存'})
    assert adjust.status_code==200 and adjust.json()['product']['stock']==45
    again=api(client,'post','/api/merchant/products/1/inventory',merchant,{
        'operation_id':'restock-product-1','quantity':5,'note':'重复提交应幂等'})
    assert again.status_code==200 and again.json()['product']['stock']==45
    update=api(client,'patch','/api/merchant/products/1',merchant,{'name':'地铁单程体验券·更新版','active':False})
    assert update.status_code==200 and update.json()['active'] is False
    assert not any(x['id']==1 for x in client.get('/api/products',headers=login(client)).json())
    reactivate=api(client,'patch','/api/merchant/products/1',merchant,{'active':True})
    assert reactivate.status_code==200 and any(x['id']==1 for x in client.get('/api/products',headers=login(client)).json())
    assert api(client,'get','/api/merchant/products/1/inventory',login(client)).status_code==403

def test_inventory_adjustment_rejects_zero_and_overdraft(client):
    merchant=login(client,'merchant')
    assert api(client,'post','/api/merchant/products/1/inventory',merchant,{
        'operation_id':'zero-stock-op','quantity':0,'note':'无效变更'}).status_code==422
    assert api(client,'post','/api/merchant/products/1/inventory',merchant,{
        'operation_id':'too-large-op','quantity':-41,'note':'超过现有库存'}).status_code==409

def test_admin_can_create_merchant_and_filter_catalog(client):
    admin=login(client,'admin')
    created=api(client,'post','/api/admin/merchants',admin,{
        'username':'newmerchant','display_name':'新商户','password':'merchant-pass-1'
    })
    assert created.status_code==201 and created.json()['role']=='merchant'
    assert api(client,'post','/api/admin/merchants',admin,{
        'username':'newmerchant','display_name':'重复商户','password':'merchant-pass-1'
    }).status_code==409
    merchants=api(client,'get','/api/admin/merchants',admin).json()
    new=next(x for x in merchants if x['display_name']=='新商户')
    merchant=login(client,'newmerchant','merchant-pass-1')
    product=api(client,'post','/api/merchant/products',merchant,{
        'name':'新商户礼品','description':'测试商品','category':'生活好物','icon':'gift','cost':5,'stock':3
    })
    assert product.status_code==201
    all_products=client.get('/api/products',headers=login(client)).json()
    filtered=client.get('/api/products',headers=login(client),params={'merchant_id':new['id']}).json()
    assert any(p['name']=='新商户礼品' for p in all_products)
    assert [p['name'] for p in filtered]==['新商户礼品']

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
