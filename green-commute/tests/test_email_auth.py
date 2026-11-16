"""Optional email-code authentication keeps the password flow intact."""
import pytest
from fastapi.testclient import TestClient

from datetime import timedelta
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import EmailCode, User, utcnow


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ENVIRONMENT', 'test')
    monkeypatch.setenv('SEED_DEMO_DATA', '1')
    monkeypatch.setenv('DEMO_PASSWORD', 'Demo@123456')
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def email_sender(monkeypatch):
    sent = {}

    def capture(email, code):
        sent[email] = code
        return 'test'

    monkeypatch.setattr('app.main.send_email_code', capture)
    return sent


def test_email_code_creates_resident_and_is_one_time(client, email_sender):
    address = '  New.User@Example.COM '
    requested = client.post('/api/auth/email/send-code', json={'email': address})
    assert requested.status_code == 200
    code = email_sender['new.user@example.com']
    logged_in = client.post('/api/auth/email/login', json={'email': address, 'code': code})
    assert logged_in.status_code == 200, logged_in.text
    body = logged_in.json()
    assert body['token_type'] == 'bearer'
    assert body['user']['role'] == 'resident'
    assert body['user']['email'] == 'new.user@example.com'
    assert client.post('/api/auth/email/login', json={'email': address, 'code': code}).status_code == 401
    with SessionLocal() as db:
        user = db.query(User).filter_by(email='new.user@example.com').one()
        assert user.role == 'resident'


def test_email_code_wrong_attempts_and_existing_user(client, email_sender):
    address = 'returning@example.com'
    assert client.post('/api/auth/email/send-code', json={'email': address}).status_code == 200
    code = email_sender[address]
    wrong_code = '000000' if code != '000000' else '999999'
    for _ in range(4):
        assert client.post('/api/auth/email/login', json={'email': address, 'code': wrong_code}).status_code == 401
    assert client.post('/api/auth/email/login', json={'email': address, 'code': code}).status_code == 200
    with SessionLocal() as db:
        row = db.query(EmailCode).filter_by(email=address).order_by(EmailCode.id.desc()).first()
        row.created_at = utcnow() - timedelta(seconds=61)
        db.commit()
    assert client.post('/api/auth/email/send-code', json={'email': address}).status_code == 200
    again = client.post('/api/auth/email/login', json={'email': address, 'code': email_sender[address]})
    assert again.status_code == 200
    with SessionLocal() as db:
        assert db.query(User).filter_by(email=address).count() == 1


def test_email_validation_and_admin_directory(client, email_sender):
    assert client.post('/api/auth/email/send-code', json={'email': 'invalid'}).status_code == 422
    assert client.post('/api/auth/email/login', json={'email': 'invalid', 'code': '123'}).status_code == 422
    address = 'listed@example.com'
    client.post('/api/auth/email/send-code', json={'email': address})
    login = client.post('/api/auth/email/login', json={'email': address, 'code': email_sender[address]})
    assert login.status_code == 200
    admin = client.post('/api/auth/login', json={'username': 'admin', 'password': 'Demo@123456'}).json()
    accounts = client.get('/api/admin/accounts', headers={'Authorization': 'Bearer '+admin['access_token']})
    listed = next(x for x in accounts.json() if x['email'] == address)
    assert listed['role'] == 'resident'
