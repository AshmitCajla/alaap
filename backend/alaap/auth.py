"""Owner logins: PBKDF2 password hashes and signed JWT session tokens."""

import base64
import hashlib
import hmac
import os
import time

import jwt

from . import config

ITERATIONS = 200_000
TOKEN_DAYS = 30


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iters))
        return hmac.compare_digest(check, base64.b64decode(digest))
    except ValueError:
        return False


def make_token(user_id: int, business_id: int) -> str:
    payload = {"sub": str(user_id), "biz": business_id, "exp": int(time.time()) + TOKEN_DAYS * 86400}
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def read_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
