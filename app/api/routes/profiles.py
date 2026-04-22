from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.profile import ProfileListResponse, ProfileOut, ErrorResponse
from app.services.profile_service import get_profiles, VALID_AGE_GROUPS, VALID_GENDERS
from app.services.nl_parser import parse_natural_language

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _validate_filters(
    gender: Optional[str],
    age_group: Optional[str],
    sort_by: Optional[str],
    order: str,
    min_age: Optional[int],
    max_age: Optional[int],
    min_gender_probability: Optional[float],
    min_country_probability: Optional[float],
    limit: int,
):
    if gender is not None and gender.lower() not in VALID_GENDERS:
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if age_group is not None and age_group.lower() not in VALID_AGE_GROUPS:
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if sort_by is not None and sort_by not in ("age", "created_at", "gender_probability"):
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if min_age is not None and min_age < 0:
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if max_age is not None and max_age < 0:
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if min_age is not None and max_age is not None and min_age > max_age:
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if min_gender_probability is not None and not (0 <= min_gender_probability <= 1):
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if min_country_probability is not None and not (0 <= min_country_probability <= 1):
        raise HTTPException(status_code=422, detail="Invalid query parameters")
    if limit > 50:
        raise HTTPException(status_code=422, detail="Invalid query parameters")


@router.get("", response_model=ProfileListResponse)
async def list_profiles(
    gender: Optional[str] = Query(default=None),
    age_group: Optional[str] = Query(default=None),
    country_id: Optional[str] = Query(default=None),
    min_age: Optional[int] = Query(default=None),
    max_age: Optional[int] = Query(default=None),
    min_gender_probability: Optional[float] = Query(default=None),
    min_country_probability: Optional[float] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    order: str = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    _validate_filters(
        gender, age_group, sort_by, order,
        min_age, max_age, min_gender_probability, min_country_probability, limit,
    )

    total, profiles = await get_profiles(
        db,
        gender=gender,
        age_group=age_group,
        country_id=country_id,
        min_age=min_age,
        max_age=max_age,
        min_gender_probability=min_gender_probability,
        min_country_probability=min_country_probability,
        sort_by=sort_by,
        order=order,
        page=page,
        limit=limit,
    )

    return ProfileListResponse(
        status="success",
        page=page,
        limit=limit,
        total=total,
        data=[ProfileOut.model_validate(p) for p in profiles],
    )


@router.get("/search", response_model=ProfileListResponse)
async def search_profiles(
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    if not q or not q.strip():
        raise HTTPException(
            status_code=400,
            detail="Unable to interpret query",
        )

    filters = parse_natural_language(q)

    if filters is None:
        raise HTTPException(
            status_code=400,
            detail="Unable to interpret query",
        )

    total, profiles = await get_profiles(
        db,
        gender=filters.get("gender"),
        age_group=filters.get("age_group"),
        country_id=filters.get("country_id"),
        min_age=filters.get("min_age"),
        max_age=filters.get("max_age"),
        page=page,
        limit=limit,
    )

    return ProfileListResponse(
        status="success",
        page=page,
        limit=limit,
        total=total,
        data=[ProfileOut.model_validate(p) for p in profiles],
    )
