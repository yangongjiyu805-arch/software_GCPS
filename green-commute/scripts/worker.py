"""Run the transactional outbox in a single independent worker process."""
import time
from app.db import SessionLocal,Base,engine
from app.services import process_pending
if __name__=='__main__':
    Base.metadata.create_all(engine)
    print('Outbox worker running; Ctrl+C to stop',flush=True)
    while True:
        with SessionLocal() as db:
            count=process_pending(db)
        if count: print('processed',count,flush=True)
        time.sleep(2)
