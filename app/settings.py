"""Add-on options and where things are stored."""
import json
from pathlib import Path

# Private to the add-on: options, Google sign-ins, check results.
PRIVATE_DIR = Path("/data")
# This add-on's folder under addon_configs, reachable over the Samba share, so
# the raw contact snapshots can be opened from a PC.
SHARED_DIR = Path("/config")

DEFAULTS = {"daily_check_time": "08:00", "google": {}, "icloud_accounts": []}
ICLOUD_KEYS = ("label", "apple_id", "app_password")


def load_options() -> dict:
    """The add-on's options with every key present, so callers can index them directly.

    The Configuration tab's Google section arrives as {"google": {"client_id", "client_secret"}}
    and is flattened here to google_client_id and google_client_secret.
    """
    with (PRIVATE_DIR / "options.json").open(encoding="utf-8") as f:
        options = {**DEFAULTS, **_trimmed(json.load(f))}
    google = options.pop("google") or {}
    options["google_client_id"] = google.get("client_id", "")
    options["google_client_secret"] = google.get("client_secret", "")
    options["icloud_accounts"] = [{key: a.get(key, "") for key in ICLOUD_KEYS} for a in options["icloud_accounts"]]
    return options


def _trimmed(value):
    # IDs and passwords are often pasted with a stray space or newline.
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_trimmed(v) for v in value]
    if isinstance(value, dict):
        return {key: _trimmed(v) for key, v in value.items()}
    return value
