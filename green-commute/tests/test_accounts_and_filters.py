from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, SessionLocal, engine, ensure_runtime_schema
from app.main import app
from app.models import MerchantCategory, PointTransaction, Product
from test_api import api, client, login, trip


def register(client, username):
    response=client.post('/api/auth/register',json={
        'username':username,'password':'resident-pass-123','display_name':'ignored','role':'admin'
    })
    assert response.status_code==201,response.text
    result=response.json()
    assert result['user']['display_name']==username
    assert result['user']['balance']==0 and result['user']['role']=='resident'
    return result['user'],{'Authorization':'Bearer '+result['access_token']}


def create_merchant(client, admin):
    response=api(client,'post','/api/admin/merchants',admin,{
        'username':'merchant_b','display_name':'第二家店铺','password':'merchant-pass-123'
    })
    assert response.status_code==201,response.text
    return response.json(),login(client,'merchant_b','merchant-pass-123')


def test_two_residents_keep_trip_redemption_refund_and_support_isolated(client):
    _,resident_a=register(client,'resident_a')
    _,resident_b=register(client,'resident_b')
    trip_a=trip(client,resident_a,trip_id='same-client-id',distance='30').json()['trip']
    assert trip(client,resident_a,trip_id='same-client-id',distance='30').json()['balance']==33
    assert api(client,'get','/api/wallet',resident_b).json()['transactions']==[]
    assert api(client,'get',f"/api/trips/{trip_a['id']}",resident_b).status_code==404
    assert trip(client,resident_b,trip_id='same-client-id',distance='20').json()['balance']==22
    snapshot_b=api(client,'get','/api/wallet',resident_b).json()

    order=api(client,'post','/api/redemptions',resident_a,{'product_id':1}).json()['redemption']
    order_path=f"/api/redemptions/{order['id']}"
    assert api(client,'get',order_path,resident_a).status_code==200
    assert api(client,'get',order_path,resident_b).status_code==404
    assert api(client,'post',order_path+'/refund',resident_b).status_code==404
    assert api(client,'get','/api/redemptions',resident_b).json()==[]
    assert api(client,'get','/api/wallet',resident_b).json()==snapshot_b
    assert api(client,'post',order_path+'/refund',resident_a).json()['balance']==33
    assert api(client,'get','/api/wallet',resident_b).json()==snapshot_b
    assert [row['kind'] for row in api(client,'get','/api/wallet',resident_a).json()['transactions']]==[
        'REFUND','REDEEM','TRIP'
    ]
    ticket=api(client,'post','/api/support/tickets',resident_a,{
        'category':'兑换订单','subject':'咨询退款进度','content':'请协助核查刚刚提交的退款。'
    }).json()
    assert api(client,'get','/api/support/tickets',resident_b).json()==[]
    assert api(client,'get',f"/api/support/tickets/{ticket['id']}",resident_b).status_code==404
    assert api(client,'post',f"/api/support/tickets/{ticket['id']}/messages",resident_b,
               {'content':'越权回复'}).status_code==404


def test_two_merchants_cannot_manage_each_others_catalog_or_orders(client):
    admin=login(client,'admin')
    merchant_a=login(client,'merchant')
    _,merchant_b=create_merchant(client,admin)
    resident=login(client)
    categories='/api/merchant/categories'
    assert '交通优惠' in {x['name'] for x in api(client,'get',categories,merchant_a).json()}
    assert api(client,'get',categories,merchant_b).json()==[]
    assert api(client,'post',categories,merchant_a,{'name':'　 '}).status_code==422
    assert api(client,'post',categories,merchant_a,{'name':'  专属品类  '}).json()['name']=='专属品类'
    assert api(client,'post',categories,merchant_a,{'name':'专属品类'}).status_code==409
    assert api(client,'get',categories,merchant_b).json()==[]
    assert api(client,'post',categories,merchant_b,{'name':'专属品类'}).status_code==201
    assert [row['name'] for row in api(client,'get',categories,login(client,'merchant')).json()].count('专属品类')==1

    product=api(client,'post','/api/merchant/products',merchant_b,{
        'name':'第二家礼品','category':'专属品类','cost':5,'stock':4
    }).json()
    endpoint=f"/api/merchant/products/{product['id']}"
    adjustment={'quantity':2,'note':'盘点补货','operation_id':'store-b-stock-1'}
    assert api(client,'patch',endpoint,merchant_a,{'name':'越权修改'}).status_code==404
    assert api(client,'post',endpoint+'/inventory',merchant_a,adjustment).status_code==404
    assert api(client,'get',endpoint+'/inventory',merchant_a).status_code==404
    assert api(client,'post',endpoint+'/inventory',merchant_b,adjustment).json()['product']['stock']==6
    assert api(client,'patch',endpoint,merchant_b,{'active':False}).json()['active'] is False
    assert product['id'] not in {row['id'] for row in api(client,'get','/api/products',resident).json()}
    assert api(client,'patch',endpoint,merchant_b,{'active':True}).status_code==200
    assert api(client,'get','/api/products',merchant_a).status_code==403
    assert api(client,'get','/api/merchants',merchant_b).status_code==403
    trip(client,resident,distance='30')
    order=api(client,'post','/api/redemptions',resident,{'product_id':product['id']}).json()['redemption']
    fulfill=f"/api/merchant/orders/{order['id']}/fulfill"
    assert api(client,'get','/api/merchant/orders',merchant_a).json()==[]
    assert api(client,'post',fulfill,merchant_a).status_code==404
    assert api(client,'post',fulfill,merchant_b).json()['status']=='FULFILLED'


def test_admin_account_updates_invalidate_old_sessions_and_keep_history(client):
    admin=login(client,'admin')
    account,resident=register(client,'resident_manage')
    endpoint=f"/api/admin/accounts/{account['id']}"
    trip(client,resident,distance='30')
    wallet=api(client,'get','/api/wallet',resident).json()
    assert api(client,'get','/api/admin/accounts',resident).status_code==403
    assert api(client,'patch',endpoint,resident,{'enabled':False}).status_code==403
    assert api(client,'patch',endpoint,admin,{'username':'resident_renamed'}).json()['display_name']=='resident_renamed'
    assert api(client,'post',endpoint+'/reset-password',admin,{'password':'replaced-pass-123'}).json()['ok']
    assert api(client,'get','/api/wallet',resident).status_code==401
    updated_session=login(client,'resident_renamed','replaced-pass-123')
    assert api(client,'patch',endpoint,admin,{'enabled':False}).json()['enabled'] is False
    assert api(client,'get','/api/me',updated_session).status_code==401
    assert client.post('/api/auth/login',json={'username':'resident_renamed','password':'replaced-pass-123'}).status_code==401
    filtered=client.get('/api/admin/accounts',headers=admin,params={
        'username':'renamed','role':'resident','enabled':False
    }).json()
    assert [item['id'] for item in filtered]==[account['id']]
    assert api(client,'patch',endpoint,admin,{'enabled':True}).json()['enabled'] is True
    assert api(client,'get','/api/me',updated_session).status_code==401
    assert api(client,'get','/api/wallet',login(client,'resident_renamed','replaced-pass-123')).json()==wallet

    merchant=login(client,'merchant')
    merchant_id=api(client,'get','/api/me',merchant).json()['id']
    assert api(client,'patch',f'/api/admin/accounts/{merchant_id}',admin,{'enabled':False}).status_code==200
    assert api(client,'get','/api/merchant/products',merchant).status_code==401
    assert api(client,'get','/api/products',login(client)).json()==[]


def test_wallet_filters_local_days_and_directions_before_pagination(client):
    resident=login(client)
    trip(client,resident,trip_id='filter-trip-1',distance='30')
    order=api(client,'post','/api/redemptions',resident,{'product_id':1}).json()['redemption']
    api(client,'post',f"/api/redemptions/{order['id']}/refund",resident)
    trip(client,resident,trip_id='filter-trip-2',distance='10')
    with SessionLocal() as db:
        entries=db.scalars(select(PointTransaction).order_by(PointTransaction.id)).all()
        for row,created_at in zip(entries,[
            datetime(2026,1,1,16),datetime(2026,1,2,3),
            datetime(2026,1,2,15,59),datetime(2026,1,2,16)
        ]):
            row.created_at=created_at
        db.commit()

    filters={'start_date':'2026-01-02','end_date':'2026-01-02','timezone':'Asia/Shanghai'}
    income=client.get('/api/wallet',headers=resident,params={**filters,'direction':'income','limit':1}).json()
    assert [entry['kind'] for entry in income['transactions']]==['REFUND']
    assert income['next_before_id'] is not None
    older=client.get('/api/wallet',headers=resident,params={
        **filters,'direction':'income','limit':1,'before_id':income['next_before_id']
    }).json()
    assert [entry['kind'] for entry in older['transactions']]==['TRIP']
    assert older['next_before_id'] is None
    expense=client.get('/api/wallet',headers=resident,params={**filters,'direction':'expense'}).json()
    assert [entry['kind'] for entry in expense['transactions']]==['REDEEM']
    assert expense['balance']==income['balance']==44
    assert expense['transaction_count']==4 and expense['total_earned']==56 and expense['total_spent']==12
    assert client.get('/api/wallet',headers=resident,params={**filters,'timezone':'bad/zone'}).status_code==422
    assert client.get('/api/wallet',headers=resident,params={**filters,'start_date':'2026-01-03'}).status_code==422


@pytest.mark.parametrize('environment,seed_flag',[('development','0'),('production','1')])
def test_startup_without_demo_accounts_or_products(monkeypatch,environment,seed_flag):
    monkeypatch.setenv('ENVIRONMENT',environment)
    monkeypatch.setenv('SEED_DEMO_DATA',seed_flag)
    Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        assert client.get('/api/health').status_code==200
        assert client.post('/api/auth/login',json={'username':'admin','password':'Demo@123456'}).status_code==401
        _,resident=register(client,'first_resident')
        assert api(client,'get','/api/products',resident).json()==[]


def test_category_backfill_is_repeatable(client):
    merchant=login(client,'merchant')
    merchant_id=api(client,'get','/api/me',merchant).json()['id']
    with SessionLocal() as db:
        product=db.get(Product,1)
        product.category='  历史品类  '
        db.commit()
    ensure_runtime_schema()
    ensure_runtime_schema()
    with SessionLocal() as db:
        assert db.get(Product,1).category=='历史品类'
        rows=db.scalars(select(MerchantCategory).where(
            MerchantCategory.merchant_id==merchant_id,MerchantCategory.name=='历史品类')).all()
        assert len(rows)==1
