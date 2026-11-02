"""Add-on options and where things are stored."""
import json
from pathlib import Path

# Private to the add-on: options, accounts and sign-ins, check results.
PRIVATE_DIR = Path("/data")
# This add-on's folder under addon_configs, reachable over the Samba share, so
# the raw contact snapshots can be opened from a PC.
SHARED_DIR = Path("/config")

DEFAULTS = {"daily_check_time": "08:00", "notify": ""}


def load_options() -> dict:
    """The add-on's options with every key present, so callers can index them directly."""
    with (PRIVATE_DIR / "options.json").open(encoding="utf-8") as f:
        return {**DEFAULTS, **_trimmed(json.load(f))}


def _trimmed(value):
    # IDs and passwords are often pasted with a stray space or newline.
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_trimmed(v) for v in value]
    if isinstance(value, dict):
        return {key: _trimmed(v) for key, v in value.items()}
    return value
