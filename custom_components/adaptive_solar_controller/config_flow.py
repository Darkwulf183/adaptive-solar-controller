from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import *


REQUIRED_ENTITY_FIELDS = [
    (CONF_GRID_SENSOR, "sensor"),
    (CONF_PV_SENSOR, "sensor"),
    (CONF_DAILY_PRODUCTION_SENSOR, "sensor"),
    (CONF_BATTERY_VOLTAGE_SENSOR, "sensor"),
    (CONF_BATTERY_CURRENT_SENSOR, "sensor"),
    (CONF_INVERTER_OUTPUT_SENSOR, "sensor"),
    (CONF_TARGET_HELPER, "input_number"),
    (CONF_BATTERY_LOW_HELPER, "input_number"),
    (CONF_BACKUP_INVERTER, "number"),
]

FORECAST_FIELDS = [
    CONF_FORECAST_POWER_NOW,
    CONF_FORECAST_POWER_NEXT_HOUR,
    CONF_FORECAST_ENERGY_NEXT_HOUR,
    CONF_FORECAST_ENERGY_TODAY,
    CONF_FORECAST_ENERGY_REMAINING,
    CONF_FORECAST_ENERGY_TOMORROW,
    CONF_FORECAST_PEAK_TIME_TODAY,
]


def _entity_selector(domain: str | list[str]) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


def _optional_entity(schema: dict, key: str, values: dict, domain: str = "sensor") -> None:
    value = values.get(key, DEFAULTS.get(key, ""))
    field = vol.Optional(key, default=value) if value else vol.Optional(key)
    schema[field] = _entity_selector(domain)


def _schema(values: dict | None = None) -> vol.Schema:
    values = values or {}
    schema: dict = {}

    for key, domain in REQUIRED_ENTITY_FIELDS:
        schema[vol.Required(key, default=values.get(key, DEFAULTS[key]))] = _entity_selector(domain)

    _optional_entity(schema, CONF_BATTERY_POWER_SENSOR, values)

    schema[
        vol.Required(
            CONF_SOLAR_ENABLE,
            default=values.get(CONF_SOLAR_ENABLE, DEFAULTS[CONF_SOLAR_ENABLE]),
        )
    ] = _entity_selector(["input_boolean", "switch"])

    _optional_entity(schema, CONF_INVERTER_POWER_SWITCH, values, domain="switch")

    for key in FORECAST_FIELDS:
        _optional_entity(schema, key, values)

    schema[
        vol.Required(CONF_GRID_TARGET, default=values.get(CONF_GRID_TARGET, DEFAULTS[CONF_GRID_TARGET]))
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-100,
            max=500,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="W",
        )
    )
    schema[
        vol.Required(CONF_BACKUP_BLOCK_W, default=values.get(CONF_BACKUP_BLOCK_W, DEFAULTS[CONF_BACKUP_BLOCK_W]))
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=1000,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="W",
        )
    )
    schema[
        vol.Required(CONF_MIN_TARGET_W, default=values.get(CONF_MIN_TARGET_W, DEFAULTS[CONF_MIN_TARGET_W]))
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=300,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="W",
        )
    )
    schema[
        vol.Required(CONF_MAX_STEP_W, default=values.get(CONF_MAX_STEP_W, DEFAULTS[CONF_MAX_STEP_W]))
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=20,
            max=1000,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="W",
        )
    )
    schema[
        vol.Required(CONF_HARD_MAX_W, default=values.get(CONF_HARD_MAX_W, DEFAULTS[CONF_HARD_MAX_W]))
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=30,
            max=2000,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="W",
        )
    )
    for key, low, high, step, unit in (
        (CONF_ABSORPTION_V, 26.0, 31.0, 0.1, "V"),
        (CONF_ABSORPTION_TOLERANCE_V, 0.0, 1.0, 0.1, "V"),
        (CONF_ABSORPTION_MINUTES, 30, 360, 5, "min"),
    ):
        schema[vol.Required(key, default=values.get(key, DEFAULTS[key]))] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=low, max=high, step=step,
                                          mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit)
        )
    return vol.Schema(schema)


class AdaptiveSolarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 6

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id("adaptive_solar_controller")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Adaptive Solar Controller", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema())

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        current = {**DEFAULTS, **entry.data, **entry.options}
        if user_input is not None:
            self.hass.config_entries.async_update_entry(entry, options={})
            return self.async_update_reload_and_abort(
                entry,
                data_updates=user_input,
                reload_even_if_entry_is_unchanged=False,
            )
        return self.async_show_form(step_id="reconfigure", data_schema=_schema(current))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        return AdaptiveSolarOptionsFlow()


class AdaptiveSolarOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema(current))
