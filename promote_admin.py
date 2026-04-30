"""Promote a user to admin. Usage: python promote_admin.py <username>"""
import asyncio, ssl, sys, os
from urllib.parse import urlparse
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "ajibua"
    parsed = urlparse(os.getenv("DATABASE_URL", ""))
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(
        host=parsed.hostname, port=parsed.port,
        user=parsed.username, password=parsed.password,
        database=parsed.path.lstrip("/"), ssl=ctx,
    )
    result = await conn.execute("UPDATE users SET role='admin' WHERE username=$1", username)
    print(f"{result} — user '{username}' is now admin")
    await conn.close()

asyncio.run(main())
