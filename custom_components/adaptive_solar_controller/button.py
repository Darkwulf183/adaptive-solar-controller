from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AUTHORS, DOMAIN, VERSION


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ResetFullVoltageButton(c, entry)])


class ResetFullVoltageButton(CoordinatorEntity, ButtonEntity):
    """Forget the learned FULL charge voltage (e.g. after a one-off outlier)."""

    _attr_has_entity_name = True
    _attr_name = "Reset learned full charge voltage"
    _attr_icon = "mdi:battery-sync"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_reset_full_voltage"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller",
            "manufacturer": AUTHORS, "model": f"ASC v{VERSION}",
        }

    async def async_press(self) -> None:
        await self.coordinator.async_reset_full_voltage()
