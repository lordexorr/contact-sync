"""Check every account now, as the Check now button on the panel does."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ContactSyncConfigEntry
from .entity import ContactSyncEntity


async def async_setup_entry(hass: HomeAssistant, entry: ContactSyncConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([CheckNow(entry.runtime_data, "check_now")])


class CheckNow(ContactSyncEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    async def async_press(self) -> None:
        if self.sync.applying:  # applying checks every account itself
            raise HomeAssistantError("Contact Sync is applying changes. Check again once it has finished.")
        self.sync.start_check()
