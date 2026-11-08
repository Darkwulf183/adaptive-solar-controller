from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components import websocket_api
import voluptuous as vol
from datetime import date
from homeassistant.util import dt as dt_util
from .passive_pv import parse_csv, summary
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DAILY_PRODUCTION_SENSOR, DOMAIN, PLATFORMS
from .coordinator import AdaptiveSolarCoordinator

STATIC_URL = "/asc_static"

@websocket_api.websocket_command({vol.Required("type"): "adaptive_solar_controller/pv_csv",
    vol.Required("entry_id"): str, vol.Required("csv"): str, vol.Optional("commit", default=False): bool,
    vol.Optional("replace", default=False): bool})
@websocket_api.async_response
async def async_pv_csv(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Administrator required")
        return
    coordinator = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if coordinator is None or getattr(coordinator, "controller", None) is None:
        connection.send_error(msg["id"], "not_found", "ASC config entry not running")
        return
    try:
        today = dt_util.as_local(dt_util.utcnow()).date()
        expected = coordinator.cfg.get(CONF_DAILY_PRODUCTION_SENSOR) or None
        # CSV parsing can take a while for big exports: keep it out of the event loop.
        incoming = await hass.async_add_executor_job(parse_csv, msg["csv"], hass.config.time_zone, today, expected)
        state = coordinator.controller.state
        existing = state.passive_pv_daily_kwh
        added = {k: v for k, v in incoming.items() if k not in existing}
        changed = ({k: v for k, v in incoming.items() if k in existing and abs(existing[k] - v) > 1e-9}
                   if msg["replace"] else {})
        merged = {**existing, **added, **changed}
        result = summary(merged, today)
        result.update(parsed_days=len(incoming), added_days=len(added), replaced_days=len(changed),
                      duplicates=len(incoming) - len(added) - len(changed), committed=bool(msg["commit"]))
        if msg["commit"] and (added or changed):
            state.passive_pv_daily_kwh = merged
            state.passive_pv_imported_at = dt_util.utcnow().isoformat()
            state.passive_pv_import_count += 1
            await coordinator.store.async_save(state)
        connection.send_result(msg["id"], result)
    except (ValueError, TypeError) as exc:
        connection.send_error(msg["id"], "invalid_csv", str(exc))



async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries without deleting learned storage."""
    if entry.version < 6:
        # v0.4 no longer uses the old inverter-max helper, battery-high helper,
        # learned-min helper or fixed battery-high base value. Leaving stale keys
        # in entry.data is harmless; the v4 schema no longer exposes/reads them.
        hass.config_entries.async_update_entry(entry, version=6)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})
    # Registered once per HA run: reloads (options/reconfigure) must not register again.
    if not domain_data.get("_static_registered"):
        static_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(static_dir), False)]
        )
        domain_data["_static_registered"] = True
    if not domain_data.get("_pv_ws_registered"):
        websocket_api.async_register_command(hass, async_pv_csv)
        domain_data["_pv_ws_registered"] = True
    coordinator = AdaptiveSolarCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if coordinator:
        await coordinator.async_stop()
    return ok
