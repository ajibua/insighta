import asyncio
import csv
import io
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
import uuid_utils as uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_admin, require_analyst
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.models.profile import Profile
from app.models.user import User
from app.schemas.profile import ProfileListResponse, ProfileOut
from app.services.nl_parser import parse_natural_language
from app.services.profile_service import (
    VALID_AGE_GROUPS,
    VALID_GENDERS,
    get_profiles,
)

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

AGIFY_URL = "https://api.agify.io"
GENDERIZE_URL = "https://api.genderize.io"
NATIONALIZE_URL = "https://api.nationalize.io"


def _check_api_version(x_api_version: Optional[str] = Header(default=None)):
    if x_api_version != "1":
        raise HTTPException(
            status_code=400,
            detail="API version header required",
        )


def _validate_filters(gender, age_group, sort_by, order, min_age, max_age,
                      min_gender_probability, min_country_probability, limit):
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


def _build_pagination_links(base: str, page: int, limit: int, total: int,
                            extra_params: dict | None = None) -> dict:
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    def _url(p: int) -> str:
        params = {"page": p, "limit": limit}
        if extra_params:
            params.update(extra_params)
        return f"{base}?{urlencode(params)}"

    return {
        "self": _url(page),
        "next": _url(page + 1) if page < total_pages else None,
        "prev": _url(page - 1) if page > 1 else None,
    }


# ── GET /api/profiles ─────────────────────────────────────────────────────────
@router.get("", response_model=ProfileListResponse)
@limiter.limit("60/minute")
async def list_profiles(
    request: Request,
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
    x_api_version: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_analyst),
):
    _check_api_version(x_api_version)
    _validate_filters(gender, age_group, sort_by, order, min_age, max_age,
                      min_gender_probability, min_country_probability, limit)

    total, profiles = await get_profiles(
        db, gender=gender, age_group=age_group, country_id=country_id,
        min_age=min_age, max_age=max_age,
        min_gender_probability=min_gender_probability,
        min_country_probability=min_country_probability,
        sort_by=sort_by, order=order, page=page, limit=limit,
    )
    total_pages = (total + limit - 1) // limit if total > 0 else 1
    extra = {}
    if gender: extra["gender"] = gender
    if age_group: extra["age_group"] = age_group
    if country_id: extra["country_id"] = country_id
    if min_age is not None: extra["min_age"] = min_age
    if max_age is not None: extra["max_age"] = max_age
    if min_gender_probability is not None: extra["min_gender_probability"] = min_gender_probability
    if min_country_probability is not None: extra["min_country_probability"] = min_country_probability
    if sort_by: extra["sort_by"] = sort_by
    if order != "asc": extra["order"] = order
    links = _build_pagination_links("/api/profiles", page, limit, total, extra)

    return ProfileListResponse(
        status="success", page=page, limit=limit, total=total,
        total_pages=total_pages, links=links,
        data=[ProfileOut.model_validate(p) for p in profiles],
    )


# ── GET /api/profiles/search ──────────────────────────────────────────────────
@router.get("/search")
@limiter.limit("60/minute")
async def search_profiles(
    request: Request,
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    x_api_version: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_analyst),
):
    _check_api_version(x_api_version)
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Unable to interpret query")

    filters = parse_natural_language(q)
    if filters is None:
        raise HTTPException(status_code=400, detail="Unable to interpret query")

    total, profiles = await get_profiles(
        db, gender=filters.get("gender"), age_group=filters.get("age_group"),
        country_id=filters.get("country_id"), min_age=filters.get("min_age"),
        max_age=filters.get("max_age"), page=page, limit=limit,
    )
    total_pages = (total + limit - 1) // limit if total > 0 else 1
    links = _build_pagination_links("/api/profiles/search", page, limit, total, {"q": q})

    return {
        "status": "success", "page": page, "limit": limit,
        "total": total, "total_pages": total_pages, "links": links,
        "data": [ProfileOut.model_validate(p) for p in profiles],
    }


# ── GET /api/profiles/export ──────────────────────────────────────────────────
@router.get("/export")
@limiter.limit("10/minute")
async def export_profiles(
    request: Request,
    format: str = Query(default="csv"),
    gender: Optional[str] = Query(default=None),
    age_group: Optional[str] = Query(default=None),
    country_id: Optional[str] = Query(default=None),
    min_age: Optional[int] = Query(default=None),
    max_age: Optional[int] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    order: str = Query(default="asc"),
    x_api_version: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_analyst),
):
    _check_api_version(x_api_version)
    if format != "csv":
        raise HTTPException(status_code=422, detail="Only format=csv is supported")

    # Fetch all matching profiles (no pagination for export)
    total, profiles = await get_profiles(
        db, gender=gender, age_group=age_group, country_id=country_id,
        min_age=min_age, max_age=max_age, sort_by=sort_by, order=order,
        page=1, limit=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "name", "gender", "gender_probability", "age", "age_group",
        "country_id", "country_name", "country_probability", "created_at",
    ])
    for p in profiles:
        writer.writerow([
            p.id, p.name, p.gender, p.gender_probability, p.age, p.age_group,
            p.country_id, p.country_name, p.country_probability,
            p.created_at.isoformat() if p.created_at else "",
        ])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"profiles_{timestamp}.csv"
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── POST /api/profiles ────────────────────────────────────────────────────────
@router.post("")
@limiter.limit("20/minute")
async def create_profile(
    request: Request,
    payload: dict,
    x_api_version: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    _check_api_version(x_api_version)
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    # Defaults in case external APIs fail
    gender = "unknown"
    gender_prob = 0.0
    age = 0
    country_id = "XX"
    country_prob = 0.0

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            g_resp, a_resp, n_resp = await asyncio.gather(
                client.get(GENDERIZE_URL, params={"name": name}),
                client.get(AGIFY_URL, params={"name": name}),
                client.get(NATIONALIZE_URL, params={"name": name}),
            )
            gender_data = g_resp.json()
            age_data = a_resp.json()
            nation_data = n_resp.json()

            gender = gender_data.get("gender") or "unknown"
            gender_prob = gender_data.get("probability") or 0.0
            age = age_data.get("age") or 0
            countries = nation_data.get("country", [])
            top_country = countries[0] if countries else {}
            country_id = top_country.get("country_id", "XX")
            country_prob = top_country.get("probability", 0.0)
    except Exception:
        pass  # Use defaults

    from app.services.profile_service import classify_age_group
    from app.services.profile_service import COUNTRY_NAMES
    country_name = COUNTRY_NAMES.get(country_id, country_id)

    profile = Profile(
        id=str(uuid.uuid7()),
        name=name.lower(),
        gender=gender.lower(),
        gender_probability=gender_prob,
        age=age,
        age_group=classify_age_group(age),
        country_id=country_id,
        country_name=country_name,
        country_probability=country_prob,
    )
    db.add(profile)
    try:
        await db.commit()
        await db.refresh(profile)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Profile with this name already exists")

    return {"status": "success", "data": ProfileOut.model_validate(profile)}


# ── DELETE /api/profiles/{profile_id} ─────────────────────────────────────────
@router.delete("/{profile_id}")
@limiter.limit("20/minute")
async def delete_profile(
    request: Request,
    profile_id: str,
    x_api_version: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    _check_api_version(x_api_version)

    from sqlalchemy import delete as sql_delete
    result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.execute(sql_delete(Profile).where(Profile.id == profile_id))
    await db.commit()

    return {"status": "success", "message": "Profile deleted"}

