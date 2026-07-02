from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AllowedEmail, AuditAction, AuditLog, User, UserRole, UserStatus

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return "pbkdf2_sha256$260000$%s$%s" % (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(expected, base64.b64decode(digest))
    except Exception:
        return False


def create_access_token(user: User) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {"sub": str(user.id), "email": user.email, "role": user.role.value, "exp": expires_at}
    return jwt.encode(payload, settings.app_secret, algorithm="HS256")


def verify_google_credential(credential: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID не настроен")
    try:
        info = id_token.verify_oauth2_token(credential, requests.Request(), settings.google_client_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Google-токен не прошел проверку") from exc
    if not info.get("email_verified"):
        raise HTTPException(status_code=403, detail="Email Google-аккаунта не подтвержден")
    return info


def login_or_create_user(db: Session, email: str, full_name: str | None) -> User:
    normalized_email = email.strip().lower()
    allowed = db.scalar(select(AllowedEmail).where(AllowedEmail.email == normalized_email))
    if allowed is None or not allowed.is_active:
        raise HTTPException(status_code=403, detail="Email не входит в список разрешенных")

    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        user = User(email=normalized_email, full_name=full_name, role=allowed.role, status=UserStatus.active)
        db.add(user)
        db.flush()
    else:
        user.full_name = full_name or user.full_name
        user.role = allowed.role

    if user.status == UserStatus.blocked:
        raise HTTPException(status_code=403, detail="Пользователь заблокирован")

    db.add(AuditLog(user_id=user.id, action=AuditAction.login, entity_type="user", entity_id=user.id, details=user.email))
    db.commit()
    db.refresh(user)
    return user


def register_user(db: Session, email: str, password: str, full_name: str | None) -> User:
    normalized_email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.manager,
        status=UserStatus.pending,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_with_password(db: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if user.status == UserStatus.pending:
        raise HTTPException(status_code=403, detail="Аккаунт ожидает одобрения администратора")
    if user.status == UserStatus.blocked:
        raise HTTPException(status_code=403, detail="Пользователь заблокирован")
    db.add(AuditLog(user_id=user.id, action=AuditAction.login, entity_type="user", entity_id=user.id, details=user.email))
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials is not None else request.query_params.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.app_secret, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна") from exc
    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден или заблокирован")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Нужна роль администратора")
    return user
