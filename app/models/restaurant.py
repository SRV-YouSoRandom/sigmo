"""Restaurant ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    restaurant_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manager_chat_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # Reminder times stored as "HH:MM" in 24h format, e.g. "10:00", "22:00"
    opening_reminder_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    closing_reminder_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    # Minutes after reminder to send a follow-up if checklist hasn't started
    reminder_followup_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.utcnow
    )