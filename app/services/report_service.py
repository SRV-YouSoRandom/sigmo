"""Daily summary report builder."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checklist_run import ChecklistRun
from app.models.staff import Staff
from app.services.checklist_engine import CHECKLIST_LABELS


async def get_runs_for_yesterday(
    db: AsyncSession, restaurant_id: str
) -> list[dict]:
    """Fetch all completed checklist runs from yesterday for a restaurant."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    result = await db.execute(
        select(ChecklistRun)
        .where(
            ChecklistRun.restaurant_id == restaurant_id,
            ChecklistRun.status == "completed",
            ChecklistRun.end_time >= yesterday,
            ChecklistRun.end_time < today,
        )
        .order_by(ChecklistRun.start_time)
    )
    runs = result.scalars().all()

    enriched: list[dict] = []
    for run in runs:
        staff_result = await db.execute(
            select(Staff).where(Staff.chat_id == run.chat_id)
        )
        staff = staff_result.scalars().first()
        enriched.append(
            {
                "checklist_id": run.checklist_id,
                "staff_name": staff.name if staff else "Unknown",
                "start_time": run.start_time,
                "end_time": run.end_time,
            }
        )
    return enriched


def build_summary_message(runs: list[dict], date_str: str | None = None) -> str:
    """Build a formatted daily summary string."""
    if date_str is None:
        yesterday = datetime.utcnow() - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    lines = [f"📋 Sigmo Daily Report – {date_str}\n"]

    for run in runs:
        label = CHECKLIST_LABELS.get(run["checklist_id"], run["checklist_id"])
        start = run["start_time"].strftime("%I:%M %p") if run["start_time"] else "N/A"
        end = run["end_time"].strftime("%I:%M %p") if run["end_time"] else "N/A"
        lines.append(label)
        lines.append(f"Completed by: {run['staff_name']}")
        lines.append(f"Start: {start} | Finish: {end}")
        lines.append("")

    return "\n".join(lines).strip()
