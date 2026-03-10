"""Prometheus metrics definitions for Sigmo."""

from prometheus_client import Counter, Histogram

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
    "Time to complete a checklist",
    ["restaurant_id", "checklist_id"],
)

webhook_latency = Histogram(
    "sigmo_webhook_processing_seconds",
    "Webhook processing time",
)
