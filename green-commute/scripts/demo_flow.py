"""Record a real, repeatable HTTP business chain into docs/evidence/demo_flow.json."""
import json, os
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
import requests
BASE=os.getenv('DEMO_BASE_URL','http://127.0.0.1:8000')
steps=[]
def call(label,method,path,token=None,body=None):
    headers={'Authorization':'Bearer '+token} if token else {}
    r=requests.request(method,BASE+path,headers=headers,json=body,timeout=12)
    d=r.json();steps.append({'step':label,'method':method,'path':path,'status':r.status_code,'response':d})
    if r.status_code not in (200,201):raise RuntimeError(f'{label}: HTTP {r.status_code}: {d}')
    return d

def login(role):return call('登录'+role,'POST','/api/auth/login',body={'username':role,'password':os.getenv('DEMO_PASSWORD','Demo@123456')})['access_token']

if __name__=='__main__':
    resident=login('resident')
    trip=call('提交30km公交','POST','/api/trips',resident,{'client_trip_id':'sample-'+uuid4().hex[:14],'mode':'bus','distance_km':'30'})
    same=call('读取积分余额','GET','/api/wallet',resident)
    red=call('兑换12积分商品','POST','/api/redemptions',resident,{'product_id':1})
    merchant=login('merchant')
    rid=red['redemption']['id']
    call('商户查询订单','GET','/api/merchant/orders',merchant)
    call('商户核销','POST',f'/api/merchant/orders/{rid}/fulfill',merchant)
    admin=login('admin')
    call('管理员清算','POST',f'/api/admin/settlements/{rid}/settle',admin)
    final=call('查询最终积分流水','GET','/api/wallet',resident)
    call('全站统计','GET','/api/admin/stats',admin)
    # Do not put signed authentication tokens into an evidence artifact.
    for s in steps:
        
        if isinstance(s['response'],dict): s['response'].pop('access_token',None)
    result={'run_utc':datetime.now(timezone.utc).isoformat(),'note':'Actual local HTTP calls; no external transport/payment validation.','steps':steps,
        'this_trip_issued':trip['trip']['points'],'this_redemption_cost':red['redemption']['points'],
        'balance_after':final['balance'],'ledger_net':sum(t['delta'] for t in final['transactions'])}
    dest=Path('docs/evidence/demo_flow.json');dest.parent.mkdir(exist_ok=True,parents=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('Saved',dest,'trip points',trip['trip']['points'],'redeem cost',red['redemption']['points'],'final balance',final['balance'])
