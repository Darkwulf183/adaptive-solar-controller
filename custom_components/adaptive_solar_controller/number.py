from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTime
from homeassistant.helpers import entity_registry as er
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AUTHORS, DOMAIN, VERSION, CONF_ABSORPTION_MINUTES, DEFAULTS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    # Remove the obsolete read-only sensor from the registry before registering the
    # editable number with the same suggested object_id. Existing history stays intact.
    registry = er.async_get(hass)
    old_unique_id = f"{entry.entry_id}_absorption_required"
    old_id = registry.async_get_entity_id("sensor", DOMAIN, old_unique_id)
    if old_id:
        registry.async_remove(old_id)
    async_add_entities([
        BatteryCapacityStartNumber(hass.data[DOMAIN][entry.entry_id], entry),
        FullAbsorptionRequiredNumber(hass.data[DOMAIN][entry.entry_id], entry),
        InverterMaxPowerNumber(hass.data[DOMAIN][entry.entry_id], entry),
        BatteryHardCutoffNumber(hass.data[DOMAIN][entry.entry_id], entry),
        BatteryEmergencyVoltageNumber(hass.data[DOMAIN][entry.entry_id], entry),
    ])


class BatteryCapacityStartNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Battery usable capacity start"
    _attr_icon = "mdi:battery-plus-variant"
    _attr_native_min_value = 0.5
    _attr_native_max_value = 30.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_battery_capacity_start"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller",
            "manufacturer": AUTHORS, "model": f"ASC v{VERSION}",
        }

    @property
    def native_value(self):
        return round(self.coordinator.controller.state.battery_capacity_start_kwh, 1)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_battery_capacity_start(float(value))
        self.async_write_ha_state()


class FullAbsorptionRequiredNumber(CoordinatorEntity, NumberEntity):
    """Editable cumulative absorption threshold; no duplicate read-only sensor."""
    _attr_has_entity_name = True
    _attr_name = "FULL absorption required"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_native_min_value = 30
    _attr_native_max_value = 360
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_full_absorption_required_number"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller",
            "manufacturer": AUTHORS, "model": f"ASC v{VERSION}",
        }

    @property
    def native_value(self):
        return float(self.coordinator.cfg.get(CONF_ABSORPTION_MINUTES, DEFAULTS[CONF_ABSORPTION_MINUTES]))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_absorption_minutes(value)
        self.async_write_ha_state()


class InverterMaxPowerNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Inverter max power"
    _attr_icon = "mdi:solar-power-variant"
    _attr_native_min_value = 30
    _attr_native_max_value = 800
    _attr_native_step = 10
    _attr_native_unit_of_measurement = "W"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_inverter_max_power"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller", "manufacturer": AUTHORS, "model": f"ASC v{VERSION}"}

    @property
    def native_value(self):
        return float(self.coordinator.controller.state.inverter_max_power_w)

    async def async_set_native_value(self, value: float):
        await self.coordinator.async_set_inverter_max_power(value)
        self.async_write_ha_state()


class BatteryHardCutoffNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Battery hard cutoff voltage"
    _attr_icon = "mdi:battery-alert"
    _attr_native_min_value = 20.0
    _attr_native_max_value = 25.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "V"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_battery_hard_cutoff_voltage"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller", "manufacturer": AUTHORS, "model": f"ASC v{VERSION}"}

    @property
    def native_value(self):
        return round(self.coordinator.controller.state.hard_cutoff_voltage_v, 1)

    async def async_set_native_value(self, value: float):
        await self.coordinator.async_set_hard_cutoff_voltage(value)
        self.async_write_ha_state()


class BatteryEmergencyVoltageNumber(CoordinatorEntity, NumberEntity):
    """Absolute terminal-voltage emergency cutoff independent of rebound model."""
    _attr_has_entity_name = True
    _attr_name = "Battery emergency terminal cutoff voltage"
    _attr_icon = "mdi:battery-alert-variant"
    _attr_native_min_value = 20.0
    _attr_native_max_value = 25.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "V"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_battery_emergency_terminal_voltage"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller", "manufacturer": AUTHORS, "model": f"ASC v{VERSION}"}

    @property
    def native_value(self):
        return round(self.coordinator.controller.state.emergency_terminal_voltage_v, 1)

    async def async_set_native_value(self, value: float):
        await self.coordinator.async_set_emergency_terminal_voltage(value)
        self.async_write_ha_state()
