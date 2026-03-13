"""Manager-facing service – staff status, issue reports, and resume checklist."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checklist_run import ChecklistRun
from app.models.issue_report import IssueReport
from app.models.manager import Manager
from app.models.session import Session
from app.models.staff import Staff
from app.services.checklist_engine import CHECKLIST_LABELS


async def get_manager_by_chat_id(db: AsyncSession, chat_id: str) -> Manager | None:
    result = await db.execute(select(Manager).where(Manager.chat_id == chat_id))
    return result.scalars().first()


async def get_today_staff_status(db: AsyncSession, restaurant_id: str) -> str:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    runs_result = await db.execute(
        select(ChecklistRun)
        .where(
            ChecklistRun.restaurant_id == restaurant_id,
            ChecklistRun.end_time >= today_start,
        )
        .order_by(ChecklistRun.start_time)
    )
    runs = runs_result.scalars().all()

    # Active sessions
    active_result = await db.execute(
        select(Session).where(
            Session.restaurant_id == restaurant_id,
            Session.status == "active",
        )
    )
    active_sessions = active_result.scalars().all()

    # Paused sessions
    paused_result = await db.execute(
        select(Session).where(
            Session.restaurant_id == restaurant_id,
            Session.status == "paused",
        )
    )
    paused_sessions = paused_result.scalars().all()

    lines = [f"👥 <b>Staff Status – {datetime.utcnow().strftime('%b %d, %Y')}</b>\n"]

    if paused_sessions:
        lines.append("🔴 <b>Paused (Critical Issue)</b>")
        for s in paused_sessions:
            staff_res = await db.execute(select(Staff).where(Staff.chat_id == s.chat_id))
            staff = staff_res.scalars().first()
            label = CHECKLIST_LABELS.get(s.checklist_id, s.checklist_id)
            name = staff.name if staff else s.chat_id
            lines.append(f"  • {name} – {label} (step {s.current_step}) ⚠️ awaiting resolution")
        lines.append("")

    if active_sessions:
        lines.append("🟢 <b>Currently Active</b>")
        for s in active_sessions:
            staff_res = await db.execute(select(Staff).where(Staff.chat_id == s.chat_id))
            staff = staff_res.scalars().first()
            label = CHECKLIST_LABELS.get(s.checklist_id, s.checklist_id)
            elapsed = int((datetime.utcnow() - s.started_at).total_seconds() // 60)
            name = staff.name if staff else s.chat_id
            lines.append(f"  • {name} – {label} (step {s.current_step}, {elapsed}m elapsed)")
        lines.append("")

    if runs:
        lines.append("✅ <b>Completed Today</b>")
        for r in runs:
            staff_res = await db.execute(select(Staff).where(Staff.chat_id == r.chat_id))
            staff = staff_res.scalars().first()
            label = CHECKLIST_LABELS.get(r.checklist_id, r.checklist_id)
            start = r.start_time.strftime("%I:%M %p") if r.start_time else "?"
            end = r.end_time.strftime("%I:%M %p") if r.end_time else "?"
            icon = "✅" if r.status == "completed" else "❌"
            name = staff.name if staff else r.chat_id
            lines.append(f"  {icon} {name} – {label}")
            lines.append(f"      {start} → {end}")
    elif not active_sessions and not paused_sessions:
        lines.append("No activity today yet.")

    return "\n".join(lines)


async def get_open_issues(db: AsyncSession, restaurant_id: str) -> list[IssueReport]:
    result = await db.execute(
        select(IssueReport)
        .where(
            IssueReport.restaurant_id == restaurant_id,
            IssueReport.resolved == False,  # noqa: E712
        )
        .order_by(IssueReport.reported_at.desc())
    )
    return result.scalars().all()


async def build_issues_messages(
    db: AsyncSession, issues: list[IssueReport]
) -> list[dict]:
    msgs = []
    for issue in issues:
        staff_res = await db.execute(select(Staff).where(Staff.chat_id == issue.chat_id))
        staff = staff_res.scalars().first()
        label = CHECKLIST_LABELS.get(issue.checklist_id, issue.checklist_id)
        name = staff.name if staff else issue.chat_id
        reported = issue.reported_at.strftime("%b %d %I:%M %p")
        type_icon = "🔴" if issue.issue_type == "critical" else "🟡"
        type_label = "Critical" if issue.issue_type == "critical" else "Operational"

        text = (
            f"{type_icon} <b>Issue #{issue.id} – {type_label}</b>\n"
            f"Staff: {name}\n"
            f"Checklist: {label} – Step {issue.step_number}\n"
            f"Reported: {reported}\n\n"
            f"📝 {issue.description}"
        )

        # Critical issues get a Resume button in addition to Resolve
        if issue.issue_type == "critical":
            inline_keyboard = [
                [
                    {"text": "✅ Mark Resolved & Resume Staff", "callback_data": f"resolve_resume:{issue.id}:{issue.chat_id}"},
                ]
            ]
        else:
            inline_keyboard = [
                [{"text": "✅ Mark Resolved", "callback_data": f"resolve_issue:{issue.id}"}]
            ]

        msgs.append({"text": text, "reply_markup": {"inline_keyboard": inline_keyboard}})
    return msgs


async def resolve_issue(
    db: AsyncSession, issue_id: int, manager_chat_id: str
) -> IssueReport | None:
    result = await db.execute(select(IssueReport).where(IssueReport.id == issue_id))
    issue = result.scalars().first()
    if issue is None:
        return None
    issue.resolved = True
    issue.resolved_at = datetime.utcnow()
    issue.resolved_by_chat_id = manager_chat_id
    await db.commit()
    await db.refresh(issue)
    return issue