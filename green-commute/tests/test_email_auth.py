"""Optional email registration and login keep the password flow intact."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

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


def age_latest_code(email):
    with SessionLocal() as db:
        row=db.query(EmailCode).filter_by(email=email).order_by(EmailCode.id.desc()).first()
        row.created_at=utcnow()-timedelta(seconds=61)
        db.commit()


def test_email_register_then_existing_email_login(client, email_sender):
    address='  New.User@Example.COM '
    assert client.post('/api/auth/email/send-code',json={'email':address}).status_code==200
    registered=client.post('/api/auth/email/register',json={
        'email':address,'code':email_sender['new.user@example.com']})
    assert registered.status_code==201,registered.text
    body=registered.json()
    assert body['token_type']=='bearer' and body['user']['role']=='resident'
    assert body['user']['email']=='new.user@example.com'
    assert client.post('/api/auth/email/login',json={
        'email':address,'code':email_sender['new.user@example.com']}).status_code==401

    age_latest_code('new.user@example.com')
    assert client.post('/api/auth/email/send-code',json={'email':address}).status_code==200
    logged_in=client.post('/api/auth/email/login',json={
        'email':address,'code':email_sender['new.user@example.com']})
    assert logged_in.status_code==200,logged_in.text
    with SessionLocal() as db:
        assert db.query(User).filter_by(email='new.user@example.com').count()==1


def test_unregistered_email_login_requires_email_registration(client, email_sender):
    address='new-user@example.com'
    assert client.post('/api/auth/email/send-code',json={'email':address}).status_code==200
    code=email_sender[address]
    unregistered=client.post('/api/auth/email/login',json={'email':address,'code':code})
    assert unregistered.status_code==404
    registered=client.post('/api/auth/email/register',json={'email':address,'code':code})
    assert registered.status_code==201
    assert client.post('/api/auth/email/register',json={'email':address,'code':code}).status_code==409


def test_email_code_wrong_attempts_and_admin_directory(client, email_sender):
    address='listed@example.com'
    assert client.post('/api/auth/email/send-code',json={'email':address}).status_code==200
    code=email_sender[address]
    assert client.post('/api/auth/email/register',json={'email':address,'code':code}).status_code==201
    age_latest_code(address)
    assert client.post('/api/auth/email/send-code',json={'email':address}).status_code==200
    code=email_sender[address]
    wrong_code='000000' if code!='000000' else '999999'
    for _ in range(4):
        assert client.post('/api/auth/email/login',json={'email':address,'code':wrong_code}).status_code==401
    assert client.post('/api/auth/email/login',json={'email':address,'code':code}).status_code==200
    admin=client.post('/api/auth/login',json={'username':'admin','password':'Demo@123456'}).json()
    accounts=client.get('/api/admin/accounts',headers={'Authorization':'Bearer '+admin['access_token']})
    listed=next(item for item in accounts.json() if item['email']==address)
    assert listed['role']=='resident'


def test_email_validation(client, email_sender):
    assert client.post('/api/auth/email/send-code',json={'email':'invalid'}).status_code==422
    assert client.post('/api/auth/email/login',json={'email':'invalid','code':'123'}).status_code==422
