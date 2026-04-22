from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ProfileOut(BaseModel):
    id: str
    name: str
    gender: str
    gender_probability: float
    age: int
    age_group: str
    country_id: str
    country_name: str
    country_probability: float
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileListResponse(BaseModel):
    status: str = "success"
    page: int
    limit: int
    total: int
    data: List[ProfileOut]


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str


class ProfileFilters(BaseModel):
    gender: Optional[str] = None
    age_group: Optional[str] = None
    country_id: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    min_gender_probability: Optional[float] = None
    min_country_probability: Optional[float] = None
    sort_by: Optional[str] = Field(default=None, pattern="^(age|created_at|gender_probability)$")
    order: Optional[str] = Field(default="asc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)
