"""User authentication API endpoints."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from config.settings import settings
from storage.db.engine import async_session_factory
from storage.db.models import User

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    username: str


class UserInfo(BaseModel):
    user_id: str
    username: str


def _hash_password(password: str) -> str:
    """Hash a password using SHA-256 with a random salt."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{pwd_hash}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, pwd_hash = stored.split(":", 1)
        check = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return secrets.compare_digest(check, pwd_hash)
    except (ValueError, AttributeError):
        return False


def create_token(user_id: str) -> str:
    """Create a JWT token for a user."""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的Token")


async def get_current_user(authorization: str = Header(...)) -> User:
    """Dependency: get current authenticated user from Bearer token."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要Bearer认证")
    token = authorization[7:]
    payload = decode_token(token)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的Token")

    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="用户不存在")
        return user


async def get_optional_user(
    authorization: str | None = Header(None),
) -> User | None:
    """Dependency: get current user if token provided, None otherwise."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    try:
        payload = decode_token(token)
        user_id = payload.get("user_id")
        if not user_id:
            return None
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()
    except Exception:
        return None


@router.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    """Register a new user account."""
    username = req.username.strip()
    password = req.password.strip()

    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少2个字符")
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail="密码至少4个字符")

    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="用户名已存在")

        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username=username,
            hashed_password=_hash_password(password),
        )
        db.add(user)
        await db.commit()

    token = create_token(user_id)
    return AuthResponse(token=token, user_id=user_id, username=username)


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """Login with username and password."""
    username = req.username.strip()
    password = req.password.strip()

    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

    if not user or not _verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user.id)
    return AuthResponse(token=token, user_id=user.id, username=user.username)


@router.get("/auth/me", response_model=UserInfo)
async def get_me(user: User = Depends(get_current_user)):
    """Get current user info."""
    return UserInfo(user_id=user.id, username=user.username)
