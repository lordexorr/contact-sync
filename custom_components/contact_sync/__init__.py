"""Contact Sync: keeps contacts in sync across iCloud and Google accounts, and writes nothing to any account until
the changes are reviewed and applied on its page in the sidebar."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from . import websocket
from .const import DOMAIN, PANEL, STATIC_URL
from .engine import settings
from .runtime import ContactSync
from .views import ThumbView

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
FRONTEND_DIR = Path(__file__).parent / "frontend"

type ContactSyncConfigEntry = ConfigEntry[ContactSync]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """What stays for as long as Home Assistant runs: the panel's commands and files, and the photo thumbnails."""
    websocket.async_register(hass)
    hass.http.register_view(ThumbView(hass))
    await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ContactSyncConfigEntry) -> bool:
    # The engine's private files sit with Home Assistant's own; the snapshots and backups in a folder of their
    # own in the config folder, which the Samba share reaches.
    settings.configure(Path(hass.config.path(STORAGE_DIR, DOMAIN)), Path(hass.config.path(DOMAIN)))
    entry.runtime_data = sync = ContactSync(hass, entry)
    await sync.async_start()
    entry.async_on_unload(sync.async_stop)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # The version in the panel's address makes browsers fetch it afresh after an update.
    version = (await async_get_integration(hass, DOMAIN)).version
    await panel_custom.async_register_panel(
        hass, frontend_url_path=PANEL, webcomponent_name="contact-sync-panel", sidebar_title="Contact Sync",
        sidebar_icon="mdi:contacts", module_url=f"{STATIC_URL}/contact-sync-panel.js?v={version}", require_admin=True,
    )
    entry.async_on_unload(lambda: frontend.async_remove_panel(hass, PANEL))
    # Adding or removing an account, or changing the options, starts everything again with the new ones.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ContactSyncConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ContactSyncConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
