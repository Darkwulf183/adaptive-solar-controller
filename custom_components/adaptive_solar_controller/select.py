from __future__ import annotations
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import AUTHORS, DOMAIN, MODES, VERSION
from .strategy import CHEMISTRIES

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ControlModeSelect(c,entry), BatteryChemistrySelect(c,entry), LowRecoveryModeSelect(c,entry)])

class _Base(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name=True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_device_info={"identifiers":{(DOMAIN,entry.entry_id)},"name":"Adaptive Solar Controller","manufacturer":AUTHORS,"model":f"ASC v{VERSION}"}

class ControlModeSelect(_Base):
    _attr_name="Control mode"; _attr_options=MODES; _attr_icon="mdi:tune"
    def __init__(self, coordinator, entry): super().__init__(coordinator,entry); self._attr_unique_id=f"{entry.entry_id}_control_mode"
    @property
    def current_option(self): return self.coordinator.controller.mode
    async def async_select_option(self, option):
        if option in MODES: await self.coordinator.async_set_mode(option); self.async_write_ha_state()

class BatteryChemistrySelect(_Base):
    _attr_name="Battery chemistry"; _attr_options=CHEMISTRIES; _attr_icon="mdi:battery-heart-variant"
    def __init__(self, coordinator, entry): super().__init__(coordinator,entry); self._attr_unique_id=f"{entry.entry_id}_battery_chemistry"
    @property
    def current_option(self): return self.coordinator.controller.state.battery_chemistry
    async def async_select_option(self, option):
        if option in CHEMISTRIES: await self.coordinator.async_set_battery_chemistry(option); self.async_write_ha_state()


class LowRecoveryModeSelect(_Base):
    _attr_name = "LOW recovery calibration mode"
    _attr_options = ["Aus", "Automatisch", "Gezielt"]
    _attr_icon = "mdi:battery-sync-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_low_recovery_calibration_mode"

    @property
    def current_option(self):
        return self.coordinator.controller.state.low_recovery_mode

    async def async_select_option(self, option):
        if option in self._attr_options:
            await self.coordinator.async_set_low_recovery_mode(option)
            self.async_write_ha_state()
