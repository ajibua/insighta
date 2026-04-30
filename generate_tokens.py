"""
Generate test tokens for the grader submission form.
Usage: python generate_tokens.py
"""
import asyncio
import hashlib
import os
import secrets
import ssl
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import asyncpg
from dotenv import load_dotenv
from jose import jwt

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"


def create_access_token(user_id: str, role: str, expire_days: int = 30) -> str:
    """Create a long-lived access token for grader testing."""
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire, "type": "access"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


async def main():
    parsed = urlparse(os.getenv("DATABASE_URL", ""))
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    conn = await asyncpg.connect(
        host=parsed.hostname, port=parsed.port,
        user=parsed.username, password=parsed.password,
        database=parsed.path.lstrip("/"), ssl=ctx,
    )

    # Get or create admin user
    admin = await conn.fetchrow("SELECT id, username, role FROM users WHERE role='admin' LIMIT 1")
    if not admin:
        print("ERROR: No admin user found. Run: python promote_admin.py ajibua")
        await conn.close()
        return

    # Get or create analyst user — use admin as analyst too if no separate analyst exists
    analyst = await conn.fetchrow("SELECT id, username, role FROM users WHERE role='analyst' LIMIT 1")
    if not analyst:
        # Create the analyst token using the admin user but with analyst role
        analyst = admin
        analyst_role = "analyst"
    else:
        analyst_role = "analyst"

    # Generate tokens (30-day expiry for grading)
    admin_token = create_access_token(admin["id"], "admin", expire_days=30)
    analyst_token = create_access_token(analyst["id"] if analyst != admin else admin["id"], analyst_role, expire_days=30)

    # Generate refresh token and store it
    refresh_raw = secrets.token_urlsafe(48)
    refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    await conn.execute(
        """INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
           VALUES (gen_random_uuid()::text, $1, $2, $3)
           ON CONFLICT DO NOTHING""",
        admin["id"], refresh_hash, expires_at,
    )

    await conn.close()

    print("=" * 60)
    print("SUBMISSION TOKENS (valid for 30 days)")
    print("=" * 60)
    print()
    print(f"Admin user:    {admin['username']} (role: admin)")
    print(f"Analyst user:  {analyst['username'] if analyst != admin else admin['username']} (role: analyst)")
    print()
    print("--- Admin Test Token ---")
    print(admin_token)
    print()
    print("--- Analyst Test Token ---")
    print(analyst_token)
    print()
    print("--- Refresh Test Token (paired with admin) ---")
    print(refresh_raw)
    print()
    print("=" * 60)


asyncio.run(main())
