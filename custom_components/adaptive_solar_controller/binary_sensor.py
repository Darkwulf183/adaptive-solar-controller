from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AUTHORS, DOMAIN, VERSION


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([EnergySurplusAvailableBinarySensor(hass.data[DOMAIN][entry.entry_id], entry)])


class EnergySurplusAvailableBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Energy surplus available"
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_energy_surplus_available"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller",
            "manufacturer": AUTHORS, "model": f"ASC v{VERSION}",
        }

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("surplus_available", False))
