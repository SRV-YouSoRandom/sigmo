"""Session ORM model – tracks an in-progress checklist run."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("staff.chat_id"), nullable=False
    )
    restaurant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("restaurants.restaurant_id"), nullable=False
    )
    checklist_id: Mapped[str] = mapped_column(String(50), nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.utcnow, onupdate=datetime.utcnow
    )