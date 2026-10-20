"""Database setup. SQLite is the zero-config local profile; set DATABASE_URL for MySQL."""
import os
from sqlalchemy import create_engine, event
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

def get_db():
    with SessionLocal() as session:
        yield session
