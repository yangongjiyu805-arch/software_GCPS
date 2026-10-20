"""Green Commute Points – runnable REST API and bundled responsive web client."""
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
import os
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import Base,engine,get_db,SessionLocal
from .models import User, Trip, Product, PointTransaction, Redemption, Settlement, OutboxEvent, utcnow
from .security import create_token, decode_token, hash_password,verify_password
from .services import BusinessError, submit_trip,redeem,process_pending,stats,serial_user,serial_trip,serial_product,serial_redemption,calculate,MODES

class LoginIn(BaseModel):
    username: str
    password: str
class RegisterIn(BaseModel):
    username: str=Field(min_length=3,max_length=48,pattern=r'^[a-zA-Z0-9_]+$')
    display_name: str=Field(min_length=1,max_length=80)
    password: str=Field(min_length=8,max_length=128)
class TripIn(BaseModel):
    client_trip_id: str=Field(min_length=6,max_length=72,pattern=r'^[a-zA-Z0-9_-]+$')
    mode: str
    distance_km: Decimal
class ProductIn(BaseModel):
    name: str=Field(min_length=2,max_length=90)
    description: str=Field(default='',max_length=300)
    category: str=Field(default='生活好物',max_length=40)
    icon: str=Field(default='gift',max_length=16)
    cost: int=Field(ge=1,le=100000)
    stock: int=Field(ge=0,le=100000)
class FulfillIn(BaseModel):
    status: str=Field(pattern='^(FULFILLED)$')

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
    for name,desc,cat,icon,cost,stock in catalog:
        db.add(Product(merchant_id=users['merchant'].id,name=name,description=desc,category=cat,icon=icon,cost=cost,stock=stock))
    db.commit()

@asynccontextmanager
async def lifespan(app:FastAPI):
    if os.getenv('ENVIRONMENT')=='production' and (os.getenv('JWT_SECRET','') in ('','local-dev-secret-REPLACE-BEFORE-DEPLOYMENT')):
        raise RuntimeError('Set a strong JWT_SECRET before production deployment')
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _seed(db)
        process_pending(db)
    yield

app=FastAPI(title='城市绿色出行积分系统',description='碳减排模拟、积分台账、积分商城和事件清算示例',version='1.0.0',lifespan=lifespan)

@app.exception_handler(BusinessError)
async def business_handler(_,exc:BusinessError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code,content={'detail':exc.message})

def current_user(authorization: str|None=Header(default=None), db:Session=Depends(get_db)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401,detail='请先登录')
    try:
        user_id=decode_token(authorization[7:]);u=db.get(User,user_id)
        if not u:raise ValueError()
        return u
    except (jwt.PyJWTError,ValueError,TypeError):
        raise HTTPException(status_code=401,detail='登录已过期，请重新登录')

def require_role(*roles):
    def wrapped(u:User=Depends(current_user)):
        if u.role not in roles:raise HTTPException(status_code=403,detail='无权限执行该操作')
        return u
    return wrapped

@app.get('/api/health')
def health():return {'ok':True,'service':'green-commute','version':'1.0.0'}

@app.post('/api/auth/login')
def login(payload:LoginIn,db:Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.username==payload.username))
    if not u or not verify_password(payload.password,u.password_hash):
        raise HTTPException(status_code=401,detail='用户名或密码错误')
    return {'access_token':create_token(u.id),'token_type':'bearer','user':serial_user(u)}

@app.post('/api/auth/register',status_code=201)
def register(payload:RegisterIn,db:Session=Depends(get_db)):
    if db.scalar(select(User).where(User.username==payload.username)):
        raise HTTPException(status_code=409,detail='用户名已存在')
    u=User(username=payload.username,display_name=payload.display_name,password_hash=hash_password(payload.password),role='resident')
    db.add(u);db.commit();db.refresh(u)
    return {'access_token':create_token(u.id),'user':serial_user(u)}

@app.get('/api/me')
def me(u:User=Depends(current_user),db:Session=Depends(get_db)):
    db.refresh(u);return serial_user(u)

@app.get('/api/rules')
def rules():
    return {'baseline_g_per_km':180,'mode_g_per_km':{'bus':70,'metro':40,'bike':0,'walk':0},'points_per_kg':10,'rounding':'向下取整到整积分','note':'教学模拟系数，非官方碳核算认证数据'}

@app.post('/api/trips')
def add_trip(payload:TripIn,u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    trip=submit_trip(db,u.id,payload.client_trip_id,payload.mode,payload.distance_km)
    process_pending(db)
    db.refresh(trip)
    db.refresh(u)
    return {'trip':serial_trip(trip),'balance':u.balance}

@app.get('/api/trips')
def my_trips(u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    rows=db.scalars(select(Trip).where(Trip.user_id==u.id).order_by(Trip.id.desc()).limit(100)).all()
    return [serial_trip(x) for x in rows]

@app.get('/api/wallet')
def wallet(u:User=Depends(require_role('resident')),db:Session=Depends(get_db)):
    db.refresh(u)
    rows=db.scalars(select(PointTransaction).where(PointTransaction.user_id==u.id).order_by(PointTransaction.id.desc()).limit(100)).all()
    return {'balance':u.balance,'transactions':[{'id':x.id,'kind':x.kind,'delta':x.delta,'description':x.description,'reference_id':x.reference_id,'created_at':x.created_at.isoformat()+'Z'} for x in rows]}

@app.get('/api/products')
def products(db:Session=Depends(get_db)):
    return [serial_product(p) for p in db.scalars(select(Product).where(Product.active==True).order_by(Product.id)).all()]

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

@app.get('/api/merchant/products')
def merchant_products(u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    return [serial_product(p) for p in db.scalars(select(Product).where(Product.merchant_id==u.id).order_by(Product.id.desc())).all()]

@app.post('/api/merchant/products',status_code=201)
def add_product(payload:ProductIn,u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    p=Product(merchant_id=u.id,**payload.model_dump());db.add(p);db.commit();db.refresh(p)
    return serial_product(p)

@app.get('/api/merchant/orders')
def merchant_orders(u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    rows=db.execute(select(Redemption,Settlement).join(Settlement,Settlement.redemption_id==Redemption.id).where(Settlement.merchant_id==u.id).order_by(Redemption.id.desc())).all()
    return [{'redemption':serial_redemption(r),'settlement_status':s.status} for r,s in rows]

@app.post('/api/merchant/orders/{redemption_id}/fulfill')
def fulfill(redemption_id:int,u:User=Depends(require_role('merchant')),db:Session=Depends(get_db)):
    r=db.get(Redemption,redemption_id);s=db.get(Settlement,redemption_id)
    if not r or not s or s.merchant_id!=u.id:raise HTTPException(status_code=404,detail='订单不存在')
    if r.status not in ('TO_FULFILL','FULFILLED'):raise HTTPException(status_code=409,detail='订单状态不允许核销')
    r.status='FULFILLED';db.commit();return {'ok':True,'status':r.status}

@app.get('/api/admin/stats')
def platform_stats(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    summary=stats(db)
    summary.update(users=db.scalar(select(func.count()).select_from(User).where(User.role=='resident')) or 0,
                   pending_events=db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state=='PENDING')) or 0)
    return summary

@app.get('/api/admin/settlements')
def settlements(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    rows=db.scalars(select(Settlement).order_by(Settlement.redemption_id.desc())).all()
    return [{'redemption_id':s.redemption_id,'merchant_id':s.merchant_id,'points':s.points,'status':s.status,'settled_at':s.settled_at.isoformat()+'Z' if s.settled_at else None} for s in rows]

@app.post('/api/admin/settlements/{redemption_id}/settle')
def settle(redemption_id:int,u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    s=db.get(Settlement,redemption_id)
    if not s:raise HTTPException(status_code=404,detail='清算单不存在')
    r=db.get(Redemption,redemption_id)
    if r.status!='FULFILLED':raise HTTPException(status_code=409,detail='商户尚未履约')
    if s.status!='SETTLED':s.status='SETTLED';s.settled_at=utcnow();db.commit()
    return {'ok':True,'status':s.status}

@app.post('/api/admin/events/process')
def process_events(u:User=Depends(require_role('admin')),db:Session=Depends(get_db)):
    return {'processed':process_pending(db)}

STATIC=Path(__file__).resolve().parent/'static'
app.mount('/assets',StaticFiles(directory=STATIC),name='assets')
@app.get('/',include_in_schema=False)
def index():return FileResponse(STATIC/'index.html')
