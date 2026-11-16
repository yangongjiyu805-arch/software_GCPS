"""Small email-code delivery adapter for optional passwordless authentication."""
import hashlib
import hmac
import os
import smtplib
import secrets
from email.message import EmailMessage


CODE_TTL_SECONDS = 300
CODE_COOLDOWN_SECONDS = 60
CODE_MAX_ATTEMPTS = 5


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_code() -> str:
    return f'{secrets.randbelow(1_000_000):06d}'


def code_digest(email: str, code: str) -> str:
    secret = os.getenv('JWT_SECRET', 'local-dev-secret-REPLACE-BEFORE-DEPLOYMENT').encode('utf-8')
    payload = f'greengo-email-code:{normalize_email(email)}:{code}'.encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def send_email_code(email: str, code: str) -> str:
    """Deliver a code through console demo mode or configured SMTP."""
    mode = os.getenv('EMAIL_DELIVERY', 'console').strip().lower()
    if mode == 'console':
        print(f'[GreenGo email-code] to={normalize_email(email)} code={code}', flush=True)
        return 'console'
    if mode != 'smtp':
        raise RuntimeError('EMAIL_DELIVERY 必须为 console 或 smtp')

    host = os.getenv('SMTP_HOST', '').strip()
    sender = os.getenv('SMTP_FROM', '').strip() or os.getenv('SMTP_USERNAME', '').strip()
    if not host or not sender:
        raise RuntimeError('SMTP 模式需要设置 SMTP_HOST 和 SMTP_FROM')
    try:
        port = int(os.getenv('SMTP_PORT', '465'))
    except ValueError as exc:
        raise RuntimeError('SMTP_PORT 必须是整数') from exc

    message = EmailMessage()
    message['Subject'] = 'GreenGo 登录验证码'
    message['From'] = sender
    message['To'] = normalize_email(email)
    message.set_content(
        f'你的 GreenGo 登录验证码是：{code}\n\n验证码 5 分钟内有效，使用一次后失效。'
    )
    username = os.getenv('SMTP_USERNAME', '').strip()
    password = os.getenv('SMTP_PASSWORD', '')
    use_ssl = os.getenv('SMTP_USE_SSL', '1').strip().lower() in {'1', 'true', 'yes'}
    try:
        client = smtplib.SMTP_SSL(host, port, timeout=15) if use_ssl else smtplib.SMTP(host, port, timeout=15)
        with client:
            if not use_ssl:
                client.starttls()
            if username:
                client.login(username, password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise RuntimeError('验证码邮件发送失败，请检查 SMTP 配置') from exc
    return 'smtp'
