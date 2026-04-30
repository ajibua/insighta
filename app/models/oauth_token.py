from sqlalchemy import Column, String, DateTime, func
from app.db.database import Base


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    state = Column(String, primary_key=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    username = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
