"""Shared test fixtures."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.checklist_run import ChecklistRun  # noqa: F401
from app.models.checklist_step import ChecklistStep
from app.models.issue_report import IssueReport  # noqa: F401
from app.models.manager import Manager
from app.models.restaurant import Restaurant
from app.models.session import Session  # noqa: F401
from app.models.staff import Staff
from app.models.step_photo import StepPhoto  # noqa: F401

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def seeded_db(db: AsyncSession):
    """DB with restaurant (with branch + reminders), staff, manager, and checklist steps."""
    restaurant = Restaurant(
        restaurant_id="R001",
        name="Test Restaurant",
        branch="Makati",
        manager_chat_id="999",
        opening_reminder_time="10:00",
        closing_reminder_time="22:00",
        reminder_followup_minutes=20,
    )
    db.add(restaurant)

    staff = Staff(chat_id="123456", name="John", restaurant_id="R001")
    db.add(staff)

    manager = Manager(chat_id="999", name="Manager Bob", restaurant_id="R001")
    db.add(manager)

    steps = [
        ChecklistStep(
            restaurant_id="R001",
            checklist_id="KITCHEN_OPEN",
            step_number=1,
            instruction="Turn on lights",
            requires_photo=False,
        ),
        ChecklistStep(
            restaurant_id="R001",
            checklist_id="KITCHEN_OPEN",
            step_number=2,
            instruction="Clean prep table",
            requires_photo=True,
        ),
        ChecklistStep(
            restaurant_id="R001",
            checklist_id="KITCHEN_OPEN",
            step_number=3,
            instruction="Turn on oven",
            requires_photo=False,
        ),
    ]
    db.add_all(steps)
    await db.commit()
    yield db