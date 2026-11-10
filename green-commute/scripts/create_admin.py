"""Create an administrator or rotate an existing administrator's password."""
import argparse
from getpass import getpass
import re

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, ensure_runtime_schema
from app.models import User
from app.security import hash_password


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username')
    parser.add_argument('--reset-password', action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_]{3,48}', args.username):
        parser.error('用户名须为 3–48 位英文字母、数字或下划线')
    password=getpass('管理员密码（输入隐藏）: ')
    if not 8<=len(password)<=128 or password!=getpass('确认密码: '):
        parser.error('请输入 8–128 位密码并确认一致')

    ensure_runtime_schema()
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.username==args.username))
        if args.reset_password:
            if not account or account.role!='admin':
                parser.error('管理员账号不存在')
            db.execute(update(User).where(User.id==account.id).values(
                password_hash=hash_password(password),session_version=User.session_version+1))
        else:
            if account:
                parser.error('用户名已存在')
            db.add(User(username=args.username,display_name=args.username,role='admin',
                        password_hash=hash_password(password)))
        try:
            db.commit()
        except IntegrityError:
            parser.error('用户名已存在')
    print(f'管理员 {args.username} 已配置')


if __name__=='__main__':
    main()
