"""How many changes are waiting to be applied, and when the accounts were last checked."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ContactSyncConfigEntry
from .entity import ContactSyncEntity


async def async_setup_entry(hass: HomeAssistant, entry: ContactSyncConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([ChangesWaiting(entry.runtime_data, "changes_waiting"),
                        LastCheck(entry.runtime_data, "last_check")])


class ChangesWaiting(ContactSyncEntity, SensorEntity):
    """The changes a sync would make. What's still to decide in the review is in the attributes."""

    _attr_icon = "mdi:account-sync"

    @property
    def native_value(self) -> int | None:
        return self.sync.counts["changes"] if self.sync.counts is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        counts = self.sync.counts or {}
        return {"possible_matches": counts.get("suggestions", 0), "values_to_choose": counts.get("conflicts", 0),
                "duplicates": counts.get("duplicates", 0), "extra_details": counts.get("extras", 0),
                "contacts_without_group": counts.get("ungrouped", 0)}


class LastCheck(ContactSyncEntity, SensorEntity):
    """When every account was last read, and any that couldn't be."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        return self.sync.checked_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"accounts_not_read": self.sync.unread}
