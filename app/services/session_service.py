"""Session CRUD operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


async def get_active_session(db: AsyncSession, chat_id: str) -> Session | None:
    """Return the active session for a given chat_id, or None."""
    result = await db.execute(
        select(Session).where(Session.chat_id == chat_id, Session.status == "active")
    )
    return result.scalars().first()


async def create_session(
    db: AsyncSession,
    chat_id: str,
    restaurant_id: str,
    checklist_id: str,
) -> Session:
    """Create and return a new active session."""
    session = Session(
        chat_id=chat_id,
        restaurant_id=restaurant_id,
        checklist_id=checklist_id,
        current_step=1,
        status="active",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def update_session_step(
    db: AsyncSession,
    session: Session,
    next_step: int,
    last_message_id: Optional[int] = None,
) -> None:
    """Advance the session to the next step, optionally storing the new message_id."""
    vals: dict = {"current_step": next_step, "updated_at": datetime.utcnow()}
    if last_message_id is not None:
        vals["last_message_id"] = last_message_id
    await db.execute(update(Session).where(Session.id == session.id).values(**vals))
    await db.commit()


async def save_last_message_id(
    db: AsyncSession, session: Session, message_id: int
) -> None:
    """Persist the last bot message_id for this session (used for deletion)."""
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(last_message_id=message_id, updated_at=datetime.utcnow())
    )
    await db.commit()


async def complete_session(db: AsyncSession, session: Session) -> None:
    """Mark a session as completed."""
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="completed", updated_at=datetime.utcnow())
    )
    await db.commit()


async def abandon_session(db: AsyncSession, session: Session) -> None:
    """Mark a session as abandoned."""
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="abandoned", updated_at=datetime.utcnow())
    )
    await db.commit()