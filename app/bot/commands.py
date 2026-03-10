"""Command parser – maps staff text messages to checklist IDs."""

COMMAND_MAP: dict[str, str] = {
    "kitchen opening": "KITCHEN_OPEN",
    "kitchen closing": "KITCHEN_CLOSE",
    "dining opening": "DINING_OPEN",
    "dining closing": "DINING_CLOSE",
}


def parse_command(text: str) -> str | None:
    """Return a checklist_id if the text matches a known command, else None."""
    return COMMAND_MAP.get(text.strip().lower())
