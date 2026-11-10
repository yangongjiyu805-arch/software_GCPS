"""Green Commute Points – runnable REST API and bundled responsive web client."""
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os
import jwt
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import case, select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db,SessionLocal,ensure_runtime_schema
from .models import (User, Trip, Product, MerchantCategory, InventoryMovement, PointTransaction, Redemption, Settlement,
                     OutboxEvent, EmissionRule, SupportTicket, SupportMessage, utcnow)
from .assistant_service import configuration, query_model
from .security import create_token, decode_token, hash_password,verify_password
from .services import (BusinessError, submit_trip,redeem,refund_redemption,process_pending,stats,serial_user,
                       serial_inventory_movement,adjust_inventory,backfill_inventory_opening,
                       serial_trip,serial_trip_detail,serial_product,serial_redemption,serial_settlement,
                       serial_point_transaction,ledger_summary,backfill_ledger_snapshots,
                       fulfill_redemption,settle_redemption,calculate_with_factors,ensure_default_rule,
                       get_active_rule,rule_snapshot,create_emission_rule,account_name)

Username=Annotated[str,Field(min_length=3,max_length=48,pattern=r'^[a-zA-Z0-9_]+$')]
Password=Annotated[str,Field(min_length=8,max_length=128)]
StoreName=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=80)]
CategoryName=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=40)]
ManagedRole=Literal['resident','merchant']

class LoginIn(BaseModel):
    username: str
    password: str
class RegisterIn(BaseModel):
    username: Username
    password: Password
class MerchantCreateIn(BaseModel):
    username: Username
    display_name: StoreName
    password: Password
class AccountUpdateIn(BaseModel):
    username: Username|None=None
    display_name: StoreName|None=None
    enabled: bool|None=None
class PasswordResetIn(BaseModel):
    password: Password
class CategoryIn(BaseModel):
    name: CategoryName
class TripIn(BaseModel):
    client_trip_id: str=Field(min_length=6,max_length=72,pattern=r'^[a-zA-Z0-9_-]+$')
    mode: str
    distance_km: Decimal
    source: Literal['manual','simulated','imported','partner']='simulated'
    evidence_reference: str|None=Field(default=None,max_length=120)
class EmissionRuleIn(BaseModel):
    version: str=Field(min_length=1,max_length=32,pattern=r'^[a-zA-Z0-9._-]+$')
    name: str=Field(min_length=2,max_length=120)
    baseline_g_per_km: int=Field(ge=1,le=1000)
    points_per_kg: int=Field(ge=1,le=100)
    mode_g_per_km: dict[str,int]
class ProductIn(BaseModel):
    name: str=Field(min_length=2,max_length=90)
    description: str=Field(default='',max_length=300)
    category: CategoryName='生活好物'
    icon: str=Field(default='gift',max_length=16)
    cost: int=Field(ge=1,le=100000)
    stock: int=Field(ge=0,le=100000)
class ProductUpdateIn(BaseModel):
    name: str|None=Field(default=None,min_length=2,max_length=90)
    description: str|None=Field(default=None,max_length=300)
    category: CategoryName|None=None
    icon: str|None=Field(default=None,max_length=16)
    cost: int|None=Field(default=None,ge=1,le=100000)
    active: bool|None=None
class InventoryAdjustIn(BaseModel):
    operation_id: str=Field(min_length=6,max_length=72,pattern=r'^[a-zA-Z0-9_-]+$')
    quantity: int=Field(ge=-100000,le=100000)
    note: str=Field(min_length=2,max_length=200)
class FulfillIn(BaseModel):
    status: str=Field(pattern='^(FULFILLED)$')

# Support-center and AI request schemas: strongly validated at the API edge.
class TicketCreateIn(BaseModel):
    category: Literal['积分问题', '行程问题', '兑换订单', '账号帮助', '其他']
    subject: str=Field(min_length=4,max_length=100)
    content: str=Field(min_length=5,max_length=2000)

class TicketMessageIn(BaseModel):
    content: str=Field(min_length=1,max_length=2000)

class TicketStatusIn(BaseModel):
    status: Literal['OPEN', 'IN_PROGRESS', 'RESOLVED']

class ChatTurn(BaseModel):
    role: Literal['user','assistant']
    content: str=Field(min_length=1,max_length=1500)

class AssistantChatIn(BaseModel):
    message: str=Field(min_length=1,max_length=1500)
    history: list[ChatTurn]=Field(default_factory=list,max_length=8)

def _seed(db):
    if db.scalar(select(func.count()).select_from(User)):
        return
    users={}
    for username,name,role in [('resident','林同学','resident'),('merchant','青禾商户','merchant'),('admin','平台管理员','admin')]:
        u=User(username=username,display_name=name,role=role,password_hash=hash_password(os.getenv('DEMO_PASSWORD','Demo@123456')))
        db.add(u);db.flush();users[role]=u
    catalog=[
        ('地铁单程体验券','可用于一次城市轨道交通体验（演示商品）','交通优惠','train',12,40),
        ('城市骑行体验券','绿色骑行主题礼券（演示商品）','绿色出行','bike',25,25),
        ('可循环帆布袋','环保材质，日常购物可重复使用','环保好物','bag',35,30),
        ('城市绿植盲盒','桌面绿植兑换凭证（演示商品）','生活好物','plant',55,16),
        ('低碳咖啡券','自带杯享受咖啡福利（演示商品）','生活好物','coffee',18,45),
        ('公益植树证书','模拟公益植树参与电子凭证','公益捐赠','leaf',80,50),
    ]
    for category in sorted({item[2] for item in catalog}):
        db.add(MerchantCategory(merchant_id=users['merchant'].id,name=category))
    for name,desc,cat,icon,cost,stock in catalog:
        db.add(Product(merchant_id=users['merchant'].id,name=name,description=desc,category=cat,icon=icon,cost=cost,stock=stock))
    db.commit()

@asynccontextmanager
async def lifespan(app:FastAPI):
    production=os.getenv('ENVIRONMENT')=='production'
    if production and (os.getenv('JWT_SECRET','') in ('','local-dev-secret-REPLACE-BEFORE-DEPLOYMENT')):
        raise RuntimeError('Set a strong JWT_SECRET before production deployment')
    ensure_runtime_schema()
    with SessionLocal() as db:
        if not production and os.getenv('SEED_DEMO_DATA')=='1':
            _seed(db)
        ensure_default_rule(db)
        process_pending(db)
        backfill_ledger_snapshots(db)
        backfill_inventory_opening(db)
    yield

app=FastAPI(title='城市绿色出行积分系统',description='碳减排模拟、积分商城、客服工单与可选真实大模型',version='1.2.0',lifespan=lifespan)

@app.middleware('http')
async def prevent_api_caching(request,call_next):
    response=await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(BusinessError)
async def business_handler(_,exc:BusinessError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code,content={'detail':exc.message})

bearer_auth=HTTPBearer(auto_error=False)

def current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer_auth),db:Session=Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=401,detail='请先登录')
    try:
        user_id,session_version=decode_token(credentials.credentials)
        u=db.get(User,user_id)
        if not u or not u.enabled or u.session_version!=session_version:
            raise ValueError()
        return u
    except (jwt.PyJWTError,ValueError,TypeError,KeyError):
        raise HTTPException(status_code=401,detail='登录已过期，请重新登录')

def require_role(*roles):
    def wrapped(u:User=Depends(current_user)):
        if u.role not in roles:raise HTTPException(status_code=403,detail='无权限执行该操作')
        return u
    return wrapped

@app.get('/api/health')
def health():return {'ok':True,'service':'green-commute','version':app.version}

@app.post('/api/auth/login')
def login(payload:LoginIn,db:Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.username==payload.username))
    if not u or not u.enabled or not verify_password(payload.password,u.password_hash):
        raise HTTPException(status_code=401,detail='用户名或密码错误')
    return {'access_token':create_token(u.id,u.session_version),'token_type':'bearer','user':serial_user(u)}

def commit_unique(db:Session,message:str):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409,detail=message) from exc

@app.post('/api/auth/register',status_code=201)
def register(payload:RegisterIn,db:Session=Depends(get_db)):
    u=User(username=payload.username,display_name=payload.username,password_hash=hash_password(payload.password),
           role='resident',balance=0)
    db.add(u)
    commit_unique(db,'用户名已存在')
    db.refresh(u)
    return {'access_token':create_token(u.id,u.session_version),'user':serial_user(u)}

@app.get('/api/me')
def me(u:User=Depends(current_user),db:Session=Depends(get_db)):
    db.refresh(u);return serial_user(u)

@app.get('/api/rules')
def rules(db:Session=Depends(get_db)):
    rule=get_active_rule(db)
    result=rule_snapshot(rule)
    result.update(rounding='向下取整到整积分',note='按当前排放规则估算，结果不用于官方碳核证')
    return result

@app.get('/api/admin/rules')
def admin_rules(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    rows=db.scalars(select(EmissionRule).order_by(EmissionRule.id.desc())).all()
    return [rule_snapshot(x) for x in rows]

@app.post('/api/admin/rules',status_code=201)
def add_emission_rule(payload:EmissionRuleIn,u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    rule=create_emission_rule(db,payload.version,payload.name,payload.baseline_g_per_km,
                              payload.points_per_kg,payload.mode_g_per_km)
    return rule_snapshot(rule)

@app.get('/api/carbon/calculate')
def carbon_calculate(mode: str, distance_km: Decimal, db:Session=Depends(get_db)):
    rule=get_active_rule(db)
    factors={x.mode:x.grams_per_km for x in rule.factors}
    if mode not in factors:
        raise BusinessError('当前规则不支持该出行方式')
    distance_m, saved_g, points = calculate_with_factors(
        mode,distance_km,rule.baseline_g_per_km,factors[mode],rule.points_per_kg)
    return {'mode':mode,'distance_km':distance_m/1000,
            'baseline_g_per_km':rule.baseline_g_per_km,'mode_g_per_km':factors[mode],
            'saved_g':saved_g,'saved_kg':saved_g/1000,'points':points,
            'rule_version':rule.version,
            'formula':'floor(distance_m × (baseline_g_per_km - mode_g_per_km) / 1000)'}

@app.post('/api/trips')
def add_trip(payload:TripIn,u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    trip=submit_trip(db,u.id,payload.client_trip_id,payload.mode,payload.distance_km,
                     payload.source,payload.evidence_reference)
    process_pending(db)
    db.refresh(trip)
    db.refresh(u)
    return {'trip':serial_trip(trip),'balance':u.balance}

@app.get('/api/trips')
def my_trips(u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    rows=db.scalars(select(Trip).where(Trip.user_id==u.id).order_by(Trip.id.desc()).limit(100)).all()
    return [serial_trip(x) for x in rows]

@app.get('/api/trips/{trip_id}')
def trip_detail(trip_id:int,u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    row=db.get(Trip,trip_id)
    if not row or row.user_id!=u.id:
        raise HTTPException(status_code=404,detail='行程不存在')
    return serial_trip_detail(row)

@app.get('/api/wallet')
def wallet(limit:int=Query(default=100,ge=1,le=200),before_id:int|None=Query(default=None,ge=1),
           start_date:date|None=None,end_date:date|None=None,
           direction:Literal['all','income','expense']='all',
           zone:str=Query(default='UTC',alias='timezone',max_length=80),
           u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    db.refresh(u)
    q=select(PointTransaction).where(PointTransaction.user_id==u.id)
    if start_date and end_date and start_date>end_date:
        raise HTTPException(status_code=422,detail='开始日期不能晚于结束日期')
    try:
        local_zone=ZoneInfo(zone)
        if start_date:
            start=datetime.combine(start_date,time.min,local_zone).astimezone(timezone.utc)
            q=q.where(PointTransaction.created_at>=start.replace(tzinfo=None))
        if end_date:
            end=datetime.combine(end_date+timedelta(days=1),time.min,local_zone).astimezone(timezone.utc)
            q=q.where(PointTransaction.created_at<end.replace(tzinfo=None))
    except (ZoneInfoNotFoundError,ValueError,OverflowError) as exc:
        raise HTTPException(status_code=422,detail='日期或时区无效') from exc
    if direction=='income':
        q=q.where(PointTransaction.delta>0)
    elif direction=='expense':
        q=q.where(PointTransaction.delta<0)
    if before_id is not None:q=q.where(PointTransaction.id<before_id)
    rows=db.scalars(q.order_by(PointTransaction.id.desc()).limit(limit+1)).all()
    has_more=len(rows)>limit
    rows=rows[:limit]
    result=ledger_summary(db,u.id)
    result.update(transactions=[serial_point_transaction(x) for x in rows],
                 page_size=limit,next_before_id=rows[-1].id if has_more and rows else None)
    return result

@app.get('/api/products')
def products(merchant_id:int|None=None,u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    q=select(Product,User.display_name).join(User,User.id==Product.merchant_id).where(
        Product.active.is_(True),User.enabled.is_(True))
    if merchant_id is not None:q=q.where(Product.merchant_id==merchant_id)
    return [serial_product(p,name) for p,name in db.execute(q.order_by(Product.id)).all()]

def merchant_directory(db:Session,enabled_only:bool):
    product_count=func.count(case((Product.active.is_(True),Product.id)))
    q=select(User.id,User.display_name,product_count).outerjoin(Product,Product.merchant_id==User.id)
    q=q.where(User.role=='merchant')
    if enabled_only:
        q=q.where(User.enabled.is_(True))
    rows=db.execute(q.group_by(User.id,User.display_name).order_by(User.id)).all()
    return [{'id':id,'display_name':name,'product_count':count} for id,name,count in rows]

@app.get('/api/merchants')
def merchants(u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    return merchant_directory(db,enabled_only=True)

@app.post('/api/redemptions')
def create_redemption(payload:dict,u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    product_id=payload.get('product_id')
    if not isinstance(product_id,int) or isinstance(product_id,bool):
        raise HTTPException(status_code=422,detail='商品编号必须为整数')
    result=redeem(db,u.id,product_id)
    process_pending(db)
    db.refresh(result);db.refresh(u)
    return {'redemption':serial_redemption(result),'balance':u.balance}

@app.get('/api/redemptions')
def my_redemptions(u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    return [serial_redemption(r) for r in db.scalars(select(Redemption).where(Redemption.user_id==u.id).order_by(Redemption.id.desc()).limit(100)).all()]

def owned_redemption(db:Session,user_id:int,redemption_id:int):
    row=db.scalar(select(Redemption).where(Redemption.id==redemption_id,Redemption.user_id==user_id))
    if row is None:
        raise HTTPException(status_code=404,detail='兑换订单不存在')
    return row

@app.get('/api/redemptions/{redemption_id}')
def my_redemption_detail(redemption_id:int,u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    return serial_redemption(owned_redemption(db,u.id,redemption_id))

@app.post('/api/redemptions/{redemption_id}/refund')
def refund_my_redemption(redemption_id:int,u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    row=owned_redemption(db,u.id,redemption_id)
    if row.status=='PROCESSING':
        process_pending(db)
        db.refresh(row)
    result=refund_redemption(db,u.id,redemption_id)
    db.refresh(u)
    return {'redemption':serial_redemption(result),'balance':u.balance}

@app.get('/api/merchant/products')
def merchant_products(u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    return [serial_product(p) for p in db.scalars(select(Product).where(Product.merchant_id==u.id).order_by(Product.id.desc())).all()]

@app.get('/api/merchant/categories')
def merchant_categories(u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    rows=db.scalars(select(MerchantCategory).where(MerchantCategory.merchant_id==u.id)
                    .order_by(MerchantCategory.name,MerchantCategory.id)).all()
    return [{'id':row.id,'name':row.name} for row in rows]

@app.post('/api/merchant/categories',status_code=201)
def add_category(payload:CategoryIn,u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    category=MerchantCategory(merchant_id=u.id,name=payload.name)
    db.add(category)
    commit_unique(db,'该品类已存在')
    return {'id':category.id,'name':category.name}

def find_category(db:Session,merchant_id:int,name:str):
    return db.scalar(select(MerchantCategory).where(
        MerchantCategory.merchant_id==merchant_id,MerchantCategory.name==name))

@app.post('/api/merchant/products',status_code=201)
def add_product(payload:ProductIn,u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    data=payload.model_dump()
    opening=data.pop('stock')
    category=find_category(db,u.id,data['category'])
    if category:
        data['category']=category.name
    p=Product(merchant_id=u.id,stock=0,**data);db.add(p);db.flush()
    if opening:
        adjust_inventory(db,p.id,opening,'OPENING',f'product-{p.id}','商品初始库存',p.id)
    if category is None:
        db.add(MerchantCategory(merchant_id=u.id,name=p.category))
    commit_unique(db,'品类已由其他操作创建，请重试')
    db.refresh(p)
    return serial_product(p)

@app.patch('/api/merchant/products/{product_id}')
def update_product(product_id:int,payload:ProductUpdateIn,
                   u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    p=db.get(Product,product_id)
    if not p or p.merchant_id!=u.id:raise HTTPException(status_code=404,detail='商品不存在')
    changes=payload.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(status_code=422,detail='请填写有效的商品字段')
    if 'category' in changes:
        category=find_category(db,u.id,changes['category'])
        if category:
            changes['category']=category.name
        else:
            db.add(MerchantCategory(merchant_id=u.id,name=changes['category']))
    for key,value in changes.items():setattr(p,key,value)
    commit_unique(db,'品类已由其他操作创建，请重试')
    db.refresh(p)
    return serial_product(p)

@app.post('/api/merchant/products/{product_id}/inventory')
def change_inventory(product_id:int,payload:InventoryAdjustIn,
                     u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    p=db.get(Product,product_id)
    if not p or p.merchant_id!=u.id:raise HTTPException(status_code=404,detail='商品不存在')
    movement=adjust_inventory(db,product_id,payload.quantity,'ADJUSTMENT',payload.operation_id,payload.note)
    db.commit();db.refresh(p)
    return {'product':serial_product(p),'movement':serial_inventory_movement(movement)}

@app.get('/api/merchant/products/{product_id}/inventory')
def inventory_history(product_id:int,limit:int=Query(default=100,ge=1,le=200),
                      u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    p=db.get(Product,product_id)
    if not p or p.merchant_id!=u.id:raise HTTPException(status_code=404,detail='商品不存在')
    rows=db.scalars(select(InventoryMovement).where(InventoryMovement.product_id==product_id)
                    .order_by(InventoryMovement.id.desc()).limit(limit)).all()
    return {'product':serial_product(p),'movements':[serial_inventory_movement(x) for x in rows]}

@app.get('/api/admin/merchants')
def admin_merchants(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    return merchant_directory(db,enabled_only=False)

@app.post('/api/admin/merchants',status_code=201)
def add_merchant(payload:MerchantCreateIn,u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    merchant=User(username=payload.username,display_name=payload.display_name,
                  password_hash=hash_password(payload.password),role='merchant')
    db.add(merchant)
    commit_unique(db,'用户名已存在')
    db.refresh(merchant)
    return serial_user(merchant)

@app.get('/api/admin/accounts')
def admin_accounts(role:ManagedRole|None=None,username:str=Query(default='',max_length=48),enabled:bool|None=None,
                   u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    q=select(User).where(User.role.in_(('resident','merchant')))
    if role:
        q=q.where(User.role==role)
    if username.strip():
        q=q.where(User.username.icontains(username.strip(),autoescape=True))
    if enabled is not None:
        q=q.where(User.enabled==enabled)
    return [serial_user(account) for account in db.scalars(q.order_by(User.username,User.id))]

def managed_account(db:Session,account_id:int):
    account=db.scalar(select(User).where(User.id==account_id,User.role.in_(('resident','merchant'))))
    if account is None:
        raise HTTPException(status_code=404,detail='账号不存在')
    return account

@app.patch('/api/admin/accounts/{account_id}')
def update_account(account_id:int,payload:AccountUpdateIn,
                   u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    account=managed_account(db,account_id)
    changes=payload.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(status_code=422,detail='请填写有效的账号字段')
    if account.role=='resident':
        if 'display_name' in changes:
            raise HTTPException(status_code=422,detail='居民使用用户名作为显示名称')
        if 'username' in changes:
            changes['display_name']=changes['username']
    statement=update(User).where(User.id==account.id)
    if 'enabled' in changes:
        version=User.session_version+case((User.enabled!=changes['enabled'],1),else_=0)
        # MySQL evaluates UPDATE assignments from left to right.
        statement=statement.ordered_values((User.session_version,version),*changes.items())
    else:
        statement=statement.values(**changes)
    try:
        db.execute(statement)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409,detail='用户名已存在') from exc
    db.commit()
    db.refresh(account)
    return serial_user(account)

@app.post('/api/admin/accounts/{account_id}/reset-password')
def reset_account_password(account_id:int,payload:PasswordResetIn,
                           u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    account=managed_account(db,account_id)
    db.execute(update(User).where(User.id==account.id).values(
        password_hash=hash_password(payload.password),session_version=User.session_version+1))
    db.commit()
    return {'ok':True}

@app.get('/api/merchant/orders')
def merchant_orders(u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    rows=db.execute(select(Redemption,Settlement).join(Settlement,Settlement.redemption_id==Redemption.id).where(Settlement.merchant_id==u.id).order_by(Redemption.id.desc())).all()
    return [{'redemption':serial_redemption(r),'settlement':serial_settlement(s),
             'settlement_status':s.status} for r,s in rows]

@app.post('/api/merchant/orders/{redemption_id}/fulfill')
def fulfill(redemption_id:int,u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    r=fulfill_redemption(db,u.id,redemption_id)
    return {'ok':True,'status':r.status,'fulfilled_at':r.fulfilled_at.isoformat()+'Z' if r.fulfilled_at else None}

@app.get('/api/admin/stats')
def platform_stats(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    summary=stats(db)
    summary.update(users=db.scalar(select(func.count()).select_from(User).where(User.role=='resident')) or 0,
                   pending_events=db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state=='PENDING')) or 0)
    return summary

@app.get('/api/admin/settlements')
def settlements(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    rows=db.scalars(select(Settlement).order_by(Settlement.redemption_id.desc())).all()
    return [serial_settlement(s) for s in rows]

@app.post('/api/admin/settlements/{redemption_id}/settle')
def settle(redemption_id:int,u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    s=settle_redemption(db,redemption_id)
    return {'ok':True,'status':s.status,'settled_at':s.settled_at.isoformat()+'Z' if s.settled_at else None}

@app.post('/api/admin/events/process')
def process_events(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    return {'processed':process_pending(db)}

# ---- Human customer support. All data are stored in SQLite/MySQL. ----
def _ticket_data(db:Session, ticket:SupportTicket):
    customer=db.get(User,ticket.user_id)
    return {'id':ticket.id,'user_id':ticket.user_id,'customer_name':account_name(customer) if customer else '未知用户',
            'category':ticket.category,'subject':ticket.subject,'status':ticket.status,
            'created_at':ticket.created_at.isoformat()+'Z',
            'updated_at':ticket.updated_at.isoformat()+'Z'}

def _get_ticket(db:Session,ticket_id:int,u:User):
    ticket=db.get(SupportTicket,ticket_id)
    if not ticket or (u.role!='admin' and ticket.user_id!=u.id):
        raise HTTPException(status_code=404,detail='工单不存在')
    return ticket

@app.get('/api/support/tickets')
def list_support_tickets(u:User=Depends(current_user),db:Session=Depends(get_db)):
    q=select(SupportTicket)
    if u.role!='admin':q=q.where(SupportTicket.user_id==u.id)
    rows=db.scalars(q.order_by(SupportTicket.updated_at.desc(),SupportTicket.id.desc()).limit(100)).all()
    return [_ticket_data(db,t) for t in rows]

@app.post('/api/support/tickets',status_code=201)
def open_support_ticket(payload:TicketCreateIn,u:User=Depends(require_role('resident','merchant')),db:Session=Depends(get_db)):
    t=SupportTicket(user_id=u.id,subject=payload.subject.strip(),category=payload.category,status='OPEN')
    m=SupportMessage(ticket_id=0,sender_id=u.id,content=payload.content.strip())
    if not t.subject or not m.content:
        raise HTTPException(status_code=422,detail='标题和内容不能为空')
    db.add(t);db.flush();m.ticket_id=t.id;db.add(m);db.commit();db.refresh(t)
    return _ticket_data(db,t)

@app.get('/api/support/tickets/{ticket_id}')
def support_ticket_detail(ticket_id:int,u:User=Depends(current_user),db:Session=Depends(get_db)):
    t=_get_ticket(db,ticket_id,u)
    rows=db.scalars(select(SupportMessage).where(SupportMessage.ticket_id==t.id).order_by(SupportMessage.id).limit(200)).all()
    messages=[]
    for msg in rows:
        author=db.get(User,msg.sender_id)
        messages.append({'id':msg.id,'sender_role':author.role if author else 'unknown',
                         'sender_name':account_name(author) if author else '未知用户','sender_id':msg.sender_id,
                         'content':msg.content,'created_at':msg.created_at.isoformat()+'Z'})
    return {'ticket':_ticket_data(db,t),'messages':messages}

@app.post('/api/support/tickets/{ticket_id}/messages',status_code=201)
def support_reply(ticket_id:int,payload:TicketMessageIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    t=_get_ticket(db,ticket_id,u)
    if not payload.content.strip():raise HTTPException(status_code=422,detail='回复不能为空')
    t.status='IN_PROGRESS' if u.role=='admin' else 'OPEN'
    t.updated_at=utcnow()
    db.add(SupportMessage(ticket_id=t.id,sender_id=u.id,content=payload.content.strip()))
    db.commit()
    return {'ok':True,'status':t.status}

@app.patch('/api/support/tickets/{ticket_id}/status')
def set_support_status(ticket_id:int,payload:TicketStatusIn,u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    t=_get_ticket(db,ticket_id,u)
    t.status=payload.status;t.updated_at=utcnow();db.commit()
    return {'ok':True,'status':t.status}

# ---- Real LLM invocation is opt-in; never silently invent AI responses. ----
@app.get('/api/assistant/config')
def assistant_config(u:User=Depends(current_user)):
    return configuration()

@app.post('/api/assistant/chat')
async def assistant_chat(payload:AssistantChatIn,u:User=Depends(current_user)):
    if not payload.message.strip():raise HTTPException(status_code=422,detail='问题不能为空')
    return await query_model(payload.message.strip(),[x.model_dump() for x in payload.history])

STATIC=Path(__file__).resolve().parent/'static'
app.mount('/assets',StaticFiles(directory=STATIC),name='assets')
@app.get('/',include_in_schema=False)
def index():return FileResponse(STATIC/'index.html')
