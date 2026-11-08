"""What Contact Sync shares in its diagnostics download, with passwords, sign-ins, names and email addresses taken
out: how it's set up, what the latest check found in each account, and what the last apply did."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ContactSyncConfigEntry
from .const import CONF_CLIENT_ID
from .engine import apply, check

TO_REDACT = {"app_password", "refresh_token", "client_secret", "apple_id", "email", "label", "login", "name"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ContactSyncConfigEntry) -> dict[str, Any]:
    sync = entry.runtime_data
    status = await hass.async_add_executor_job(check.load_status)
    result = await hass.async_add_executor_job(apply.load_result)
    return {
        "version": sync.version,
        "options": dict(entry.options),
        "google_app_set": bool(entry.data.get(CONF_CLIENT_ID)),
        "accounts": [{"type": s.subentry_type, **async_redact_data(dict(s.data), TO_REDACT)}
                     for s in entry.subentries.values()],
        "checking": sync.checking,
        "applying": sync.applying,
        "check_error": sync.check_error,
        "counts": sync.counts,
        "latest_check": async_redact_data(status, TO_REDACT) if status else None,
        "last_apply": {"status": result["status"], "started_at": result["started_at"],
                       "finished_at": result["finished_at"], "summary": apply.summary(result),
                       "not_made": sum(bool(c["error"]) for c in result["changes"])} if result else None,
    }
