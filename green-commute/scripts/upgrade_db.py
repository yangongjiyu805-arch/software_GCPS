"""Apply additive database upgrades before restarting a deployed GreenGo instance."""
from app.db import SessionLocal, ensure_runtime_schema
from app.services import backfill_inventory_opening, backfill_ledger_snapshots, ensure_default_rule


def main():
    ensure_runtime_schema()
    with SessionLocal() as db:
        ensure_default_rule(db)
        backfill_ledger_snapshots(db)
        backfill_inventory_opening(db)
    print('GreenGo database is up to date.')


if __name__=='__main__':
    main()
