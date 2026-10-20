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

class PointTransaction(Base):
    __tablename__='point_transactions'
    __table_args__=(UniqueConstraint('kind','reference_id',name='uq_ledger_business'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    kind: Mapped[str]=mapped_column(String(20))
    reference_id: Mapped[int]=mapped_column(Integer)
    delta: Mapped[int]=mapped_column(Integer)
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
