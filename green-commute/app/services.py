"""Business rules: integer gram/km accounting, ledger invariants, and transactional outbox.

The local delivery path runs the dispatcher directly after transaction commit. The
same dispatcher may be retried independently by a worker or an administrator.
"""
from decimal import Decimal, InvalidOperation
import json
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from .models import (User, Trip, PointTransaction, Product, InventoryMovement, Redemption, Settlement,
                     OutboxEvent, EmissionRule, EmissionFactor, TripCalculation,
                     TripEvidence, utcnow)

# Illustrative teaching constants, not externally verified emissions factors.
BASELINE_G_PER_KM = 180
TRANSPORT_G_PER_KM = {'bus':70, 'metro':40, 'bike':0, 'walk':0}
MODES = {'bus':'公交','metro':'地铁','bike':'骑行','walk':'步行'}
TRIP_SOURCES = {'manual','simulated','imported','partner'}
DEFAULT_RULE_VERSION = '2026.1'

class BusinessError(Exception):
    def __init__(self,message,status_code=400):
        self.message=message;self.status_code=status_code

def ensure_default_rule(db):
    """Create the initial versioned rule set without touching existing trips."""
    rule=db.scalar(select(EmissionRule).where(EmissionRule.version==DEFAULT_RULE_VERSION))
    changed=False
    if rule is None:
        rule=EmissionRule(version=DEFAULT_RULE_VERSION,name='GreenGo 基准排放规则',
                          baseline_g_per_km=BASELINE_G_PER_KM,points_per_kg=10,active=True,
                          effective_from=utcnow().replace(microsecond=0))
        db.add(rule);db.flush();changed=True
    existing={x.mode:x for x in rule.factors}
    for mode,grams in TRANSPORT_G_PER_KM.items():
        if mode not in existing:
            db.add(EmissionFactor(rule_id=rule.id,mode=mode,grams_per_km=grams));changed=True
    if changed:db.commit();db.refresh(rule)
    return rule

def get_active_rule(db):
    now=utcnow()
    rule=db.scalar(select(EmissionRule).where(EmissionRule.active==True,
                   EmissionRule.effective_from<=now,
                   (EmissionRule.effective_to.is_(None) | (EmissionRule.effective_to>now)))
                   .order_by(EmissionRule.effective_from.desc(),EmissionRule.id.desc()))
    return rule or ensure_default_rule(db)

def create_emission_rule(db, version, name, baseline_g_per_km, points_per_kg, factors):
    """Publish a new rule version; old calculation snapshots remain immutable."""
    if set(factors) != set(MODES):
        raise BusinessError('必须为公交、地铁、骑行、步行分别设置减排系数')
    if any(not isinstance(value,int) or value<0 or value>=baseline_g_per_km for value in factors.values()):
        raise BusinessError('出行方式减排系数必须为非负整数且小于基准值')
    if baseline_g_per_km<=0 or points_per_kg<=0:
        raise BusinessError('减排基准和积分比例必须为正数')
    if db.scalar(select(EmissionRule).where(EmissionRule.version==version)):
        raise BusinessError('规则版本已存在',409)
    # MySQL DATETIME may round fractional seconds into the future.
    now=utcnow().replace(microsecond=0)
    try:
        db.execute(update(EmissionRule).where(EmissionRule.active==True).values(active=False,effective_to=now))
        rule=EmissionRule(version=version,name=name,baseline_g_per_km=baseline_g_per_km,
                          points_per_kg=points_per_kg,active=True,effective_from=now)
        db.add(rule);db.flush()
        db.add_all([EmissionFactor(rule_id=rule.id,mode=mode,grams_per_km=value)
                    for mode,value in factors.items()])
        db.commit();db.refresh(rule)
        return rule
    except IntegrityError:
        db.rollback()
        raise BusinessError('规则版本已存在',409)

def rule_snapshot(rule):
    factors={x.mode:x.grams_per_km for x in rule.factors}
    return {'id':rule.id,'version':rule.version,'name':rule.name,
            'baseline_g_per_km':rule.baseline_g_per_km,'points_per_kg':rule.points_per_kg,
            'mode_g_per_km':factors,'effective_from':rule.effective_from.isoformat()+'Z',
            'effective_to':rule.effective_to.isoformat()+'Z' if rule.effective_to else None}

def calculate_with_factors(mode:str, distance_km: Decimal, baseline_g_per_km: int,
                           mode_g_per_km: int, points_per_kg: int=10):
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
    if baseline_g_per_km <= mode_g_per_km or points_per_kg <= 0:
        raise BusinessError('减排规则无效',500)
    saved_g=(distance_m*(baseline_g_per_km-mode_g_per_km))//1000
    pts=(saved_g*points_per_kg)//1000
    return distance_m,saved_g,pts

def calculate(mode:str, distance_km: Decimal):
    """Backward-compatible calculation using the default teaching rule."""
    return calculate_with_factors(mode,distance_km,BASELINE_G_PER_KM,TRANSPORT_G_PER_KM.get(mode,-1),10)

def account_name(user):
    return user.username if user.role=='resident' else user.display_name

def serial_user(user):
    return {'id':user.id,'username':user.username,'display_name':account_name(user),
            'role':user.role,'balance':user.balance,'enabled':user.enabled}

def serial_trip(t):
    calc=getattr(t,'calculation',None)
    evidence=getattr(t,'evidence',None) or []
    return {'id':t.id,'client_trip_id':t.client_trip_id,'mode':t.mode,'mode_name':MODES[t.mode],
            'distance_km':t.distance_m/1000,'saved_kg':t.saved_g/1000,'points':t.points,
            'status':t.status,'source':evidence[0].source_type if evidence else 'legacy',
            'rule_version':calc.rule_version if calc else None,
            'calculation':{'baseline_g_per_km':calc.baseline_g_per_km,
                           'mode_g_per_km':calc.mode_g_per_km,
                           'points_per_kg':calc.points_per_kg} if calc else None,
            'created_at':t.created_at.isoformat()+'Z'}

def serial_trip_detail(t):
    result=serial_trip(t)
    result['evidence']=[{'source_type':item.source_type,
                         'external_reference':item.external_reference,
                         'captured_at':item.captured_at.isoformat()+'Z'}
                        for item in (getattr(t,'evidence',None) or [])]
    return result

def serial_product(p, merchant_name=None):
    stock_status='OUT_OF_STOCK' if p.stock==0 else 'LOW_STOCK' if p.stock<=5 else 'AVAILABLE'
    return {'id':p.id,'name':p.name,'description':p.description,'category':p.category,'icon':p.icon,
            'cost':p.cost,'stock':p.stock,'stock_status':stock_status,'active':p.active,
            'merchant_id':p.merchant_id,'merchant_name':merchant_name}

def serial_inventory_movement(item):
    return {'id':item.id,'product_id':item.product_id,'kind':item.kind,
            'operation_id':item.operation_id,'reference_id':item.reference_id,
            'quantity':item.quantity,'before_stock':item.before_stock,
            'after_stock':item.after_stock,'note':item.note,
            'created_at':item.created_at.isoformat()+'Z'}

def adjust_inventory(db,product_id,quantity,kind,operation_id,note,reference_id=None):
    """Atomically change stock and record an idempotent inventory movement."""
    if not isinstance(product_id,int) or isinstance(product_id,bool):
        raise BusinessError('商品编号无效',422)
    if not isinstance(quantity,int) or isinstance(quantity,bool) or quantity==0:
        raise BusinessError('库存变动必须为非零整数',422)
    if not operation_id or len(operation_id)>72:
        raise BusinessError('库存操作编号无效',422)
    existing=db.scalar(select(InventoryMovement).where(
        InventoryMovement.operation_id==operation_id))
    if existing:
        if (existing.product_id,existing.quantity,existing.kind)!=(product_id,quantity,kind):
            raise BusinessError('库存操作编号已被其他变更使用',409)
        return existing
    conditions=[Product.id==product_id]
    if quantity<0:conditions.append(Product.stock>=-quantity)
    changed=db.execute(update(Product).where(*conditions).values(stock=Product.stock+quantity))
    if changed.rowcount!=1:
        if db.get(Product,product_id) is None:raise BusinessError('商品不存在',404)
        raise BusinessError('库存不足',409)
    product=db.get(Product,product_id)
    db.refresh(product,attribute_names=['stock'])
    before=product.stock-quantity
    movement=InventoryMovement(product_id=product_id,kind=kind,
                               operation_id=operation_id,reference_id=reference_id,
                               quantity=quantity,before_stock=before,
                               after_stock=product.stock,note=note[:200])
    db.add(movement)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(InventoryMovement).where(
            InventoryMovement.operation_id==operation_id))
        if existing and (existing.product_id,existing.quantity,existing.kind)==(product_id,quantity,kind):
            return existing
        raise BusinessError('库存操作编号冲突',409)
    return movement

def backfill_inventory_opening(db):
    """Record opening snapshots for products created before inventory history existed."""
    products=db.scalars(select(Product).order_by(Product.id)).all()
    changed=False
    for product in products:
        if db.scalar(select(InventoryMovement.id).where(
                InventoryMovement.product_id==product.id).limit(1)) is not None:
            continue
        if product.stock<=0:continue
        db.add(InventoryMovement(product_id=product.id,kind='OPENING',
                                 operation_id=f'legacy-opening-{product.id}',
                                 quantity=product.stock,before_stock=0,
                                 after_stock=product.stock,note='历史商品初始库存'))
        changed=True
    if changed:db.commit()
    return changed

def serial_redemption(r):
    return {'id':r.id,'product_id':r.product_id,'product_name':r.product_name,'points':r.points,
            'status':r.status,'created_at':r.created_at.isoformat()+'Z',
            'updated_at':r.updated_at.isoformat()+'Z' if r.updated_at else None,
            'fulfilled_at':r.fulfilled_at.isoformat()+'Z' if r.fulfilled_at else None,
            'refunded_at':r.refunded_at.isoformat()+'Z' if r.refunded_at else None,
            'can_refund':r.status=='TO_FULFILL'}

def serial_settlement(item):
    return {'redemption_id':item.redemption_id,'merchant_id':item.merchant_id,
            'points':item.points,'status':item.status,
            'created_at':item.created_at.isoformat()+'Z',
            'settled_at':item.settled_at.isoformat()+'Z' if item.settled_at else None,
            'cancelled_at':item.cancelled_at.isoformat()+'Z' if item.cancelled_at else None}

def serial_point_transaction(item):
    return {'id':item.id,'kind':item.kind,'delta':item.delta,
            'balance_after':item.balance_after,'description':item.description,
            'reference_id':item.reference_id,'created_at':item.created_at.isoformat()+'Z'}

def post_points(db,user_id,kind,reference_id,delta,description):
    """Post one idempotent ledger entry and update the materialized balance.

    The user balance is a fast read model; PointTransaction is the audit source.
    The business key makes retries safe, while the conditional update prevents a
    negative balance when two redemptions compete for the same account.
    """
    if not kind or not isinstance(reference_id,int) or isinstance(reference_id,bool):
        raise BusinessError('积分业务引用无效',422)
    if not isinstance(delta,int) or isinstance(delta,bool) or delta==0:
        raise BusinessError('积分变动必须为非零整数',422)
    existing=db.scalar(select(PointTransaction).where(
        PointTransaction.kind==kind,PointTransaction.reference_id==reference_id))
    if existing:
        if existing.user_id!=user_id or existing.delta!=delta:
            raise BusinessError('积分业务流水冲突',409)
        return existing
    conditions=[User.id==user_id]
    if delta<0:
        conditions.append(User.balance>=-delta)
    changed=db.execute(update(User).where(*conditions).values(balance=User.balance+delta))
    if changed.rowcount!=1:
        raise BusinessError('积分余额不足',409)
    user=db.get(User,user_id)
    db.refresh(user,attribute_names=['balance'])
    entry=PointTransaction(user_id=user_id,kind=kind,reference_id=reference_id,
                           delta=delta,balance_after=user.balance,
                           description=description[:200])
    db.add(entry)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(PointTransaction).where(
            PointTransaction.kind==kind,PointTransaction.reference_id==reference_id))
        if existing and existing.user_id==user_id and existing.delta==delta:
            return existing
        raise BusinessError('积分业务流水冲突',409)
    return entry

def backfill_ledger_snapshots(db):
    """Populate balance snapshots for ledgers created before the additive column."""
    rows=db.scalars(select(PointTransaction).order_by(
        PointTransaction.user_id,PointTransaction.id)).all()
    running={};changed=False
    for item in rows:
        running[item.user_id]=running.get(item.user_id,0)+item.delta
        if item.balance_after!=running[item.user_id]:
            item.balance_after=running[item.user_id];changed=True
    if changed:db.commit()
    return len(rows)

def ledger_summary(db,user_id):
    earned=db.scalar(select(func.coalesce(func.sum(PointTransaction.delta),0)).where(
        PointTransaction.user_id==user_id,PointTransaction.delta>0)) or 0
    spent=db.scalar(select(func.coalesce(func.sum(-PointTransaction.delta),0)).where(
        PointTransaction.user_id==user_id,PointTransaction.delta<0)) or 0
    count=db.scalar(select(func.count()).select_from(PointTransaction).where(
        PointTransaction.user_id==user_id)) or 0
    user=db.get(User,user_id)
    net=earned-spent
    return {'balance':user.balance,'total_earned':earned,'total_spent':spent,
            'net_change':net,'transaction_count':count,'consistent':user.balance==net}

def submit_trip(db,user_id,client_trip_id,mode,distance_km,source='simulated',evidence_reference=None):
    if source not in TRIP_SOURCES:
        raise BusinessError('行程来源无效')
    rule=get_active_rule(db)
    factors={x.mode:x.grams_per_km for x in rule.factors}
    if mode not in factors:
        raise BusinessError('当前规则不支持该出行方式')
    meters,saved,points=calculate_with_factors(mode,distance_km,rule.baseline_g_per_km,
                                                factors[mode],rule.points_per_kg)
    existing=db.scalar(select(Trip).where(Trip.user_id==user_id,Trip.client_trip_id==client_trip_id))
    if existing:
        if (existing.mode,existing.distance_m)!=(mode,meters):
            raise BusinessError('行程编号已用于其他行程',409)
        return existing
    trip=Trip(user_id=user_id,client_trip_id=client_trip_id,mode=mode,distance_m=meters,saved_g=saved,points=points)
    try:
        db.add(trip);db.flush()
        db.add(TripCalculation(trip_id=trip.id,rule_id=rule.id,rule_version=rule.version,
                               baseline_g_per_km=rule.baseline_g_per_km,
                               mode_g_per_km=factors[mode],points_per_kg=rule.points_per_kg,
                               distance_m=meters,saved_g=saved,points=points))
        db.add(TripEvidence(trip_id=trip.id,source_type=source,
                            external_reference=evidence_reference,
                            payload=json.dumps({'mode':mode,'distance_km':str(distance_km)},ensure_ascii=False)))
        db.add(OutboxEvent(kind='TripSubmitted',ref_id=trip.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Trip).where(Trip.user_id==user_id,Trip.client_trip_id==client_trip_id))
        if existing and (existing.mode,existing.distance_m)==(mode,meters): return existing
        raise BusinessError('行程编号冲突，请重新提交',409)
    return trip

def redeem(db,user_id,product_id):
    p=db.scalar(select(Product).join(User,User.id==Product.merchant_id).where(
        Product.id==product_id,Product.active.is_(True),User.enabled.is_(True)))
    if p is None:raise BusinessError('商品不存在或已下架',404)
    try:
        red=Redemption(user_id=user_id,product_id=p.id,product_name=p.name,points=p.cost)
        db.add(red);db.flush()
        adjust_inventory(db,p.id,-1,'REDEMPTION',f'redemption-{red.id}',
                         '兑换扣减库存',red.id)
        post_points(db,user_id,'REDEEM',red.id,-p.cost,'兑换 '+p.name)
        db.add(OutboxEvent(kind='RedemptionCreated',ref_id=red.id))
        db.commit()
        return red
    except Exception:
        db.rollback();raise

def refund_redemption(db,user_id,redemption_id):
    """Return points for a resident-owned order before merchant fulfillment."""
    red=db.get(Redemption,redemption_id)
    if red is None or red.user_id!=user_id:
        raise BusinessError('兑换订单不存在',404)
    if red.status=='REFUNDED':
        return red
    existing=db.scalar(select(PointTransaction).where(
        PointTransaction.kind=='REFUND',PointTransaction.reference_id==red.id,PointTransaction.user_id==user_id))
    if existing:
        red.status='REFUNDED'
        red.refunded_at=red.refunded_at or utcnow()
        red.updated_at=utcnow()
        settlement=db.get(Settlement,red.id)
        if settlement and settlement.status!='SETTLED':
            settlement.status='CANCELLED';settlement.cancelled_at=settlement.cancelled_at or utcnow()
        db.commit()
        return red
    if red.status!='TO_FULFILL':
        raise BusinessError('当前订单状态不允许退款',409)
    product=db.get(Product,red.product_id)
    if product is None:raise BusinessError('原商品不存在，无法回补库存',409)
    try:
        now=utcnow()
        claimed=db.execute(update(Redemption).where(
            Redemption.id==redemption_id,Redemption.user_id==user_id,Redemption.status=='TO_FULFILL')
            .values(status='REFUNDED',refunded_at=now,updated_at=now))
        if claimed.rowcount!=1:
            db.rollback()
            if red.status=='REFUNDED':
                return red
            raise BusinessError('当前订单状态不允许退款',409)
        adjust_inventory(db,product.id,1,'REFUND',f'refund-{red.id}',
                         '退款回补库存',red.id)
        post_points(db,user_id,'REFUND',red.id,red.points,'兑换退款 '+red.product_name)
        settlement=db.get(Settlement,red.id)
        if settlement and settlement.status!='SETTLED':
            settlement.status='CANCELLED';settlement.cancelled_at=now
        db.commit()
        return red
    except Exception:
        db.rollback();raise

def fulfill_redemption(db,merchant_id,redemption_id):
    red=db.get(Redemption,redemption_id)
    settlement=db.get(Settlement,redemption_id)
    if not red or not settlement or settlement.merchant_id!=merchant_id:
        raise BusinessError('订单不存在',404)
    if red.status=='FULFILLED':return red
    now=utcnow()
    claimed=db.execute(update(Redemption).where(
        Redemption.id==redemption_id,Redemption.status=='TO_FULFILL')
        .values(status='FULFILLED',fulfilled_at=now,updated_at=now))
    if claimed.rowcount!=1:
        db.rollback()
        if red.status=='FULFILLED':
            return red
        raise BusinessError('订单状态不允许核销',409)
    db.commit();db.refresh(red)
    return red

def settle_redemption(db,redemption_id):
    settlement=db.get(Settlement,redemption_id)
    if not settlement:raise BusinessError('清算单不存在',404)
    red=db.get(Redemption,redemption_id)
    if not red or red.status!='FULFILLED':raise BusinessError('商户尚未履约',409)
    if settlement.status!='SETTLED':
        settlement.status='SETTLED';settlement.settled_at=utcnow();settlement.cancelled_at=None
        db.commit()
    return settlement

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
                if trip:
                    txn=db.scalar(select(PointTransaction).where(
                        PointTransaction.kind=='TRIP',PointTransaction.reference_id==trip.id))
                    if trip.status=='PENDING' or (trip.points>0 and not txn):
                        if trip.points>0:
                            post_points(db,trip.user_id,'TRIP',trip.id,trip.points,'绿色出行积分')
                        trip.status='AWARDED'
            elif e.kind=='RedemptionCreated':
                red=db.get(Redemption,e.ref_id)
                if red:
                    p=db.get(Product,red.product_id)
                    settlement=db.get(Settlement,red.id)
                    if not settlement:db.add(Settlement(redemption_id=red.id,merchant_id=p.merchant_id,points=red.points))
                    if red.status=='PROCESSING':
                        red.status='TO_FULFILL';red.updated_at=utcnow()
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
    fulfilled=db.scalar(select(func.count()).select_from(Redemption).where(Redemption.status=='FULFILLED')) or 0
    refunded=db.scalar(select(func.count()).select_from(Redemption).where(Redemption.status=='REFUNDED')) or 0
    pending_settlements=db.scalar(select(func.count()).select_from(Settlement).where(Settlement.status=='PENDING')) or 0
    settled_points=db.scalar(select(func.coalesce(func.sum(Settlement.points),0)).where(Settlement.status=='SETTLED')) or 0
    low_stock=db.scalar(select(func.count()).select_from(Product).where(Product.active==True,Product.stock<=5)) or 0
    return {'trips':trips,'saved_kg':round(grams/1000,3),'issued_points':points,'redemptions':redeems,
            'fulfilled_orders':fulfilled,'refunded_orders':refunded,
            'pending_settlements':pending_settlements,'settled_points':settled_points,
            'low_stock_products':low_stock}
