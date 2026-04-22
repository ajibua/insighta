from sqlalchemy import Column, String, Float, Integer, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String, nullable=False, unique=True, index=True)
    gender = Column(String, nullable=False, index=True)
    gender_probability = Column(Float, nullable=False)
    age = Column(Integer, nullable=False, index=True)
    age_group = Column(String, nullable=False, index=True)
    country_id = Column(String(2), nullable=False, index=True)
    country_name = Column(String, nullable=False)
    country_probability = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
