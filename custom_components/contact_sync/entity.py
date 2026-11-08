"""What Contact Sync's entities share: one device for the service, and updates whenever the review changes."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, PANEL, SIGNAL_UPDATED
from .runtime import ContactSync


class ContactSyncEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, sync: ContactSync, key: str) -> None:
        self.sync = sync
        self._attr_translation_key = key
        self._attr_unique_id = f"{sync.entry.entry_id}_{key}"
        # The device's page links to the panel, and shows the version installed.
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, sync.entry.entry_id)}, name="Contact Sync",
                                            entry_type=DeviceEntryType.SERVICE, sw_version=sync.version,
                                            configuration_url=f"homeassistant://{PANEL}")

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self.async_write_ha_state))
