from datetime import datetime, timezone

import uuid_utils as uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token_str,
    hash_token,
    refresh_token_expiry,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User


async def upsert_user(db: AsyncSession, github_user: dict) -> User:
    github_id = str(github_user["id"])
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    if user:
        user.username = github_user.get("login", user.username)
        user.email = github_user.get("email", user.email)
        user.avatar_url = github_user.get("avatar_url", user.avatar_url)
        user.last_login_at = datetime.now(timezone.utc)
    else:
        user = User(
            id=str(uuid.uuid7()),
            github_id=github_id,
            username=github_user.get("login", ""),
            email=github_user.get("email"),
            avatar_url=github_user.get("avatar_url"),
            role="analyst",
            is_active=True,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user


async def issue_token_pair(db: AsyncSession, user: User) -> tuple[str, str]:
    """Issue a new access + refresh token pair."""
    access_token = create_access_token(user.id, user.role)
    refresh_str = create_refresh_token_str()

    rt = RefreshToken(
        id=str(uuid.uuid7()),
        user_id=user.id,
        token_hash=hash_token(refresh_str),
        expires_at=refresh_token_expiry(),
    )
    db.add(rt)
    await db.commit()
    return access_token, refresh_str


async def rotate_refresh_token(db: AsyncSession, refresh_str: str) -> tuple[str, str] | None:
    """
    Validate a refresh token, revoke it, and issue a new pair.
    Returns None if token is invalid/expired/revoked.
    """
    token_hash = hash_token(refresh_str)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
    )
    rt = result.scalar_one_or_none()

    if not rt:
        return None
    if rt.expires_at < datetime.now(timezone.utc):
        return None

    # Revoke old token
    rt.is_revoked = True
    await db.commit()

    # Load user
    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        return None

    return await issue_token_pair(db, user)


async def revoke_refresh_token(db: AsyncSession, refresh_str: str) -> bool:
    token_hash = hash_token(refresh_str)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if not rt:
        return False
    rt.is_revoked = True
    await db.commit()
    return True
