from sqlalchemy import Column, String, DateTime, func
from app.db.database import Base


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state = Column(String, primary_key=True)
    code_verifier = Column(String, nullable=False)
    cli_callback = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
