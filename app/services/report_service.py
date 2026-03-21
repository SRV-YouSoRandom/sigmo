"""Daily summary report builder."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import to_pht, pht_today_start_utc
from app.models.checklist_run import ChecklistRun
from app.models.issue_report import IssueReport
from app.models.staff import Staff
from app.services.checklist_engine import CHECKLIST_LABELS

# All checklist IDs the system knows about — used to detect missed checklists
ALL_CHECKLIST_IDS = {"KITCHEN_OPEN", "KITCHEN_CLOSE", "DINING_OPEN", "DINING_CLOSE"}


def _pht_day_window() -> tuple[datetime, datetime]:
    """Return the UTC start and end of yesterday in PHT (UTC+8).

    PHT midnight = 16:00 UTC the previous calendar day.
    So "yesterday PHT" runs from 16:00 UTC two days ago to 16:00 UTC yesterday.

    Previously the window was midnight-to-midnight UTC (= 08:00-08:00 PHT),
    which silently missed late-night closing runs before 08:00 PHT.
    """
    today_pht_start_utc = pht_today_start_utc()
    yesterday_pht_start_utc = today_pht_start_utc - timedelta(days=1)
    return yesterday_pht_start_utc, today_pht_start_utc


async def get_runs_for_yesterday(db: AsyncSession, restaurant_id: str) -> list[dict]:
    """Return all completed and abandoned runs for yesterday (PHT-aligned window)."""
    window_start, window_end = _pht_day_window()

    result = await db.execute(
        select(ChecklistRun)
        .where(
            ChecklistRun.restaurant_id == restaurant_id,
            ChecklistRun.status.in_(["completed", "abandoned"]),
            ChecklistRun.end_time >= window_start,
            ChecklistRun.end_time < window_end,
        )
        .order_by(ChecklistRun.start_time)
    )
    runs = result.scalars().all()

    enriched: list[dict] = []
    for run in runs:
        staff_result = await db.execute(select(Staff).where(Staff.chat_id == run.chat_id))
        staff = staff_result.scalars().first()
        duration_seconds = (
            (run.end_time - run.start_time).total_seconds()
            if run.start_time and run.end_time
            else None
        )
        enriched.append({
            "checklist_id": run.checklist_id,
            "staff_name": staff.name if staff else "Unknown",
            "start_time": run.start_time,
            "end_time": run.end_time,
            "status": run.status,
            "photo_count": run.photo_count,
            "duration_seconds": duration_seconds,
        })
    return enriched


async def get_issues_for_yesterday(db: AsyncSession, restaurant_id: str) -> list[dict]:
    """Return all issues reported yesterday (PHT-aligned window)."""
    window_start, window_end = _pht_day_window()

    result = await db.execute(
        select(IssueReport)
        .where(
            IssueReport.restaurant_id == restaurant_id,
            IssueReport.reported_at >= window_start,
            IssueReport.reported_at < window_end,
        )
        .order_by(IssueReport.reported_at)
    )
    issues = result.scalars().all()

    enriched: list[dict] = []
    for issue in issues:
        staff_result = await db.execute(select(Staff).where(Staff.chat_id == issue.chat_id))
        staff = staff_result.scalars().first()
        enriched.append({
            "issue_type": issue.issue_type,
            "staff_name": staff.name if staff else "Unknown",
            "checklist_id": issue.checklist_id,
            "step_number": issue.step_number,
            "description": issue.description,
            "resolved": issue.resolved,
            "reported_at": issue.reported_at,
        })
    return enriched


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins == 0:
        return f"{secs}s"
    return f"{mins}m {secs}s"


def build_summary_message(
    runs: list[dict],
    issues: Optional[list[dict]] = None,
    date_str: Optional[str] = None,
    restaurant=None,
) -> str:
    if date_str is None:
        yesterday_pht = to_pht(datetime.utcnow() - timedelta(days=1))
        date_str = yesterday_pht.strftime("%b %d, %Y")  # e.g. "Jan 01, 2026"

    issues = issues or []

    completed  = [r for r in runs if r["status"] == "completed"]
    abandoned  = [r for r in runs if r["status"] == "abandoned"]
    done_ids   = {r["checklist_id"] for r in runs}
    missed_ids = ALL_CHECKLIST_IDS - done_ids

    critical_issues    = [i for i in issues if i["issue_type"] == "critical"]
    operational_issues = [i for i in issues if i["issue_type"] == "operational"]
    unresolved_count   = sum(1 for i in issues if not i["resolved"])

    # ── Header ───────────────────────────────────────────────────────────────
    location = ""
    if restaurant:
        location = restaurant.name
        if restaurant.branch:
            location += f" \u2013 {restaurant.branch}"

    lines: list[str] = []
    lines.append("============================")
    lines.append("   \U0001f4cb  SIGMO DAILY REPORT")
    lines.append("============================")
    if location:
        lines.append(f"\U0001f3e6 {location}")
    lines.append(f"\U0001f4c5 {date_str}")
    lines.append("")

    # ── Nothing at all ───────────────────────────────────────────────────────
    if not completed and not abandoned and not issues:
        lines.append("\u26a0\ufe0f No activity recorded yesterday.")
        lines.append("")
        lines.append("All 4 checklists were missed:")
        for cid in sorted(ALL_CHECKLIST_IDS):
            lines.append(f"  \u2022 {CHECKLIST_LABELS.get(cid, cid)}")
        return "\n".join(lines).strip()

    # ── Completed ────────────────────────────────────────────────────────────
    if completed:
        lines.append("\u2705 <b>Completed</b>")
        for r in completed:
            label  = CHECKLIST_LABELS.get(r["checklist_id"], r["checklist_id"])
            start  = to_pht(r["start_time"]).strftime("%I:%M %p") if r["start_time"] else "?"
            end    = to_pht(r["end_time"]).strftime("%I:%M %p")   if r["end_time"]   else "?"
            dur    = _fmt_duration(r["duration_seconds"])
            photos = f"  \U0001f4f7 {r['photo_count']}" if r["photo_count"] else ""
            lines.append(f"  <b>{label}</b>")
            lines.append(f"  \U0001f464 {r['staff_name']}   \U0001f550 {start} \u2192 {end}   \u23f1 {dur}{photos}")
        lines.append("")

    # ── Abandoned ────────────────────────────────────────────────────────────
    if abandoned:
        lines.append("\u274c <b>Abandoned</b>")
        for r in abandoned:
            label = CHECKLIST_LABELS.get(r["checklist_id"], r["checklist_id"])
            start = to_pht(r["start_time"]).strftime("%I:%M %p") if r["start_time"] else "?"
            end   = to_pht(r["end_time"]).strftime("%I:%M %p")   if r["end_time"]   else "?"
            dur   = _fmt_duration(r["duration_seconds"])
            lines.append(f"  <b>{label}</b>")
            lines.append(f"  \U0001f464 {r['staff_name']}   Started {start}, cancelled {end}   \u23f1 {dur} elapsed")
        lines.append("")

    # ── Missed ───────────────────────────────────────────────────────────────
    if missed_ids:
        lines.append("\u26a0\ufe0f <b>Not Done Yesterday</b>")
        for cid in sorted(missed_ids):
            lines.append(f"  \u2022 {CHECKLIST_LABELS.get(cid, cid)}")
        lines.append("")

    # ── Issues ───────────────────────────────────────────────────────────────
    if issues:
        lines.append("\U0001f6a8 <b>Issues Reported</b>")
        for issue in critical_issues:
            label    = CHECKLIST_LABELS.get(issue["checklist_id"], issue["checklist_id"])
            time_str = to_pht(issue["reported_at"]).strftime("%I:%M %p")
            status   = "\u2705 resolved" if issue["resolved"] else "\U0001f534 <b>UNRESOLVED</b>"
            lines.append(f"  \U0001f534 <b>Critical</b>  [{status}]")
            lines.append(f"  \U0001f464 {issue['staff_name']}   {label}  Step {issue['step_number']}   \U0001f550 {time_str}")
            lines.append(f"  \U0001f4dd \"{issue['description']}\"")
        for issue in operational_issues:
            label    = CHECKLIST_LABELS.get(issue["checklist_id"], issue["checklist_id"])
            time_str = to_pht(issue["reported_at"]).strftime("%I:%M %p")
            status   = "\u2705 resolved" if issue["resolved"] else "\U0001f7e1 unresolved"
            lines.append(f"  \U0001f7e1 <b>Operational</b>  [{status}]")
            lines.append(f"  \U0001f464 {issue['staff_name']}   {label}  Step {issue['step_number']}   \U0001f550 {time_str}")
            lines.append(f"  \U0001f4dd \"{issue['description']}\"")
        lines.append("")

    # ── Totals ───────────────────────────────────────────────────────────────
    total = len(completed) + len(abandoned)
    lines.append("----------------------------")
    lines.append(f"\U0001f4ca Completion:  {len(completed)}/{total} checklists done")
    if missed_ids:
        lines.append(f"\u23f3 Missed:      {len(missed_ids)} checklist(s)")
    if issues:
        issue_line = f"\u26a0\ufe0f  Issues:      {len(issues)} reported"
        if unresolved_count:
            issue_line += f"  ({unresolved_count} still open \u2757)"
        else:
            issue_line += "  (all resolved \u2705)"
        lines.append(issue_line)
    lines.append("============================")

    return "\n".join(lines).strip()