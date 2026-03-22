import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")


def _user_info(user: dict) -> UserInfo:
    return UserInfo(id=str(user["_id"]), email=user["email"], name=user["name"], created_at=user["created_at"])


async def _issue_tokens(user: dict) -> AuthResponse:
    user_id = str(user["_id"])
    access = create_access_token(user_id)
    refresh, jti = create_refresh_token(user_id)

    db = get_db()
    await db.refresh_tokens.insert_one({
        "user_id": user["_id"],
        "token_hash": hash_token(refresh),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        "created_at": datetime.now(timezone.utc),
    })

    return AuthResponse(access_token=access, refresh_token=refresh, user=_user_info(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    db = get_db()
    email = req.email.lower()

    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    now = datetime.now(timezone.utc)
    result = await db.users.insert_one({
        "email": email,
        "password_hash": hash_password(req.password),
        "name": req.name,
        "created_at": now,
        "updated_at": now,
    })

    user = await db.users.find_one({"_id": result.inserted_id})
    return await _issue_tokens(user)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    from app.core.security import is_account_locked, record_failed_login, clear_login_attempts

    email = req.email.lower()
    if is_account_locked(email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account temporarily locked due to too many failed attempts. Try again later.")

    db = get_db()
    user = await db.users.find_one({"email": email})

    if not user or not verify_password(req.password, user["password_hash"]):
        record_failed_login(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    clear_login_attempts(email)
    return await _issue_tokens(user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(req: RefreshRequest):
    from jose import JWTError, jwt as jose_jwt

    try:
        payload = jose_jwt.decode(req.refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    db = get_db()
    token_hash = hash_token(req.refresh_token)

    # Revoke old token
    result = await db.refresh_tokens.delete_one({"token_hash": token_hash})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token already used or revoked")

    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    except (InvalidId, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return await _issue_tokens(user)


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    db = get_db()
    await db.refresh_tokens.delete_many({"user_id": user["_id"]})
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserInfo)
async def me(user: dict = Depends(get_current_user)):
    return _user_info(user)
