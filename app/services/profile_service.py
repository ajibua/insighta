from typing import Optional, Tuple, List
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile


VALID_SORT_COLUMNS = {
    "age": Profile.age,
    "created_at": Profile.created_at,
    "gender_probability": Profile.gender_probability,
}

VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}
VALID_GENDERS = {"male", "female"}


def _build_filters(
    stmt,
    gender: Optional[str],
    age_group: Optional[str],
    country_id: Optional[str],
    min_age: Optional[int],
    max_age: Optional[int],
    min_gender_probability: Optional[float],
    min_country_probability: Optional[float],
):
    if gender is not None:
        stmt = stmt.where(Profile.gender == gender.lower())
    if age_group is not None:
        stmt = stmt.where(Profile.age_group == age_group.lower())
    if country_id is not None:
        stmt = stmt.where(Profile.country_id == country_id.upper())
    if min_age is not None:
        stmt = stmt.where(Profile.age >= min_age)
    if max_age is not None:
        stmt = stmt.where(Profile.age <= max_age)
    if min_gender_probability is not None:
        stmt = stmt.where(Profile.gender_probability >= min_gender_probability)
    if min_country_probability is not None:
        stmt = stmt.where(Profile.country_probability >= min_country_probability)
    return stmt


async def get_profiles(
    db: AsyncSession,
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    country_id: Optional[str] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    min_gender_probability: Optional[float] = None,
    min_country_probability: Optional[float] = None,
    sort_by: Optional[str] = None,
    order: str = "asc",
    page: int = 1,
    limit: int = 10,
) -> Tuple[int, List[Profile]]:
    # Count query
    count_stmt = select(func.count()).select_from(Profile)
    count_stmt = _build_filters(
        count_stmt, gender, age_group, country_id,
        min_age, max_age, min_gender_probability, min_country_probability,
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Data query
    data_stmt = select(Profile)
    data_stmt = _build_filters(
        data_stmt, gender, age_group, country_id,
        min_age, max_age, min_gender_probability, min_country_probability,
    )

    if sort_by and sort_by in VALID_SORT_COLUMNS:
        col = VALID_SORT_COLUMNS[sort_by]
        data_stmt = data_stmt.order_by(col.desc() if order == "desc" else col.asc())
    else:
        data_stmt = data_stmt.order_by(Profile.created_at.asc())

    offset = (page - 1) * limit
    data_stmt = data_stmt.offset(offset).limit(limit)

    result = await db.execute(data_stmt)
    profiles = result.scalars().all()

    return total, list(profiles)
