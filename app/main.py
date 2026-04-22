from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.profiles import router as profiles_router

app = FastAPI(title="Insighta Labs API", version="1.0.0")

# CORS — required for grading script
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


app.include_router(profiles_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
