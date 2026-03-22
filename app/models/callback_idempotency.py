"""CallbackIdempotency ORM model.

Prevents duplicate processing of Telegram callback queries (e.g. ✅ Done)
when a staff member taps a button multiple times while offline and all taps
arrive simultaneously when connectivity is restored.

Each row records that a specific (chat_id, message_id) callback has already
been processed. Rows are cleaned up when the associated session ends
(completed or abandoned), keeping the table tiny.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CallbackIdempotency(Base):
    __tablename__ = "callback_idempotency"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # The Telegram message_id of the step message the button was attached to.
    # This is unique per step — once processed, duplicates are rejected.
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="uq_callback_chat_message"),
    )