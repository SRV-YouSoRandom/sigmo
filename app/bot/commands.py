"""Command parser – maps staff text messages and slash commands to checklist IDs."""

COMMAND_MAP: dict[str, str] = {
    "kitchen opening": "KITCHEN_OPEN",
    "kitchen closing": "KITCHEN_CLOSE",
    "dining opening": "DINING_OPEN",
    "dining closing": "DINING_CLOSE",
    # Slash command equivalents
    "/kitchen_opening": "KITCHEN_OPEN",
    "/kitchen_closing": "KITCHEN_CLOSE",
    "/dining_opening": "DINING_OPEN",
    "/dining_closing": "DINING_CLOSE",
}

# Slash commands to register with BotFather via setMyCommands
BOT_COMMANDS = [
    {"command": "start", "description": "Start the bot and see available checklists"},
    {"command": "help", "description": "Show how to use the bot"},
    {"command": "kitchen_opening", "description": "Start Kitchen Opening checklist"},
    {"command": "kitchen_closing", "description": "Start Kitchen Closing checklist"},
    {"command": "dining_opening", "description": "Start Dining Opening checklist"},
    {"command": "dining_closing", "description": "Start Dining Closing checklist"},
    {"command": "cancel", "description": "Cancel the current checklist"},
]


def parse_command(text: str) -> str | None:
    """Return a checklist_id if the text matches a known command, else None."""
    return COMMAND_MAP.get(text.strip().lower())