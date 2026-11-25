"""Controlled icon identifiers for catalog entries.

The frontend maps each identifier to an icon (frontend/src/components/catalogIcons.tsx).
Add an identifier here AND there together; unknown identifiers fall back to a
generic tool icon in the UI. Icons always appear next to text labels.
"""

ICON_IDS = [
    # trades
    "zap",
    "wrench",
    "snowflake",
    # electrical
    "cable",
    "plug",
    "lightbulb",
    "fan",
    "battery",
    "toggle",
    # plumbing
    "droplet",
    "shower",
    "waves",
    "cylinder",
    "cog",
    "flame",
    "bath",
    # air conditioning
    "spray",
    "gauge",
    "thermometer",
    "circuit_board",
    "truck",
    "wind",
    # generic / places
    "hammer",
    "map_pin",
    "building",
]

ICON_CHOICES = [(icon, icon) for icon in ICON_IDS]
