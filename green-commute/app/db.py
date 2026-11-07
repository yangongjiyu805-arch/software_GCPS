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
    tables=inspector.get_table_names()
    additions={
        'point_transactions':{'balance_after':'INTEGER NOT NULL DEFAULT 0'},
        'redemptions':{
            'updated_at':'DATETIME',
            'fulfilled_at':'DATETIME',
            'refunded_at':'DATETIME',
        },
        'settlements':{'cancelled_at':'DATETIME'},
    }
    with engine.begin() as conn:
        for table,columns_to_add in additions.items():
            if table not in tables:continue
            columns={col['name'] for col in inspect(conn).get_columns(table)}
            for column,definition in columns_to_add.items():
                if column not in columns:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {definition}'))
        if 'redemptions' in tables:
            conn.execute(text('UPDATE redemptions SET updated_at=created_at WHERE updated_at IS NULL'))

def get_db():
    with SessionLocal() as session:
        yield session
