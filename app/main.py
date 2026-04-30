from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes.profiles import router as profiles_router
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.middleware.logging import RequestLoggingMiddleware

app = FastAPI(title="Insighta Labs+ API", version="2.0.0")

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware order: last added = outermost (runs first)
# 1. Logging (innermost)
app.add_middleware(RequestLoggingMiddleware)

# 2. CORS (outermost — must intercept OPTIONS preflight first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "https://insightalabs-web-api.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    """
    CSRF double-submit cookie protection for web portal.
    Only enforced when the request uses cookie-based auth (no Bearer header).
    Skips safe methods (GET, HEAD, OPTIONS) and auth routes.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)

    # Skip CSRF for requests with Bearer auth (CLI flow)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return await call_next(request)

    # Skip CSRF for auth endpoints (login/callback flows)
    if request.url.path.startswith("/auth/"):
        return await call_next(request)

    # Enforce CSRF only when cookie-based auth is present
    if request.cookies.get("access_token"):
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": "CSRF token missing or invalid"},
            )

    return await call_next(request)


# Validation error → 422 with standard error shape
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Invalid query parameters"},
    )


# HTTP errors (400/404/etc.) -> standard error shape
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = str(exc.detail) if exc.detail else "Internal server error"
    if exc.status_code == 404 and message == "Not Found":
        message = "Profile not found"
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": message},
    )


# Generic 500
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"},
    )


app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(users_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
