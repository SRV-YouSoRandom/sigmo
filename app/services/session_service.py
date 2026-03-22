"""Session CRUD operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


async def get_active_session(db: AsyncSession, chat_id: str) -> Session | None:
    result = await db.execute(
        select(Session).where(Session.chat_id == chat_id, Session.status == "active")
    )
    return result.scalars().first()


async def get_paused_session(db: AsyncSession, chat_id: str) -> Session | None:
    result = await db.execute(
        select(Session).where(Session.chat_id == chat_id, Session.status == "paused")
    )
    return result.scalars().first()


async def get_active_or_paused_session(db: AsyncSession, chat_id: str) -> Session | None:
    result = await db.execute(
        select(Session).where(
            Session.chat_id == chat_id,
            Session.status.in_(["active", "paused"]),
        )
    )
    return result.scalars().first()


async def create_session(
    db: AsyncSession,
    chat_id: str,
    restaurant_id: str,
    checklist_id: str,
) -> Session:
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
    # Always reset last_message_id to None (or the provided value) when
    # advancing a step. This prevents a stale message ID from being used
    # in a future delete attempt if save_last_message_id hasn't been called
    # yet for the new step message.
    vals: dict = {
        "current_step": next_step,
        "updated_at": datetime.utcnow(),
        "last_message_id": last_message_id,  # explicitly None unless caller passes a value
    }
    await db.execute(update(Session).where(Session.id == session.id).values(**vals))
    await db.commit()


async def save_last_message_id(db: AsyncSession, session: Session, message_id: int) -> None:
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(last_message_id=message_id, updated_at=datetime.utcnow())
    )
    await db.commit()


async def pause_session(db: AsyncSession, session: Session) -> None:
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="paused", updated_at=datetime.utcnow())
    )
    await db.commit()


async def resume_session(db: AsyncSession, session: Session) -> None:
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="active", updated_at=datetime.utcnow())
    )
    await db.commit()


async def complete_session(db: AsyncSession, session: Session) -> None:
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="completed", updated_at=datetime.utcnow())
    )
    await db.commit()


async def abandon_session(db: AsyncSession, session: Session) -> None:
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="abandoned", updated_at=datetime.utcnow())
    )
    await db.commit()