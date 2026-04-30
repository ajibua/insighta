from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.models.user import User

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
@limiter.limit("30/minute")
async def get_me(request: Request, user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return {
        "status": "success",
        "data": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "is_active": user.is_active,
            "last_login_at": str(user.last_login_at) if user.last_login_at else None,
            "created_at": str(user.created_at) if user.created_at else None,
        },
    }
