"""Prometheus metrics definitions for Sigmo."""

from prometheus_client import Counter, Gauge, Histogram

checklist_started = Counter(
    "sigmo_checklist_started_total",
    "Total checklists started",
    ["restaurant_id", "checklist_id"],
)

checklist_completed = Counter(
    "sigmo_checklist_completed_total",
    "Total checklists completed",
    ["restaurant_id", "checklist_id"],
)

checklist_abandoned = Counter(
    "sigmo_checklist_abandoned_total",
    "Total checklists abandoned",
    ["restaurant_id", "checklist_id"],
)

checklist_duration = Histogram(
    "sigmo_checklist_duration_seconds",
    "Time to complete a checklist in seconds",
    ["restaurant_id", "checklist_id"],
    buckets=[60, 120, 300, 600, 900, 1800, 3600],
)

issues_reported = Counter(
    "sigmo_issues_reported_total",
    "Total issues reported",
    ["restaurant_id", "issue_type"],
)

photos_submitted = Counter(
    "sigmo_photos_submitted_total",
    "Total photos submitted during checklists",
    ["restaurant_id"],
)

active_sessions = Gauge(
    "sigmo_active_sessions",
    "Currently active checklist sessions",
    ["restaurant_id"],
)

webhook_latency = Histogram(
    "sigmo_webhook_processing_seconds",
    "Webhook processing time in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)