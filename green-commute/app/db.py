"""Database setup. SQLite is the zero-config local profile; set DATABASE_URL for MySQL."""
import os
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./green_commute.db')
kwargs = {'connect_args': {'check_same_thread': False, 'timeout': 30}} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, **kwargs)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute('PRAGMA foreign_keys=ON')
        cur.execute('PRAGMA busy_timeout=30000')
        cur.execute('PRAGMA journal_mode=WAL')
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def ensure_runtime_schema():
    """Apply the small additive migrations needed by the zero-config profile.

    The project intentionally keeps deployment lightweight, so an additive ledger
    column is upgraded at startup for existing SQLite/MySQL databases instead of
    requiring a separate migration command during the classroom demo.
    """
    inspector=inspect(engine)
    if 'point_transactions' not in inspector.get_table_names():
        return
    columns={col['name'] for col in inspector.get_columns('point_transactions')}
    if 'balance_after' not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                'ALTER TABLE point_transactions '
                'ADD COLUMN balance_after INTEGER NOT NULL DEFAULT 0'
            ))

def get_db():
    with SessionLocal() as session:
        yield session
