"""Business rules: integer gram/km accounting, ledger invariants, and transactional outbox.

The local delivery path runs the dispatcher directly after transaction commit. The
same dispatcher may be retried independently by a worker or an administrator.
"""
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from .models import User, Trip, PointTransaction, Product, Redemption, Settlement, OutboxEvent, utcnow

# Illustrative teaching constants, not externally verified emissions factors.
BASELINE_G_PER_KM = 180
TRANSPORT_G_PER_KM = {'bus':70, 'metro':40, 'bike':0, 'walk':0}
MODES = {'bus':'公交','metro':'地铁','bike':'骑行','walk':'步行'}

class BusinessError(Exception):
    def __init__(self,message,status_code=400):
        self.message=message;self.status_code=status_code

def calculate(mode:str, distance_km: Decimal):
    if mode not in MODES:
        raise BusinessError('出行方式无效')
    try:
        km=Decimal(str(distance_km))
        meters=km * 1000
    except (InvalidOperation,TypeError):
        raise BusinessError('距离无效')
    if not km.is_finite() or km<=0 or km>100 or meters!=meters.to_integral_value() or km.as_tuple().exponent < -2:
        raise BusinessError('距离应在0.01—100公里之间，最多两位小数')
    distance_m=int(meters)
    # Distance is entered to hundredth of km (10 m). All factors are integers.
    saved_g=(distance_m*(BASELINE_G_PER_KM-TRANSPORT_G_PER_KM[mode]))//1000
    pts=saved_g//100  # floor(kg CO2e saved × 10)
    return distance_m,saved_g,pts

def serial_user(user):
    return {'id':user.id,'username':user.username,'display_name':user.display_name,'role':user.role,'balance':user.balance}

def serial_trip(t):
    return {'id':t.id,'client_trip_id':t.client_trip_id,'mode':t.mode,'mode_name':MODES[t.mode], 'distance_km':t.distance_m/1000,'saved_kg':t.saved_g/1000,'points':t.points,'status':t.status,'created_at':t.created_at.isoformat()+'Z'}

def serial_product(p):
    return {'id':p.id,'name':p.name,'description':p.description,'category':p.category,'icon':p.icon,'cost':p.cost,'stock':p.stock,'active':p.active,'merchant_id':p.merchant_id}

def serial_redemption(r):
    return {'id':r.id,'product_id':r.product_id,'product_name':r.product_name,'points':r.points,'status':r.status,'created_at':r.created_at.isoformat()+'Z'}

def submit_trip(db,user_id,client_trip_id,mode,distance_km):
    meters,saved,points=calculate(mode,distance_km)
    existing=db.scalar(select(Trip).where(Trip.user_id==user_id,Trip.client_trip_id==client_trip_id))
    if existing:
        if (existing.mode,existing.distance_m)!=(mode,meters):
            raise BusinessError('行程编号已用于其他行程',409)
        return existing
    trip=Trip(user_id=user_id,client_trip_id=client_trip_id,mode=mode,distance_m=meters,saved_g=saved,points=points)
    try:
        db.add(trip);db.flush()
        db.add(OutboxEvent(kind='TripSubmitted',ref_id=trip.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Trip).where(Trip.user_id==user_id,Trip.client_trip_id==client_trip_id))
        if existing and (existing.mode,existing.distance_m)==(mode,meters): return existing
        raise BusinessError('行程编号冲突，请重新提交',409)
    return trip

def redeem(db,user_id,product_id):
    p=db.get(Product,product_id)
    if p is None or not p.active:raise BusinessError('商品不存在或已下架',404)
    try:
        # Atomic conditional updates serialize competing debits / stock depletion.
        debit=db.execute(update(User).where(User.id==user_id, User.balance>=p.cost).values(balance=User.balance-p.cost))
        if debit.rowcount!=1:raise BusinessError('积分余额不足',409)
        stock=db.execute(update(Product).where(Product.id==p.id,Product.stock>=1,Product.active==True).values(stock=Product.stock-1))
        if stock.rowcount!=1:raise BusinessError('商品库存不足',409)
        red=Redemption(user_id=user_id,product_id=p.id,product_name=p.name,points=p.cost)
        db.add(red);db.flush()
        db.add(PointTransaction(user_id=user_id,kind='REDEEM',reference_id=red.id,delta=-p.cost,description='兑换 '+p.name))
        db.add(OutboxEvent(kind='RedemptionCreated',ref_id=red.id))
        db.commit()
        return red
    except Exception:
        db.rollback();raise

def process_pending(db, limit=100):
    """At-least-once delivery with idempotent consumers; DB transaction per event.

    Educational single-process dispatcher. Deploy just one worker per DB, or add
    leases/row locking for horizontally scaled consumers.
    """
    events=db.scalars(select(OutboxEvent).where(OutboxEvent.state=='PENDING').order_by(OutboxEvent.id).limit(limit)).all()
    processed=0
    for e in events:
        try:
            if e.kind=='TripSubmitted':
                trip=db.get(Trip,e.ref_id)
                if trip and trip.status=='PENDING':
                    # If ledger exists after retry, never credit again.
                    txn=db.scalar(select(PointTransaction).where(PointTransaction.kind=='TRIP',PointTransaction.reference_id==trip.id))
                    if not txn:
                        db.execute(update(User).where(User.id==trip.user_id).values(balance=User.balance+trip.points))
                        db.add(PointTransaction(user_id=trip.user_id,kind='TRIP',reference_id=trip.id,delta=trip.points,description='绿色出行积分'))
                    trip.status='AWARDED'
            elif e.kind=='RedemptionCreated':
                red=db.get(Redemption,e.ref_id)
                if red:
                    p=db.get(Product,red.product_id)
                    settlement=db.get(Settlement,red.id)
                    if not settlement:db.add(Settlement(redemption_id=red.id,merchant_id=p.merchant_id,points=red.points))
                    if red.status=='PROCESSING':red.status='TO_FULFILL'
            else:
                raise ValueError('Unknown event kind: '+e.kind)
            e.state='DONE';e.attempts+=1;e.error=None
            db.commit();processed+=1
        except Exception as exc:
            db.rollback()
            event=db.get(OutboxEvent,e.id)
            if event:
                event.attempts+=1
                event.error=str(exc)[:600]
                db.commit()  # leave PENDING for retry
    return processed

def stats(db):
    trips=db.scalar(select(func.count()).select_from(Trip).where(Trip.status=='AWARDED')) or 0
    grams=db.scalar(select(func.coalesce(func.sum(Trip.saved_g),0)).where(Trip.status=='AWARDED')) or 0
    points=db.scalar(select(func.coalesce(func.sum(Trip.points),0)).where(Trip.status=='AWARDED')) or 0
    redeems=db.scalar(select(func.count()).select_from(Redemption)) or 0
    return {'trips':trips,'saved_kg':round(grams/1000,3),'issued_points':points,'redemptions':redeems}
