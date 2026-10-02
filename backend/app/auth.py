import hashlib
import hmac
import secrets
from datetime import timedelta, timezone
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import get_config
from .database import get_db
from .models import AuthSession, LoginAttempt, User, utcnow

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "pi_session"


def hash_password(password):
    return hasher.hash(password)


def token_hash(token):
    return hmac.new(get_config().secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def user_dict(user):
    return {k: getattr(user, k) for k in ("id", "username", "display_name", "role", "active")}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    session = db.get(AuthSession, token_hash(token)) if token else None
    if not session or aware(session.expires_at) <= utcnow():
        raise HTTPException(401, "Login required")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account inactive")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf_token):
            raise HTTPException(403, "Invalid CSRF token")
    request.state.session = session
    return user


def roles(*allowed):
    def dependency(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Insufficient permission")
        return user

    return dependency


admin = roles("admin")
editor = roles("admin", "engineer")
operator = roles("admin", "engineer", "team_leader")


def login_user(data, request: Request, response: Response, db: Session):
    origin = request.headers.get("origin")
    if origin:
        public = get_config().public_origin
        if (public and origin.rstrip("/") != public.rstrip("/")) or (
            not public and urlsplit(origin).netloc != request.headers.get("host")
        ):
            raise HTTPException(403, "Login origin rejected")
    # Persist failures across processes. Do not trust client-controlled forwarded IPs.
    source = token_hash(
        (request.client.host if request.client else "unknown") + ":" + data.username.lower()
    )
    since = utcnow() - timedelta(minutes=15)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < since))
    if (
        db.scalar(
            select(func.count()).select_from(LoginAttempt).where(LoginAttempt.source == source)
        )
        >= 10
    ):
        db.commit()
        raise HTTPException(429, "Too many login attempts; retry in 15 minutes")
    user = db.scalar(select(User).where(User.username == data.username))
    try:
        valid = hasher.verify(user.password_hash if user else DUMMY_HASH, data.password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or not user or not user.active:
        db.add(LoginAttempt(source=source))
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
    db.execute(delete(LoginAttempt).where(LoginAttempt.source == source))
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    previous = request.cookies.get(COOKIE)
    if previous:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(previous)))
    token, csrf = secrets.token_urlsafe(48), secrets.token_hex(32)
    db.add(
        AuthSession(
            token_hash=token_hash(token),
            user_id=user.id,
            csrf_token=csrf,
            expires_at=utcnow() + timedelta(hours=get_config().session_hours),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=get_config().cookie_secure,
        samesite="strict",
        path="/api",
        max_age=get_config().session_hours * 3600,
    )
    return {"user": user_dict(user), "csrf_token": csrf}
