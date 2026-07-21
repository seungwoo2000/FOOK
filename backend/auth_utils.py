from __future__ import annotations
import base64, hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

PBKDF2_ROUNDS = 310_000

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ROUNDS)
    return f'pbkdf2_sha256${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}'

def verify_password(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt_b64, digest_b64 = encoded.split('$', 3)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def issue_session(conn, user_id: str, days: int = 30) -> str:
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    conn.execute(text('INSERT INTO auth_sessions(user_id, token_hash, expires_at) VALUES (:u,:t,:e)'), {'u':user_id,'t':token_hash,'e':expires})
    return token

def resolve_user(conn, token: str | None):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return conn.execute(text('''
      SELECT u.id, u.email, u.display_name, u.is_active
      FROM auth_sessions s JOIN app_users u ON u.id=s.user_id
      WHERE s.token_hash=:t AND s.revoked_at IS NULL AND s.expires_at > now() AND u.is_active=true
    '''), {'t':token_hash}).mappings().first()
