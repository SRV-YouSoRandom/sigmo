"""ChecklistStep ORM model."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChecklistStep(Base):
    __tablename__ = "checklist_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    restaurant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("restaurants.restaurant_id"), nullable=False
    )
    checklist_id: Mapped[str] = mapped_column(String(50), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("restaurant_id", "checklist_id", "step_number"),
    )
