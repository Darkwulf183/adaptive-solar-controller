from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AUTHORS, DOMAIN, VERSION


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ControllerEnableSwitch(c, entry),
        FlightRecorderSwitch(c, entry),
        BatteryCalibrationSwitch(c, entry),
    ])


class _BaseSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry, key: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller",
            "manufacturer": AUTHORS, "model": f"ASC v{VERSION}",
        }


class ControllerEnableSwitch(_BaseSwitch):
    _attr_name = "Controller enabled"; _attr_icon = "mdi:power"
    def __init__(self, coordinator, entry): super().__init__(coordinator, entry, "enabled")
    @property
    def is_on(self): return self.coordinator.controller.enabled
    async def async_turn_on(self, **kwargs): await self.coordinator.async_set_enabled(True); self.async_write_ha_state()
    async def async_turn_off(self, **kwargs): await self.coordinator.async_set_enabled(False); self.async_write_ha_state()


class FlightRecorderSwitch(_BaseSwitch):
    _attr_name = "14 day flight recorder"; _attr_icon = "mdi:airplane-clock"
    def __init__(self, coordinator, entry): super().__init__(coordinator, entry, "flight_recorder")
    @property
    def is_on(self): return self.coordinator.controller.state.flight_recorder_enabled
    async def async_turn_on(self, **kwargs): await self.coordinator.async_set_flight_recorder(True); self.async_write_ha_state()
    async def async_turn_off(self, **kwargs): await self.coordinator.async_set_flight_recorder(False); self.async_write_ha_state()


class BatteryCalibrationSwitch(_BaseSwitch):
    _attr_name = "Battery calibration"; _attr_icon = "mdi:battery-sync-outline"
    def __init__(self, coordinator, entry): super().__init__(coordinator, entry, "battery_calibration")
    @property
    def is_on(self): return self.coordinator.controller.state.battery_calibration_enabled
    async def async_turn_on(self, **kwargs): await self.coordinator.async_set_battery_calibration(True); self.async_write_ha_state()
    async def async_turn_off(self, **kwargs): await self.coordinator.async_set_battery_calibration(False); self.async_write_ha_state()
