"""ChecklistRun ORM model – a completed or abandoned checklist record."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChecklistRun(Base):
    __tablename__ = "checklist_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("staff.chat_id"), nullable=False
    )
    restaurant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("restaurants.restaurant_id"), nullable=False
    )
    checklist_id: Mapped[str] = mapped_column(String(50), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
