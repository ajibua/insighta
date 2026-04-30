import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from app.core.config import settings

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAIL_URL = "https://api.github.com/user/emails"


def generate_pkce_pair() -> tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge (S256 method).
    verifier: 32 random bytes → base64url → 43 chars (no padding)
    challenge: SHA256(verifier) → base64url → 43 chars
    """
    raw = secrets.token_bytes(32)
    code_verifier = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return code_verifier, code_challenge


def build_github_auth_url(state: str, code_challenge: str, redirect_uri: str) -> str:
    params = urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    return f"{GITHUB_AUTH_URL}?{params}"


async def exchange_code_for_token(code: str, code_verifier: str, redirect_uri: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ValueError(f"GitHub token exchange failed: {data}")
        return token


async def get_github_user(github_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/json"},
        )
        resp.raise_for_status()
        user = resp.json()
        if not user.get("email"):
            email_resp = await client.get(
                GITHUB_EMAIL_URL,
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/json"},
            )
            if email_resp.status_code == 200:
                emails = email_resp.json()
                primary = next((e["email"] for e in emails if e.get("primary")), None)
                user["email"] = primary
        return user
