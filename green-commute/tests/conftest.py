"""Keep all test runs, including individual files, on a disposable database."""
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from sqlalchemy.engine import make_url


test_url=os.getenv('GREENGO_TEST_DATABASE_URL')
if test_url:
    parsed=make_url(test_url)
    if parsed.get_backend_name()!='mysql' or not (parsed.database or '').startswith('greengo_test_'):
        raise RuntimeError('Use a disposable MySQL schema named greengo_test_* for the test suite')
else:
    test_db=Path(tempfile.gettempdir())/f'greengo-tests-{uuid4().hex}.db'
    test_url='sqlite:///'+test_db.as_posix()

os.environ['DATABASE_URL']=test_url
os.environ['JWT_SECRET']='test-secret-for-isolated-integration-suite'
