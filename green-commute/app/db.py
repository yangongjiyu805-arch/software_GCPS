"""Database setup. SQLite is the zero-config local profile; set DATABASE_URL for MySQL."""
import os
from sqlalchemy import create_engine, event, inspect, select, text
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
    """Upgrade old databases in place. Web, worker and the upgrade command share this path."""
    from .models import MerchantCategory, Product

    additions={
        'users':{'enabled':'BOOLEAN NOT NULL DEFAULT 1',
                 'session_version':'INTEGER NOT NULL DEFAULT 0'},
        'point_transactions':{'balance_after':'INTEGER NOT NULL DEFAULT 0'},
        'redemptions':{
            'updated_at':'DATETIME',
            'fulfilled_at':'DATETIME',
            'refunded_at':'DATETIME',
        },
        'settlements':{'cancelled_at':'DATETIME'},
    }
    with engine.connect() as conn:
        mysql=conn.dialect.name in ('mysql', 'mariadb')
        lock_name="CONCAT('greengo-schema-',MD5(DATABASE()))"
        if conn.dialect.name=='sqlite':
            conn.exec_driver_sql('BEGIN IMMEDIATE')
        elif mysql and conn.scalar(text(f'SELECT GET_LOCK({lock_name},30)'))!=1:
            raise RuntimeError('Could not lock the GreenGo database for upgrade')
        try:
            Base.metadata.create_all(conn)
            for table,columns_to_add in additions.items():
                columns={col['name'] for col in inspect(conn).get_columns(table)}
                for column,definition in columns_to_add.items():
                    if column not in columns:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {definition}'))
            conn.execute(text('UPDATE redemptions SET updated_at=created_at WHERE updated_at IS NULL'))

            products=Product.__table__
            categories=MerchantCategory.__table__
            legacy=conn.execute(select(products.c.id,products.c.merchant_id,products.c.category)
                                .order_by(products.c.id)).all()
            canonical_names={}
            for product_id,merchant_id,old_name in legacy:
                name=old_name.strip() or '生活好物'
                key=(merchant_id,name)
                if key not in canonical_names:
                    existing=conn.scalar(select(categories.c.name).where(
                        categories.c.merchant_id==merchant_id,categories.c.name==name))
                    if existing is None:
                        conn.execute(categories.insert().values(merchant_id=merchant_id,name=name))
                    canonical_names[key]=existing or name
                canonical=canonical_names[key]
                if canonical!=old_name:
                    conn.execute(products.update().where(products.c.id==product_id).values(category=canonical))
            conn.commit()
        finally:
            if mysql:
                conn.execute(text(f'SELECT RELEASE_LOCK({lock_name})'))

def get_db():
    with SessionLocal() as session:
        yield session
