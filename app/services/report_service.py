"""Daily summary report builder."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checklist_run import ChecklistRun
from app.models.staff import Staff
from app.services.checklist_engine import CHECKLIST_LABELS


async def get_runs_for_yesterday(
    db: AsyncSession, restaurant_id: str
) -> list[dict]:
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
        staff_result = await db.execute(select(Staff).where(Staff.chat_id == run.chat_id))
        staff = staff_result.scalars().first()
        enriched.append({
            "checklist_id": run.checklist_id,
            "staff_name": staff.name if staff else "Unknown",
            "start_time": run.start_time,
            "end_time": run.end_time,
        })
    return enriched


def build_summary_message(
    runs: list[dict],
    date_str: Optional[str] = None,
    restaurant=None,
) -> str:
    if date_str is None:
        yesterday = datetime.utcnow() - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    # Build header with branch if available
    location = ""
    if restaurant:
        location = restaurant.name
        if restaurant.branch:
            location += f" – {restaurant.branch}"
        location = f" | {location}"

    lines = [f"📋 <b>Sigmo Daily Report{location}</b>\n{date_str}\n"]

    if not runs:
        lines.append("No completed checklists yesterday.")
        return "\n".join(lines).strip()

    for run in runs:
        label = CHECKLIST_LABELS.get(run["checklist_id"], run["checklist_id"])
        start = run["start_time"].strftime("%I:%M %p") if run["start_time"] else "N/A"
        end = run["end_time"].strftime("%I:%M %p") if run["end_time"] else "N/A"
        lines.append(f"✅ <b>{label}</b>")
        lines.append(f"   {run['staff_name']}  {start} → {end}")
        lines.append("")

    return "\n".join(lines).strip()