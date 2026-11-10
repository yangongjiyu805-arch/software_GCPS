"""PBKDF2 password hashing and signed short-lived auth tokens."""
import base64, hashlib, hmac, os
from datetime import datetime, timedelta, timezone
import jwt

JWT_SECRET = os.getenv('JWT_SECRET', 'local-dev-secret-REPLACE-BEFORE-DEPLOYMENT')

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256',password.encode(),salt,240_000)
    return 'pbkdf2_sha256$240000$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(digest).decode()

def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, count, salt, digest = stored.split('$')
        if scheme!='pbkdf2_sha256':return False
        candidate=hashlib.pbkdf2_hmac('sha256',password.encode(),base64.b64decode(salt),int(count))
        return hmac.compare_digest(candidate,base64.b64decode(digest))
    except (ValueError,TypeError):return False

def create_token(user_id: int, session_version: int) -> str:
    now=datetime.now(timezone.utc)
    return jwt.encode({'sub':str(user_id),'ver':session_version,'iat':now,'exp':now+timedelta(hours=12)},JWT_SECRET,algorithm='HS256')

def decode_token(token: str) -> tuple[int, int]:
    payload=jwt.decode(token,JWT_SECRET,algorithms=['HS256'])
    return int(payload['sub']), int(payload.get('ver', 0))
