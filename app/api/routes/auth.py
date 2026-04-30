import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.models.oauth_state import OAuthState
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.services.auth_service import (
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
    upsert_user,
)
from app.services.github_oauth import (
    build_github_auth_url,
    exchange_code_for_token,
    generate_pkce_pair,
    get_github_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


# ── GET /auth/github — Unified flow ──────────────────────────────────────────
@router.get("/github")
@limiter.limit("10 per 15 second")
async def github_login(
    request: Request,
    code_challenge: str = Query(default=None),
    state: str = Query(default=None),
    code_verifier: str = Query(default=None),
    cli_callback: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """OAuth login — works with or without PKCE params."""
    if not state:
        state = secrets.token_urlsafe(16)
    if not code_challenge:
        code_verifier, code_challenge = generate_pkce_pair()

    oauth_state = OAuthState(
        state=state,
        code_verifier=code_verifier or "",
        cli_callback=cli_callback,
    )
    db.add(oauth_state)
    await db.commit()

    url = build_github_auth_url(state, code_challenge, settings.GITHUB_REDIRECT_URI)
    return RedirectResponse(url, status_code=307)


# ── GET /auth/github/web — Alias for web portal ──────────────────────────────
@router.get("/github/web")
@limiter.limit("10 per 15 second")
async def github_login_web(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = generate_pkce_pair()

    oauth_state = OAuthState(
        state=state,
        code_verifier=code_verifier,
        cli_callback=None,
    )
    db.add(oauth_state)
    await db.commit()

    url = build_github_auth_url(state, code_challenge, settings.GITHUB_REDIRECT_URI)
    return RedirectResponse(url, status_code=307)


# ── GET /auth/github/callback ─────────────────────────────────────────────────
@router.get("/github/callback")
@limiter.limit("30 per 1 minute")
async def github_callback(
    request: Request,
    code: str = Query(default=None),
    state: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not code:
        raise HTTPException(status_code=400, detail="Missing code parameter")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    result = await db.execute(select(OAuthState).where(OAuthState.state == state))
    pending = result.scalar_one_or_none()

    if not pending:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    verifier = pending.code_verifier
    cli_callback = pending.cli_callback

    await db.execute(delete(OAuthState).where(OAuthState.state == state))
    await db.commit()

    if not verifier:
        raise HTTPException(status_code=400, detail="Missing code_verifier")

    try:
        github_token = await exchange_code_for_token(
            code, verifier, settings.GITHUB_REDIRECT_URI
        )
        github_user = await get_github_user(github_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub OAuth failed: {e}")

    user = await upsert_user(db, github_user)
    access_token, refresh_str = await issue_token_pair(db, user)

    if cli_callback:
        params = urlencode({
            "access_token": access_token,
            "refresh_token": refresh_str,
            "username": user.username,
        })
        return RedirectResponse(f"{cli_callback}?{params}")

    oauth_token = OAuthToken(
        state=state,
        access_token=access_token,
        refresh_token=refresh_str,
        username=user.username,
    )
    db.add(oauth_token)
    await db.commit()

    response = HTMLResponse(content=_success_page(user.username))
    _set_auth_cookies(response, access_token, refresh_str)
    return response


# ── GET /auth/cli/token ───────────────────────────────────────────────────────
@router.get("/cli/token")
@limiter.limit("30 per 1 minute")
async def cli_token(
    request: Request,
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OAuthToken).where(OAuthToken.state == state))
    token_row = result.scalar_one_or_none()

    if not token_row:
        return JSONResponse({"status": "pending"}, status_code=202)

    data = {
        "status": "success",
        "access_token": token_row.access_token,
        "refresh_token": token_row.refresh_token,
        "username": token_row.username,
    }

    await db.execute(delete(OAuthToken).where(OAuthToken.state == state))
    await db.commit()

    return JSONResponse(data)


# ── POST /auth/refresh ────────────────────────────────────────────────────────
@router.post("/refresh")
@limiter.limit("30 per 1 minute")
async def refresh_tokens(
    request: Request,
    body: RefreshRequest | None = None,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    token_str = (body.refresh_token if body else None) or refresh_token
    if not token_str:
        raise HTTPException(status_code=400, detail="Refresh token required")

    result = await rotate_refresh_token(db, token_str)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    access_token, new_refresh = result
    response = JSONResponse({
        "status": "success",
        "access_token": access_token,
        "refresh_token": new_refresh,
    })
    if refresh_token:
        _set_auth_cookies(response, access_token, new_refresh)
    return response


# ── POST /auth/logout ─────────────────────────────────────────────────────────
@router.post("/logout")
@limiter.limit("30 per 1 minute")
async def logout(
    request: Request,
    body: LogoutRequest | None = None,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    token_str = (body.refresh_token if body else None) or refresh_token
    if token_str:
        await revoke_refresh_token(db, token_str)
    response = JSONResponse({"status": "success", "message": "Logged out"})
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("csrf_token")
    return response


# ── GET /auth/logout — Method not allowed ─────────────────────────────────────
@router.get("/logout")
async def logout_get(request: Request):
    return JSONResponse(
        status_code=405,
        content={"status": "error", "message": "Method not allowed. Use POST to logout."},
    )


# ── GET /auth/me ──────────────────────────────────────────────────────────────
@router.get("/me")
@limiter.limit("30 per 1 minute")
async def me(request: Request, user: User = Depends(get_current_user)):
    return {
        "status": "success",
        "data": {
            "id": user.id,
            "github_id": user.github_id,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "is_active": user.is_active,
            "last_login_at": str(user.last_login_at) if user.last_login_at else None,
            "created_at": str(user.created_at) if user.created_at else None,
        },
    }


# ── helpers ───────────────────────────────────────────────────────────────────
def _set_auth_cookies(response, access_token: str, refresh_token: str):
    csrf_token = secrets.token_urlsafe(32)

    response.set_cookie(
        "access_token", access_token,
        httponly=True, samesite=settings.COOKIE_SAMESITE, secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        httponly=True, samesite=settings.COOKIE_SAMESITE, secure=settings.COOKIE_SECURE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        "csrf_token", csrf_token,
        httponly=False, samesite=settings.COOKIE_SAMESITE, secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )


def _success_page(username: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>Logged in — Insighta Labs+</title>
<style>
  body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e2e4f0;
       display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
  .box{{text-align:center;padding:40px}}
  h2{{color:#4ecdc4;margin-bottom:12px}}
  p{{color:#8b8fa8;font-size:14px}}
</style></head>
<body><div class="box">
  <h2>✓ Logged in as @{username}</h2>
  <p>Redirecting you back…</p>
</div>
<script>
  setTimeout(() => window.location.href = '{settings.FRONTEND_URL}', 1500);
</script>
</body></html>"""
