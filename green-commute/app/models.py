from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    username: Mapped[str]=mapped_column(String(48),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(200))
    display_name: Mapped[str]=mapped_column(String(80))
    role: Mapped[str]=mapped_column(String(15),default='resident')
    balance: Mapped[int]=mapped_column(Integer,default=0)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class Trip(Base):
    __tablename__='trips'
    __table_args__=(UniqueConstraint('user_id','client_trip_id',name='uq_user_trip'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    client_trip_id: Mapped[str]=mapped_column(String(72))
    mode: Mapped[str]=mapped_column(String(12))
    distance_m: Mapped[int]=mapped_column(Integer)
    saved_g: Mapped[int]=mapped_column(Integer)
    points: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(18),default='PENDING')
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    calculation: Mapped['TripCalculation|None'] = relationship(back_populates='trip', uselist=False, cascade='all, delete-orphan')
    evidence: Mapped[list['TripEvidence']] = relationship(back_populates='trip', order_by='TripEvidence.id', cascade='all, delete-orphan')

class EmissionRule(Base):
    """Versioned teaching rule set used to calculate one trip."""
    __tablename__='emission_rules'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    version: Mapped[str]=mapped_column(String(32),unique=True,index=True)
    name: Mapped[str]=mapped_column(String(120))
    baseline_g_per_km: Mapped[int]=mapped_column(Integer)
    points_per_kg: Mapped[int]=mapped_column(Integer,default=10)
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    effective_from: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    effective_to: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    factors: Mapped[list['EmissionFactor']] = relationship(back_populates='rule', cascade='all, delete-orphan')

class EmissionFactor(Base):
    __tablename__='emission_factors'
    __table_args__=(UniqueConstraint('rule_id','mode',name='uq_rule_mode_factor'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    rule_id: Mapped[int]=mapped_column(ForeignKey('emission_rules.id'),index=True)
    mode: Mapped[str]=mapped_column(String(12))
    grams_per_km: Mapped[int]=mapped_column(Integer)
    rule: Mapped[EmissionRule] = relationship(back_populates='factors')

class TripCalculation(Base):
    """Immutable calculation snapshot for audit and future rule changes."""
    __tablename__='trip_calculations'
    trip_id: Mapped[int]=mapped_column(ForeignKey('trips.id'),primary_key=True)
    rule_id: Mapped[int]=mapped_column(ForeignKey('emission_rules.id'),index=True)
    rule_version: Mapped[str]=mapped_column(String(32))
    baseline_g_per_km: Mapped[int]=mapped_column(Integer)
    mode_g_per_km: Mapped[int]=mapped_column(Integer)
    points_per_kg: Mapped[int]=mapped_column(Integer)
    distance_m: Mapped[int]=mapped_column(Integer)
    saved_g: Mapped[int]=mapped_column(Integer)
    points: Mapped[int]=mapped_column(Integer)
    calculated_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    trip: Mapped[Trip] = relationship(back_populates='calculation')
    rule: Mapped[EmissionRule] = relationship()

class TripEvidence(Base):
    """Source metadata for a submitted trip; the prototype may use simulated data."""
    __tablename__='trip_evidence'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    trip_id: Mapped[int]=mapped_column(ForeignKey('trips.id'),index=True)
    source_type: Mapped[str]=mapped_column(String(20))
    external_reference: Mapped[str|None]=mapped_column(String(120),nullable=True)
    payload: Mapped[str|None]=mapped_column(Text,nullable=True)
    captured_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    trip: Mapped[Trip] = relationship(back_populates='evidence')

class PointTransaction(Base):
    __tablename__='point_transactions'
    __table_args__=(UniqueConstraint('kind','reference_id',name='uq_ledger_business'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    kind: Mapped[str]=mapped_column(String(20))
    reference_id: Mapped[int]=mapped_column(Integer)
    delta: Mapped[int]=mapped_column(Integer)
    balance_after: Mapped[int]=mapped_column(Integer,default=0)
    description: Mapped[str]=mapped_column(String(200))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class Product(Base):
    __tablename__='products'
    id: Mapped[int]=mapped_column(primary_key=True)
    merchant_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    name: Mapped[str]=mapped_column(String(90))
    description: Mapped[str]=mapped_column(String(300))
    category: Mapped[str]=mapped_column(String(40))
    icon: Mapped[str]=mapped_column(String(16),default='gift')
    cost: Mapped[int]=mapped_column(Integer)
    stock: Mapped[int]=mapped_column(Integer)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class Redemption(Base):
    __tablename__='redemptions'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    product_id: Mapped[int]=mapped_column(ForeignKey('products.id'))
    product_name: Mapped[str]=mapped_column(String(90))
    points: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(25),default='PROCESSING')
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class Settlement(Base):
    __tablename__='settlements'
    redemption_id: Mapped[int]=mapped_column(ForeignKey('redemptions.id'),primary_key=True)
    merchant_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    points: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(20),default='PENDING')
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    settled_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class OutboxEvent(Base):
    __tablename__='outbox_events'
    id: Mapped[int]=mapped_column(primary_key=True)
    kind: Mapped[str]=mapped_column(String(40))
    ref_id: Mapped[int]=mapped_column(Integer)
    state: Mapped[str]=mapped_column(String(16),default='PENDING')
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    error: Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('kind','ref_id',name='uq_outbox_business'),)


class SupportTicket(Base):
    """A user-owned customer-service conversation; admins act as agents."""
    __tablename__ = 'support_tickets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    category: Mapped[str] = mapped_column(String(24))
    subject: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default='OPEN', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class SupportMessage(Base):
    __tablename__ = 'support_messages'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('support_tickets.id'), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
