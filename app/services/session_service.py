"""Session CRUD operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.callback_idempotency import CallbackIdempotency
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
    # Also clears last_message_id — the step message buttons are wiped
    # by the caller before pausing, so there is no valid message to delete
    # on resume. Clearing here prevents a stale ID from being acted on
    # if the session object is ever reused after this call.
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="paused", last_message_id=None, updated_at=datetime.utcnow())
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
        .values(status="completed", last_message_id=None, updated_at=datetime.utcnow())
    )
    await db.commit()
    # Clean up idempotency keys for this chat — session is over, no more
    # duplicate callbacks can meaningfully arrive for these message IDs.
    await _clear_idempotency_for_chat(db, session.chat_id)


async def abandon_session(db: AsyncSession, session: Session) -> None:
    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="abandoned", last_message_id=None, updated_at=datetime.utcnow())
    )
    await db.commit()
    # Clean up idempotency keys for this chat — session is over.
    await _clear_idempotency_for_chat(db, session.chat_id)


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

async def claim_callback(
    db: AsyncSession, chat_id: str, message_id: int
) -> bool:
    """Attempt to claim exclusive processing rights for a (chat_id, message_id) pair.

    Returns True if this is the FIRST handler to claim it (proceed normally).
    Returns False if another handler already claimed it (duplicate — skip processing).

    Uses a DB-level unique constraint so the race is resolved atomically,
    regardless of how many concurrent coroutines arrive simultaneously.
    """
    try:
        db.add(CallbackIdempotency(chat_id=chat_id, message_id=message_id))
        await db.commit()
        return True
    except IntegrityError:
        # Unique constraint violated — another handler got here first.
        await db.rollback()
        return False


async def _clear_idempotency_for_chat(db: AsyncSession, chat_id: str) -> None:
    """Delete all idempotency rows for a chat_id. Called when session ends."""
    await db.execute(
        delete(CallbackIdempotency).where(CallbackIdempotency.chat_id == chat_id)
    )
    await db.commit()