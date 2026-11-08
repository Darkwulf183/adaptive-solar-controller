from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from functools import partial
import logging
import math
import time

from homeassistant.components import persistent_notification
from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import *
from .controller import AdaptiveController, PlantSnapshot
from .flight_recorder import FlightRecorder
from .lock_owner import ADOPTED, PENDING, RELEASED, reconcile_lock_owner
from . import switch_confirm
from .storage import LearningStore
from .rebound_learning import rebuild_reference_model, predicted_sag
from .passive_pv import estimate, summary
from .safety import OK, TRIP_RESULTS, UndervoltageGuard

_LOGGER = logging.getLogger(__name__)
GRID_STALE_SECONDS = 60


class AdaptiveSolarCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.cfg = {**DEFAULTS, **entry.data, **entry.options}
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.store = LearningStore(hass, entry.entry_id)
        self.recorder = FlightRecorder(hass, entry.entry_id)
        self.controller: AdaptiveController | None = None
        self._cycles_since_save = 0
        self._solar_was_enabled = False
        self._warmup_pending = True
        self._last_grid_event = None
        self._remove_grid_listener = None
        self._remove_watchdog = None
        self._low_recovery_session = None
        self._cutoff_latched = False
        self._cutoff_off = switch_confirm.SwitchOffTracker()
        self._lock_off = switch_confirm.SwitchOffTracker()
        self._guard = UndervoltageGuard()
        self._safety_lock = asyncio.Lock()
        self._last_cutoff_status = "ok"
        self._cutoff_notified = False
        self._passive_cache = None


    async def async_start(self) -> None:
        state = await self.store.async_load()
        # Historical measurements already reside in HA's persistent learning state.
        # No OneShot or one-time transfer code is included in this release.
        if state.rebound_learning_reference and not state.rebound_learning_model:
            state.rebound_learning_model = rebuild_reference_model(state.rebound_learning_reference)
            await self.store.async_save(state)
        self._cutoff_latched = bool(state.hard_cutoff_latched)
        self.controller = AdaptiveController(state)
        await self._async_bootstrap_seasonal_history()
        self._last_grid_event = dt_util.utcnow()
        self._remove_grid_listener = async_track_state_change_event(self.hass, [self.cfg[CONF_GRID_SENSOR]], self._async_grid_changed)
        self._remove_watchdog = async_track_time_interval(self.hass, self._async_grid_watchdog, timedelta(seconds=GRID_STALE_SECONDS))
        await self.async_request_refresh()

    async def _async_bootstrap_seasonal_history(self) -> None:
        if self.controller is None or self.controller.state.seasonal_history_bootstrapped:
            return
        entity_id = self.cfg.get(CONF_DAILY_PRODUCTION_SENSOR)
        if not entity_id:
            return
        end = dt_util.utcnow(); start = end - timedelta(days=1100)
        try:
            query = partial(history.state_changes_during_period, self.hass, start, end, entity_id, no_attributes=True, include_start_time_state=False)
            result = await get_instance(self.hass).async_add_executor_job(query)
            count = self.controller.seasonal.bootstrap_history(result.get(entity_id, []), dt_util.as_local(end).date())
            if count:
                _LOGGER.info("ASC imported %s historical PV production days", count)
                await self.store.async_save(self.controller.state)
        except Exception:
            _LOGGER.exception("ASC could not bootstrap seasonal PV history")

    async def async_stop(self) -> None:
        if self._remove_grid_listener: self._remove_grid_listener()
        if self._remove_watchdog: self._remove_watchdog()
        if self.controller: await self.store.async_save(self.controller.state)

    async def async_set_mode(self, mode: str) -> None:
        self.controller.mode = mode; self.controller.state.control_mode = mode; self.controller.reset_transient()
        await self.store.async_save(self.controller.state); await self.async_request_refresh()

    async def async_set_enabled(self, enabled: bool) -> None:
        self.controller.enabled = enabled; self.controller.state.controller_enabled = enabled; self.controller.reset_transient()
        await self.store.async_save(self.controller.state); await self.async_request_refresh()

    async def async_set_flight_recorder(self, enabled: bool) -> None:
        self.controller.state.flight_recorder_enabled = enabled
        await self.store.async_save(self.controller.state); await self.async_request_refresh()

    async def async_set_battery_calibration(self, enabled: bool) -> None:
        self.controller.state.battery_calibration_enabled = enabled
        self.controller.state.calibration_full_seen = False
        self.controller.reset_transient()
        await self.store.async_save(self.controller.state); await self.async_request_refresh()

    async def async_set_inverter_max_power(self, value: float) -> None:
        # Stored separately from config-entry options: no risk of clearing inverter switch.
        value = max(30.0, min(800.0, 30.0 + round((float(value) - 30.0) / 10.0) * 10.0))
        self.controller.state.inverter_max_power_w = value
        await self.store.async_save(self.controller.state)
        await self.async_request_refresh()

    async def async_set_hard_cutoff_voltage(self, value: float) -> None:
        state = self.controller.state
        state.hard_cutoff_voltage_v = max(20.0, min(25.0, round(float(value), 1)))
        await self.store.async_save(state)
        await self.async_request_refresh()

    async def async_set_emergency_terminal_voltage(self, value: float) -> None:
        state = self.controller.state
        state.emergency_terminal_voltage_v = max(20.0, min(25.0, round(float(value), 1)))
        await self.store.async_save(state)
        await self.async_request_refresh()

    async def async_set_low_recovery_mode(self, mode: str) -> None:
        if mode not in ("Aus", "Automatisch", "Gezielt"):
            return
        self.controller.state.low_recovery_mode = mode
        if mode == "Aus":
            self._low_recovery_session = None
            self.controller.state.low_recovery_last_status = "off"
        await self.store.async_save(self.controller.state)
        await self.async_request_refresh()

    def _low_recovery_update(self, snap, result, now, had_full_cycle: bool):
        """FULL-gated LOW recovery, with 120s load and 480s relax phases.

        Gezielt requests power only within measured house demand; Automatisch
        observes naturally occurring transitions without forcing extra output.
        Neither mode may bypass controller block, hard cutoff, PV charge, or FULL.
        """
        state = self.controller.state
        mode = state.low_recovery_mode
        t = now.timestamp()
        session = self._low_recovery_session
        active_control = result.mode in (MODE_ADAPTIVE, MODE_PREDICTIVE) and not result.blocked
        sensor = self._state(self.cfg.get(CONF_BATTERY_VOLTAGE_SENSOR))
        try:
            direct_v = float(sensor.state) if sensor else float("nan")
            age = max(0.0, t - sensor.last_updated.timestamp()) if sensor else float("inf")
        except (TypeError, ValueError, AttributeError):
            direct_v, age = float("nan"), float("inf")
        low = snap.battery_low_v
        safe = (mode != "Aus" and state.battery_chemistry == "lead_acid"
                and active_control and not self._cutoff_latched
                and math.isfinite(direct_v) and age <= 60
                and (direct_v + max(0.0, (predicted_sag(state.rebound_learning_model, snap.inverter_output_w) or 0.0) - 0.20)) > state.hard_cutoff_voltage_v + 0.05
                and snap.battery_a < 0.5
                and result.chemistry_strategy_state not in ("lead_full_hold", "lead_full_emergency"))
        if mode == "Aus" or state.battery_chemistry != "lead_acid":
            self._low_recovery_session = None
            state.low_recovery_last_status = "off"
            return None
        if not safe:
            if session is not None:
                self._low_recovery_session = None
                state.low_recovery_last_status = "aborted_safety_or_sensor"
                state.low_recovery_last_abort = state.low_recovery_last_status
            else:
                state.low_recovery_last_status = "waiting_safe_conditions"
            return None

        full_ts = state.last_full_anchor_ts
        if session is None:
            if (mode == "Automatisch" and state.low_recovery_last_success_ts
                    and t - state.low_recovery_last_success_ts < 180 * 86400):
                state.low_recovery_last_status = "waiting_180_day_interval"
                return None
            if not had_full_cycle or not full_ts or full_ts == state.low_recovery_last_full_ts:
                state.low_recovery_last_status = "waiting_full"
                return None
            if t <= full_ts or t - full_ts > 7 * 86400:
                state.low_recovery_last_status = "waiting_current_full"
                return None
            if low <= state.hard_cutoff_voltage_v + 0.05:
                state.low_recovery_last_status = "low_too_close_to_cutoff"
                return None
            max_w = min(800, state.inverter_max_power_w)
            steps = [round(max_w - (max_w - 30.0) * i / 9) for i in range(10)]
            session = {"full_ts": full_ts, "started": now.isoformat(), "step": 0,
                       "phase": "approach", "phase_start": t, "steps": steps,
                       "points": [], "samples": [], "last_v": direct_v,
                       "auto_load": None, "auto_pairs": []}
            self._low_recovery_session = session

        # FULL must remain from the same discharge; a new FULL invalidates the run.
        if state.last_full_anchor_ts != session["full_ts"]:
            self._low_recovery_session = None
            state.low_recovery_last_status = "aborted_new_full"
            state.low_recovery_last_abort = state.low_recovery_last_status
            return None

        if mode == "Automatisch":
            # Observe only; never force a target. Capture load/relax pairs near
            # the lower voltage range, then commit only when real LOW occurs.
            state.low_recovery_last_status = "auto_observing"
            if direct_v <= low + 1.0:
                if snap.inverter_output_w >= 90 and snap.battery_a < -2:
                    session["auto_load"] = (t, direct_v, snap.inverter_output_w, snap.battery_a)
                elif session["auto_load"] is not None and snap.inverter_output_w <= 50:
                    lt, lv, lw, la = session["auto_load"]
                    if t - lt <= 300 and direct_v >= lv + 0.03:
                        session["auto_pairs"].append({"actual_w":round(lw,1),
                            "load_v":round(lv,3), "relaxed_v":round(direct_v,3),
                            "sag_v":round(direct_v-lv,3)})
                        session["auto_pairs"] = session["auto_pairs"][-30:]
                    session["auto_load"] = None
            if "ENERGY_LOW_ANCHOR" in result.events:
                if session["auto_pairs"]:
                    state.low_recovery_runs = (state.low_recovery_runs + [{
                        "mode":"Automatisch", "full_ts":full_ts, "finished":now.isoformat(),
                        "points":session["auto_pairs"], "quality":"opportunistic"}])[-10:]
                    state.low_recovery_last_status = "complete"
                    state.low_recovery_last_success_ts = t
                else:
                    state.low_recovery_last_status = "waiting_usable_auto_pairs_next_cycle"
                state.low_recovery_last_full_ts = full_ts
                self._low_recovery_session = None
            return None

        # Gezielt: actively approach LOW using no more than measured house demand.
        if session["phase"] == "approach":
            state.low_recovery_last_status = "approaching_low"
            session["samples"].append((direct_v, snap.battery_a, snap.inverter_output_w))
            session["samples"] = session["samples"][-40:]
            if "ENERGY_LOW_ANCHOR" in result.events:
                vals = session["samples"]
                tail = vals[-5:]
                session["points"].append({"step": 1,
                    "requested_w": session["steps"][0],
                    "actual_w": round(sum(x[2] for x in tail) / len(tail), 1),
                    "load_v": round(sum(x[0] for x in tail) / len(tail), 3),
                    "battery_a": round(sum(x[1] for x in tail) / len(tail), 2),
                    "samples": len(vals)})
                session["phase"] = "relaxation"
                session["phase_start"] = t
                session["step"] = 0
                session["samples"] = []
                state.low_recovery_last_full_ts = full_ts
                return 30
            # Avoid export; the normal fast grid controller remains unchanged.
            house_w = max(30.0, snap.inverter_output_w + snap.grid_w - float(self.cfg[CONF_GRID_TARGET]))
            allowed = min(session["steps"][0], house_w, state.inverter_max_power_w)
            return round(max(30.0, allowed))

        # During relaxation keep the minimum inverter command. No forced grid export.
        if session["phase"] == "relaxation":
            state.low_recovery_last_status = "relaxation"
            session["samples"].append((direct_v, snap.battery_a, snap.inverter_output_w))
            if t - session["phase_start"] >= 480:
                values = session["samples"]
                if session["points"] and values:
                    session["points"][-1]["relaxed_v"] = round(sum(x[0] for x in values[-10:]) / len(values[-10:]), 3)
                    session["points"][-1]["sag_v"] = round(max(0.0, session["points"][-1]["relaxed_v"] - session["points"][-1]["load_v"]), 3)
                if session["step"] >= 9:
                    state.low_recovery_runs = (state.low_recovery_runs + [{
                        "mode":"Gezielt", "full_ts":full_ts, "started":session["started"],
                        "finished":now.isoformat(), "points":session["points"],
                        "quality":"full_validated"}])[-10:]
                    state.low_recovery_last_status = "complete"
                    state.low_recovery_last_success_ts = t
                    self._low_recovery_session = None
                    return 30
                session["step"] += 1
                session["phase"] = "load"
                session["phase_start"] = t
                session["samples"] = []
            return 30

        # Load steps 2..10; first 660W approach was already step 1.
        state.low_recovery_last_status = "load"
        house_w = max(30.0, snap.inverter_output_w + snap.grid_w - float(self.cfg[CONF_GRID_TARGET]))
        requested = min(session["steps"][session["step"]], house_w, state.inverter_max_power_w)
        session["samples"].append((direct_v, snap.battery_a, snap.inverter_output_w))
        if t - session["phase_start"] >= 120 or direct_v <= low:
            vals = session["samples"]
            session["points"].append({"step":session["step"] + 1,
                "requested_w":session["steps"][session["step"]],
                "actual_w":round(sum(x[2] for x in vals) / len(vals),1),
                "load_v":round(sum(x[0] for x in vals[-5:]) / len(vals[-5:]),3),
                "battery_a":round(sum(x[1] for x in vals) / len(vals),2),
                "samples":len(vals)})
            session["phase"] = "relaxation"
            session["phase_start"] = t
            session["samples"] = []
            return 30
        return round(max(30.0, requested))

    async def async_set_absorption_minutes(self, value: float) -> None:
        """Persist the new FULL threshold without resetting learned battery state."""
        value = float(max(30, min(360, round(float(value) / 5) * 5)))
        self.cfg[CONF_ABSORPTION_MINUTES] = value
        self.controller.battery.absorption_minutes = value
        # Update the same source that was already supplying the setting.
        if CONF_ABSORPTION_MINUTES in self.entry.options:
            opts = {**self.entry.options, CONF_ABSORPTION_MINUTES: value}
            self.hass.config_entries.async_update_entry(self.entry, options=opts)
        else:
            data = {**self.entry.data, CONF_ABSORPTION_MINUTES: value}
            self.hass.config_entries.async_update_entry(self.entry, data=data)
        await self.async_request_refresh()

    async def async_set_battery_capacity_start(self, value: float) -> None:
        value = max(0.5, min(30.0, round(value, 1)))
        state = self.controller.state
        state.battery_capacity_start_kwh = value
        # Explicitly moving the start-capacity slider means "new capacity basis".
        # Keep voltage/demand learning, reset only capacity/energy confidence.
        state.usable_capacity_estimate_kwh = value
        state.capacity_samples = 0
        state.stored_energy_kwh = min(value, max(0.0, state.stored_energy_kwh)) if state.stored_energy_kwh >= 0 else -1.0
        state.energy_anchor_seen = False
        state.energy_anchor_samples = 0
        state.energy_integrated_seconds = 0.0
        state.full_cycle_active = False
        state.discharge_since_full_kwh = 0.0
        self.controller.reset_transient()
        await self.store.async_save(state); await self.async_request_refresh()

    async def async_set_battery_chemistry(self, chemistry: str) -> None:
        if chemistry not in ("lead_acid", "lifepo4"):
            return
        state = self.controller.state
        if state.battery_chemistry == chemistry:
            return
        state.battery_chemistry = chemistry
        # Chemistry change means a new battery model basis. Preserve plant, demand,
        # forecast, seasonal and response learning; reset battery-specific strategy.
        state.capacity_samples = 0
        state.energy_anchor_seen = False
        state.energy_anchor_samples = 0
        state.stored_energy_kwh = -1.0
        state.full_cycle_active = False
        state.discharge_since_full_kwh = 0.0
        state.power_envelope_multiplier = 1.0
        state.power_envelope_samples = 0
        state.planner_eval_samples = 0
        state.planner_reserve_error_ema = 0.0
        state.planning_reserve_adjustment = 0.0
        state.progressive_gamma = 1.70 if chemistry == "lead_acid" else 1.45
        state.last_planner_evaluation = "chemistry_changed"
        self.controller.reset_transient()
        await self.store.async_save(state)
        await self.async_request_refresh()

    @callback
    def _async_grid_changed(self, event: Event[EventStateChangedData]) -> None:
        old_state = event.data.get("old_state"); new_state = event.data.get("new_state")
        if new_state is None or (old_state is not None and old_state.state == new_state.state): return
        try: value = float(new_state.state)
        except (TypeError, ValueError): return
        if not math.isfinite(value): return
        self._last_grid_event = dt_util.utcnow(); self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _async_grid_watchdog(self, now) -> None:
        if self.controller is None or self._last_grid_event is None: return
        if (dt_util.utcnow() - self._last_grid_event).total_seconds() <= GRID_STALE_SECONDS: return
        # No regular updates while the grid sensor is stale: keep watching the battery.
        self.hass.async_create_task(self._async_safety_only())
        if (self.data or {}).get("blocked_reason") == "grid_sensor_stale": return
        self.async_set_updated_data(self._paused_data("grid_sensor_stale"))

    def _state(self, entity_id: str | None): return self.hass.states.get(entity_id) if entity_id else None

    def _float_entity(self, entity_id: str | None, fallback: float | None = 0.0) -> float | None:
        state = self._state(entity_id)
        if state is None: return fallback
        try:
            value = float(state.state); return value if math.isfinite(value) else fallback
        except (TypeError, ValueError): return fallback

    def _float(self, key: str, fallback: float = 0.0) -> float: return float(self._float_entity(self.cfg.get(key), fallback))

    def _solar_release(self) -> tuple[bool, str]:
        state = self._state(self.cfg.get(CONF_SOLAR_ENABLE))
        if state is None or state.state in ("unknown", "unavailable", "none", ""): return False, "solar_release_unavailable"
        return state.state.lower() in ("on", "true", "1", "yes", "open"), ""

    def _critical_inputs(self) -> dict[str, float | None]:
        """Safety-critical measurements. None = unavailable/invalid (never silently 0)."""
        return {
            "battery_voltage": self._float_entity(self.cfg.get(CONF_BATTERY_VOLTAGE_SENSOR), None),
            "battery_current": self._float_entity(self.cfg.get(CONF_BATTERY_CURRENT_SENSOR), None),
            "grid": self._float_entity(self.cfg.get(CONF_GRID_SENSOR), None),
            "inverter_output": self._float_entity(self.cfg.get(CONF_INVERTER_OUTPUT_SENSOR), None),
        }

    async def _async_safety_only(self) -> None:
        if self.controller is None:
            return
        c = self._critical_inputs()
        self._last_cutoff_status = await self._async_manage_cutoff(
            c["battery_voltage"], c["battery_current"], c["inverter_output"]
        )

    async def _async_manage_cutoff(self, battery_v: float | None, battery_a: float | None, inverter_w: float | None) -> str:
        """Stop output on hard undervoltage, with debounce, hysteresis and ownership.

        Runs at the start of EVERY update (also while paused/warming up) and from the
        stale-grid watchdog. An unavailable voltage sensor is no longer read as 0 V:
        it trips only after a grace period (see safety.py). If no physical switch is
        configured, the 30 W helper floor cannot be mistaken for a disconnection.
        """
        async with self._safety_lock:
            state = self.controller.state
            cutoff = state.hard_cutoff_voltage_v
            emergency_floor = state.emergency_terminal_voltage_v
            invalid_voltage = battery_v is None or not math.isfinite(battery_v)
            current = battery_a if battery_a is not None and math.isfinite(battery_a) else 0.0

            relaxed_lower_v = None
            if not invalid_voltage:
                # Conservative relaxed-voltage estimate from the provisional rebound curve.
                # NOT a cell-level BMS. The terminal-voltage emergency floor never uses it.
                sag = predicted_sag(state.rebound_learning_model, max(0.0, inverter_w or 0.0))
                rebound_credit = max(0.0, sag - 0.20) if sag is not None and current < -0.5 else 0.0
                relaxed_lower_v = battery_v + rebound_credit

            verdict = self._guard.evaluate(time.monotonic(), battery_v, relaxed_lower_v, cutoff, emergency_floor)
            if verdict in TRIP_RESULTS and not self._cutoff_latched:
                _LOGGER.warning("ASC battery cutoff latched (%s): V=%s", verdict, battery_v)
                self._cutoff_latched = True
                state.hard_cutoff_latched = True
                await self.store.async_save(state)

            if not self._cutoff_latched:
                return verdict if verdict != OK else "ok"

            if not invalid_voltage and battery_v >= cutoff + 0.8 and current >= 0.5:
                self._cutoff_latched = False
                state.hard_cutoff_latched = False
                self._guard.reset()
                if self._cutoff_notified:
                    persistent_notification.async_dismiss(self.hass, "asc_cutoff_no_switch")
                    self._cutoff_notified = False
                await self.store.async_save(state)
                return "recovered_manual_reenable_if_needed"

            entity_id = self.cfg.get(CONF_INVERTER_POWER_SWITCH) or ""
            # An active battery safety latch has priority even if the control mode
            # was changed. Physical switch-off still requires a configured switch.
            if not self.controller.enabled:
                return "cutoff_controller_disabled"
            if not entity_id or entity_id == self.cfg.get(CONF_SOLAR_ENABLE):
                if not self._cutoff_notified:
                    _LOGGER.error("ASC cannot physically disconnect inverter: no dedicated power switch configured")
                    persistent_notification.async_create(
                        self.hass,
                        "Die Batterie-Abschaltgrenze wurde erreicht, aber es ist kein eigener "
                        "Inverter-Power-Schalter konfiguriert. ASC kann den Wechselrichter NICHT "
                        "abschalten (nur 30 W Minimum). Bitte Batterie/Inverter manuell prüfen.",
                        title="ASC: Batterieschutz ohne Schalter",
                        notification_id="asc_cutoff_no_switch",
                    )
                    self._cutoff_notified = True
                return "cutoff_no_dedicated_switch"
            st = self._state(entity_id)
            now = time.monotonic()
            sw = None if st is None else st.state
            if sw not in ("on", "off"):
                return "cutoff_switch_unavailable"
            observed = self._cutoff_off.observe(sw, now)
            if sw == "off":
                if observed == switch_confirm.CONFIRMED:
                    persistent_notification.async_dismiss(self.hass, "asc_switch_off_unconfirmed")
                    return "cutoff_switch_off_confirmed"
                return "cutoff_latched"
            if observed == switch_confirm.PENDING:
                return "cutoff_switch_off_pending"
            try:
                await self.hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
            except Exception:
                _LOGGER.exception("ASC hard cutoff switch-off failed")
                self._cutoff_off.sent(now)
                return "cutoff_switch_error"
            self._cutoff_off.sent(now)
            if self._cutoff_off.unconfirmed:
                persistent_notification.async_create(
                    self.hass,
                    f"Die Batterie-Abschaltgrenze wurde erreicht, aber der Schalter {entity_id} meldet nach "
                    f"{self._cutoff_off.attempts} Abschaltbefehlen weiter 'an'. Bitte den Wechselrichter "
                    "von Hand prüfen und abschalten.",
                    title="ASC: Abschaltung nicht bestätigt",
                    notification_id="asc_switch_off_unconfirmed",
                )
                return "cutoff_switch_off_unconfirmed"
            return "cutoff_switch_off_sent" if self._cutoff_off.attempts == 1 else "cutoff_switch_off_retry"

    async def _async_set_target(self, applied: float, current: float) -> None:
        """Write the inverter target helper, clamped to the helper's own min/max."""
        entity_id = self.cfg[CONF_TARGET_HELPER]
        value = float(round(applied))
        st = self._state(entity_id)
        if st is not None:
            try:
                lo = float(st.attributes.get("min", value))
                hi = float(st.attributes.get("max", value))
                value = max(lo, min(hi, value))
            except (TypeError, ValueError):
                pass
        value = int(round(value))
        if value == int(round(current)):
            return
        try:
            await self.hass.services.async_call(
                "input_number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
            )
        except Exception:
            _LOGGER.exception("ASC could not set %s to %s", entity_id, value)

    def _passive_pv_stats(self):
        s = self.controller.state
        today = dt_util.as_local(dt_util.utcnow()).date()
        key = (s.passive_pv_import_count, len(s.passive_pv_daily_kwh), today)
        if self._passive_cache and self._passive_cache[0] == key:
            return self._passive_cache[1]
        stats = (estimate(s.passive_pv_daily_kwh, today + timedelta(days=1)),
                 summary(s.passive_pv_daily_kwh, today)["theoretical_weight"])
        self._passive_cache = (key, stats)
        return stats

    async def _async_send_lock_off(self, entity_id: str, now: float) -> str:
        """Send turn_off for the FULL lock; repeat and alert while the switch stays on."""
        try:
            await self.hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
        except Exception:
            _LOGGER.exception("ASC could not turn off inverter %s", entity_id)
            return "turn_off_failed"
        self._lock_off.sent(now)
        if self._lock_off.unconfirmed:
            persistent_notification.async_create(
                self.hass,
                f"ASC hat {self._lock_off.attempts}-mal versucht, den Schalter {entity_id} für die FULL-Sperre "
                "abzuschalten, er meldet aber weiter 'an'. Bitte den Wechselrichter von Hand prüfen.",
                title="ASC: Abschaltung nicht bestätigt",
                notification_id="asc_switch_off_unconfirmed",
            )
            return "turn_off_unconfirmed"
        return "turn_off_sent" if self._lock_off.attempts == 1 else "turn_off_retry"

    async def _async_manage_full_lock(self, chemistry_state: str, mode: str) -> str:
        """Own only our own switch-off, never re-enable a manually off inverter."""
        state = self.controller.state
        entity_id = self.cfg.get(CONF_INVERTER_POWER_SWITCH) or ""
        owned = bool(state.inverter_full_lock_owned)
        previous_entity = state.inverter_full_lock_entity
        if not entity_id:
            return "not_configured"
        if entity_id == self.cfg.get(CONF_SOLAR_ENABLE):
            return "invalid_same_as_solar_enable"
        switch = self._state(entity_id)
        # The configured switch changed (or was renamed) while we own a lock: align the stored
        # ownership with the configured switch. Nothing is switched here, only the marker changes.
        if owned and previous_entity != entity_id:
            outcome, new_owned, new_entity = reconcile_lock_owner(
                owned, previous_entity, entity_id, None if switch is None else switch.state)
            if outcome in (ADOPTED, RELEASED):
                _LOGGER.warning("ASC FULL lock: switch changed from %r to %s (%s)", previous_entity, entity_id, outcome)
                state.inverter_full_lock_owned = new_owned
                state.inverter_full_lock_entity = new_entity
                await self.store.async_save(state)
                return outcome
            return PENDING
        if switch is None or switch.state not in ("on", "off"):
            return "switch_unavailable"
        # Monitor/Off is observational only, including release actions.
        if mode not in (MODE_ADAPTIVE, MODE_PREDICTIVE) or not self.controller.enabled:
            return "monitor_no_action"
        lock_required = self.controller.state.battery_chemistry == "lead_acid" and chemistry_state in ("lead_full_hold", "lead_full_emergency")
        if lock_required:
            now = time.monotonic()
            if owned:
                observed = self._lock_off.observe(switch.state, now)
                if switch.state == "on":
                    if observed == switch_confirm.IDLE:
                        # No open switch-off command of ours: someone switched it on manually.
                        state.inverter_full_lock_owned = False
                        state.inverter_full_lock_entity = ""
                        await self.store.async_save(state)
                        return "manual_override_on"
                    if observed == switch_confirm.PENDING:
                        return "turn_off_pending"
                    return await self._async_send_lock_off(entity_id, now)
                if observed == switch_confirm.CONFIRMED:
                    persistent_notification.async_dismiss(self.hass, "asc_switch_off_unconfirmed")
                    return "turn_off_confirmed"
                return "locked_off"
            if switch.state == "off":
                return "already_off_not_owned"
            # Persist ownership before the command so a restart cannot lose it.
            state.inverter_full_lock_owned = True
            state.inverter_full_lock_entity = entity_id
            await self.store.async_save(state)
            result = await self._async_send_lock_off(entity_id, now)
            if result == "turn_off_failed":
                state.inverter_full_lock_owned = False
                state.inverter_full_lock_entity = ""
                await self.store.async_save(state)
            return result
        if not owned:
            return "no_lock"
        if switch.state == "on":
            state.inverter_full_lock_owned = False
            state.inverter_full_lock_entity = ""
            await self.store.async_save(state)
            return "already_on_release"
        # Release ONLY on the confirmed post-FULL state; never on a plan/forecast change.
        if chemistry_state != "lead_post_full":
            return "awaiting_confirmed_full"
        full_ts = state.last_full_anchor_ts
        if not full_ts or time.time() - float(full_ts) < 3600:
            return "awaiting_confirmed_full"
        try:
            await self.hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
        except Exception:
            _LOGGER.exception("ASC could not turn on inverter %s", entity_id)
            return "turn_on_failed"
        state.inverter_full_lock_owned = False
        state.inverter_full_lock_entity = ""
        await self.store.async_save(state)
        return "turn_on_sent"

    def _measurement_spread_s(self) -> float:
        # v0.4.2.2+: battery-energy integration must never depend on the PV
        # entity timestamp (PV can remain unchanged at 0 W all night). V*A uses
        # only the synchronized battery voltage/current timestamps.
        states = [self._state(self.cfg.get(k)) for k in (CONF_BATTERY_VOLTAGE_SENSOR, CONF_BATTERY_CURRENT_SENSOR)]
        stamps = [st.last_updated.timestamp() for st in states if st is not None]
        return max(stamps) - min(stamps) if len(stamps) >= 2 else 999.0

    def _snapshot(self) -> PlantSnapshot:
        battery_v = self._float(CONF_BATTERY_VOLTAGE_SENSOR); battery_a = self._float(CONF_BATTERY_CURRENT_SENSOR)
        battery_w = self._float_entity(self.cfg.get(CONF_BATTERY_POWER_SENSOR), None)
        if battery_w is None: battery_w = battery_v * battery_a
        return PlantSnapshot(
            grid_w=self._float(CONF_GRID_SENSOR), pv_w=self._float(CONF_PV_SENSOR),
            daily_production_kwh=self._float_entity(self.cfg.get(CONF_DAILY_PRODUCTION_SENSOR), None),
            battery_v=battery_v, battery_a=battery_a, battery_w=float(battery_w),
            inverter_output_w=self._float(CONF_INVERTER_OUTPUT_SENSOR), target_w=self._float(CONF_TARGET_HELPER, DEFAULTS[CONF_MIN_TARGET_W]),
            battery_low_v=max(self.controller.state.hard_cutoff_voltage_v + 0.1, self._float(CONF_BATTERY_LOW_HELPER, 23.0)), backup_w=self._float(CONF_BACKUP_INVERTER),
            forecast_power_now_w=self._float_entity(self.cfg.get(CONF_FORECAST_POWER_NOW), None),
            forecast_power_next_hour_w=self._float_entity(self.cfg.get(CONF_FORECAST_POWER_NEXT_HOUR), None),
            forecast_energy_next_hour_kwh=self._float_entity(self.cfg.get(CONF_FORECAST_ENERGY_NEXT_HOUR), None),
            forecast_energy_today_kwh=self._float_entity(self.cfg.get(CONF_FORECAST_ENERGY_TODAY), None),
            forecast_energy_remaining_kwh=self._float_entity(self.cfg.get(CONF_FORECAST_ENERGY_REMAINING), None),
            forecast_energy_tomorrow_kwh=self._float_entity(self.cfg.get(CONF_FORECAST_ENERGY_TOMORROW), None),
            measurement_spread_s=self._measurement_spread_s(),
        )

    def _paused_data(self, reason: str, warmup: bool = False) -> dict:
        c=self.controller; s=c.state if c else None
        return {
            "status":"warmup" if warmup else "paused", "blocked_reason":reason, "blocked":True,
            "mode":c.mode if c else MODE_MONITOR, "recommended_w":None, "applied_w":None, "predicted_load_w":None,
            "current_load_w":None, "confidence":0.0, "prediction_maturity":"learning", "prediction_eval_samples":s.prediction_eval_samples if s else 0,
            "gain":round(s.gain,3) if s else 1.0, "effective_limit_w":None, "grid_error_w":None, "jump_detected":False,
            "jump_confidence":0.0, "jump_target_w":None, "raw_target_w":None, "response_learning_eligible":False,
            "saturation_reason":reason, "response_samples":s.response_samples if s else 0, "samples":s.samples if s else 0,
            "bucket_count":len(s.buckets) if s else 0, "solar_enabled":bool(warmup), "deadband_negative_w":None,
            "deadband_positive_w":None, "deadband_maturity":0.0, "minimum_useful_delta_w":None, "export_escalation":"none",
            "forecast_trust":0.0, "forecast_bias":s.forecast_bias_ema if s else 1.0, "forecast_reputation":"unknown",
            "corrected_forecast_remaining_kwh":None, "corrected_forecast_tomorrow_kwh":None, "seasonal_expected_today_kwh":None,
            "seasonal_expected_tomorrow_kwh":None, "seasonal_confidence":0.0, "seasonal_history_days":s.seasonal_history_days if s else 0,
            "battery_recovery_state":"paused", "battery_recovery_need":0.0, "battery_full_confidence":0.0,
            "learned_full_charge_voltage_v":s.learned_full_charge_voltage_v if s else None,
            "learned_full_transition_voltage_v":s.learned_full_transition_voltage_v if s else None,
            "battery_relaxation_drop_v":None, "transition_confidence":0.0, "energy_budget_kwh":s.energy_budget_kwh if s else 0.0,
            "energy_budget_state":"paused", "energy_budget_confidence":0.0, "expected_total_need_kwh":s.learned_total_gap_energy_kwh if s else 0.0,
            "learned_battery_gap_kwh":s.learned_battery_gap_energy_kwh if s else 0.0, "learned_grid_gap_kwh":s.learned_grid_gap_energy_kwh if s else 0.0,
            "current_gap_total_kwh":s.current_gap_total_kwh if s else 0.0, "battery_demand_confidence":0.0, "battery_reserve_fraction":None,
            "target_reserve_fraction":s.target_reserve_fraction*100.0 if s else None, "pv_charge_state":"unknown", "planner_reason":reason,
            "calibration_state":"off" if not s or not s.battery_calibration_enabled else "charging_to_full",
            "stored_energy_kwh":s.stored_energy_kwh if s and s.stored_energy_kwh >= 0 else None,
            "usable_capacity_kwh":s.usable_capacity_estimate_kwh if s and s.usable_capacity_estimate_kwh >= 0.5 else (s.battery_capacity_start_kwh if s else None),
            "capacity_confidence":min(100.0, (s.capacity_samples / 5.0) * 100.0) if s else 0.0,
            "energy_state_confidence":0.0, "energy_delta_kwh":0.0, "measurement_quality":"paused",
            "typical_gap_kwh":s.learned_total_gap_typical_kwh if s else 0.0, "recent_gap_kwh":s.learned_total_gap_recent_kwh if s else 0.0,
            "last_gap_classification":s.last_gap_classification if s else "unknown",
            "surplus_available":False, "available_surplus_power_w":0.0, "available_surplus_energy_kwh":0.0, "surplus_confidence":0.0,
            "battery_energy_charged_total_kwh":s.battery_energy_charged_total_kwh if s else 0.0,
            "battery_energy_discharged_total_kwh":s.battery_energy_discharged_total_kwh if s else 0.0,
            "hard_cutoff_voltage_v":s.hard_cutoff_voltage_v if s else 22.8,
            "hard_cutoff_status":self._last_cutoff_status, "flight_recorder_path":str(self.recorder.path), "events":"",
        }

    async def _async_update_data(self) -> dict:
        if self.controller is None: return {"status":"initializing","blocked_reason":"initializing"}
        # Battery protection first: also while paused, warming up or on invalid sensors.
        critical = self._critical_inputs()
        self._last_cutoff_status = await self._async_manage_cutoff(
            critical["battery_voltage"], critical["battery_current"], critical["inverter_output"])
        solar_enabled, release_error = self._solar_release()
        if not solar_enabled:
            if self._solar_was_enabled: self.controller.reset_transient()
            self._solar_was_enabled=False; self._warmup_pending=True
            return self._paused_data(release_error or "solar_release_off")
        missing = [k for k, v in critical.items() if v is None]
        if missing:
            self.controller.reset_transient()
            return self._paused_data("sensor_invalid:" + ",".join(missing))
        if not self._solar_was_enabled or self._warmup_pending:
            self._solar_was_enabled=True; self._warmup_pending=False; self.controller.reset_transient()
            return self._paused_data("warmup_after_enable", warmup=True)

        snap=self._snapshot(); now=datetime.now().astimezone()
        self.controller.battery.absorption_voltage_v = float(self.cfg[CONF_ABSORPTION_V])
        self.controller.battery.absorption_tolerance_v = float(self.cfg[CONF_ABSORPTION_TOLERANCE_V])
        self.controller.battery.absorption_minutes = float(self.cfg[CONF_ABSORPTION_MINUTES])
        had_full_cycle = bool(self.controller.state.full_cycle_active)
        old_capacity_kwh = self.controller.state.usable_capacity_estimate_kwh
        result=self.controller.calculate(snap, now, float(self.cfg[CONF_GRID_TARGET]), float(self.cfg[CONF_BACKUP_BLOCK_W]), float(self.cfg[CONF_MIN_TARGET_W]), float(self.cfg[CONF_MAX_STEP_W]), float(self.controller.state.inverter_max_power_w))

        new_capacity_kwh = self.controller.state.usable_capacity_estimate_kwh
        capacity_change_reason = ("valid_full_to_low_learning" if abs(new_capacity_kwh - old_capacity_kwh) > 0.00001 else "unchanged")
        cutoff_action = self._last_cutoff_status
        switch_action = ("cutoff_priority" if self._cutoff_latched else
                         await self._async_manage_full_lock(result.chemistry_strategy_state, result.mode))
        inverter_switch_entity = self.cfg.get(CONF_INVERTER_POWER_SWITCH) or ""
        inverter_switch_state = (self._state(inverter_switch_entity).state if self._state(inverter_switch_entity) else "not_configured")

        recovery_target = self._low_recovery_update(snap, result, now, had_full_cycle)
        if recovery_target is not None:
            # Targeted calibration may raise output only after FULL gating and
            # never above measured house demand or configured inverter maximum.
            recovery_target = max(30, min(int(recovery_target), int(self.controller.state.inverter_max_power_w)))
        applied_target = recovery_target if recovery_target is not None else result.applied_w
        if self._cutoff_latched:
            # Never command more power while below the hard cutoff. A switch
            # is required to enforce a true 0 W cutoff on hardware with 30 W floor.
            applied_target = 30 if result.mode in (MODE_ADAPTIVE, MODE_PREDICTIVE) else None
        if applied_target is not None:
            await self._async_set_target(applied_target, snap.target_w)

        if result.calibration_complete and self.controller.state.battery_calibration_enabled:
            self.controller.state.battery_calibration_enabled=False
            _LOGGER.info("ASC battery calibration completed automatically")

        absorption = self.controller.state
        absorption_elapsed = round(absorption.absorption_seconds / 60.0, 1)
        absorption_required = float(self.cfg[CONF_ABSORPTION_MINUTES])
        absorption_data = {
            "absorption_elapsed_min": absorption_elapsed,
            "absorption_required_min": absorption_required,
            "absorption_remaining_min": round(max(0.0, absorption_required - absorption_elapsed), 1),
            "absorption_status": absorption.absorption_status,
            "full_anchor_source": absorption.full_anchor_source,
        }
        data = {
            **absorption_data,
            "capacity_change_reason":capacity_change_reason,
            "hard_cutoff_voltage_v": self.controller.state.hard_cutoff_voltage_v,
            "hard_cutoff_status": cutoff_action,
            "inverter_power_switch": inverter_switch_entity, "inverter_switch_state": inverter_switch_state,
            "inverter_full_lock_owned": self.controller.state.inverter_full_lock_owned, "inverter_switch_action": switch_action,
            "status":"ok", "recommended_w":result.recommended_w, "applied_w":result.applied_w,
            "predicted_load_w":result.predicted_load_w, "current_load_w":result.current_load_w, "confidence":result.confidence,
            "prediction_maturity":result.prediction_maturity, "prediction_eval_samples":result.prediction_eval_samples, "gain":result.gain,
            "effective_limit_w":result.effective_limit_w, "blocked":result.blocked, "blocked_reason":result.blocked_reason, "mode":result.mode,
            "grid_error_w":result.grid_error_w, "jump_detected":result.jump_detected, "jump_confidence":result.jump_confidence,
            "jump_target_w":result.jump_target_w, "raw_target_w":result.raw_target_w, "response_learning_eligible":result.response_learning_eligible,
            "saturation_reason":result.saturation_reason, "response_samples":self.controller.state.response_samples, "samples":self.controller.state.samples,
            "bucket_count":len(self.controller.state.buckets), "solar_enabled":True, "deadband_negative_w":result.deadband_negative_w,
            "deadband_positive_w":result.deadband_positive_w, "deadband_maturity":result.deadband_maturity,
            "minimum_useful_delta_w":result.minimum_useful_delta_w, "export_escalation":result.export_escalation,
            "forecast_trust":result.forecast_trust, "forecast_bias":result.forecast_bias, "forecast_reputation":result.forecast_reputation,
            "corrected_forecast_remaining_kwh":result.corrected_forecast_remaining_kwh, "corrected_forecast_tomorrow_kwh":result.corrected_forecast_tomorrow_kwh,
            "seasonal_expected_today_kwh":result.seasonal_expected_today_kwh, "seasonal_expected_tomorrow_kwh":result.seasonal_expected_tomorrow_kwh,
            "seasonal_confidence":result.seasonal_confidence, "seasonal_history_days":self.controller.state.seasonal_history_days,
            "inverter_max_power_w":self.controller.state.inverter_max_power_w,
            "low_recovery_mode":self.controller.state.low_recovery_mode,
            "low_recovery_status":self.controller.state.low_recovery_last_status,
            "low_recovery_runs":len(self.controller.state.low_recovery_runs),
            "low_recovery_step":(self._low_recovery_session["step"] + 1) if self._low_recovery_session else 0,
            "low_recovery_phase":self._low_recovery_session["phase"] if self._low_recovery_session else "idle",
            "low_recovery_remaining_s":max(0, int((480 if self._low_recovery_session["phase"] == "relaxation" else 120) - (now.timestamp() - self._low_recovery_session["phase_start"]))) if self._low_recovery_session and self._low_recovery_session["phase"] != "approach" else 0,
            "rebound_valid_bins":self.controller.state.rebound_learning_model.get("valid_bins",0),
            "rebound_predicted_sag_v":predicted_sag(self.controller.state.rebound_learning_model, snap.inverter_output_w),
            "battery_recovery_state":result.battery_recovery_state, "battery_recovery_need":result.battery_recovery_need,
            "battery_full_confidence":result.battery_full_confidence, "learned_full_charge_voltage_v":result.learned_full_charge_voltage_v,
            "learned_full_transition_voltage_v":result.learned_full_transition_voltage_v, "battery_relaxation_drop_v":result.battery_relaxation_drop_v,
            "transition_confidence":result.transition_confidence, "energy_budget_kwh":result.energy_budget_kwh, "energy_budget_state":result.energy_budget_state,
            "energy_budget_confidence":result.energy_budget_confidence, "expected_total_need_kwh":result.expected_total_need_kwh,
            "learned_battery_gap_kwh":result.learned_battery_gap_kwh, "learned_grid_gap_kwh":result.learned_grid_gap_kwh,
            "current_gap_total_kwh":result.current_gap_total_kwh, "battery_demand_confidence":result.battery_demand_confidence,
            "battery_reserve_fraction":result.battery_reserve_fraction, "target_reserve_fraction":result.target_reserve_fraction,
            "pv_charge_state":result.pv_charge_state, "planner_reason":result.planner_reason, "calibration_state":result.calibration_state,
            "stored_energy_kwh":result.stored_energy_kwh, "usable_capacity_kwh":result.usable_capacity_kwh,
            "capacity_confidence":result.capacity_confidence, "energy_state_confidence":result.energy_state_confidence,
            "energy_delta_kwh":result.energy_delta_kwh, "measurement_quality":result.measurement_quality,
            "typical_gap_kwh":result.typical_gap_kwh, "recent_gap_kwh":result.recent_gap_kwh,
            "last_gap_classification":result.last_gap_classification, "surplus_available":result.surplus_available,
            "available_surplus_power_w":result.available_surplus_power_w, "available_surplus_energy_kwh":result.available_surplus_energy_kwh,
            "surplus_confidence":result.surplus_confidence,
            "battery_chemistry":result.battery_chemistry, "progressive_gamma":result.progressive_gamma,
            "progressive_release_factor":result.progressive_release_factor, "battery_power_envelope_w":result.battery_power_envelope_w,
            "power_envelope_confidence":result.power_envelope_confidence, "planning_confidence":result.planning_confidence,
            "planning_reserve_adjustment":result.planning_reserve_adjustment, "planner_evaluation":result.planner_evaluation,
            "horizon_24h_balance_kwh":result.horizon_24h_balance_kwh, "horizon_48h_balance_kwh":result.horizon_48h_balance_kwh,
            "horizon_72h_balance_kwh":result.horizon_72h_balance_kwh,
            "full_charge_priority":result.full_charge_priority, "full_charge_opportunity":result.full_charge_opportunity,
            "chemistry_strategy_state":result.chemistry_strategy_state, "days_since_full":result.days_since_full,
            "battery_energy_charged_total_kwh":self.controller.state.battery_energy_charged_total_kwh,
            "battery_energy_discharged_total_kwh":self.controller.state.battery_energy_discharged_total_kwh,
            "actual_pv_today_kwh":snap.daily_production_kwh,
            "corrected_forecast_today_total_kwh":None if snap.daily_production_kwh is None or result.corrected_forecast_remaining_kwh is None else round(snap.daily_production_kwh + result.corrected_forecast_remaining_kwh,3),
            "flight_recorder_path":str(self.recorder.path), "events":",".join(result.events),
        }

        if self.controller.state.flight_recorder_enabled:
            await self.recorder.async_append({
                **absorption_data,
                "timestamp":now.isoformat(), "events":"|".join(result.events),
                "capacity_previous_kwh":round(old_capacity_kwh,3),
                "capacity_current_kwh":round(new_capacity_kwh,3),
                "capacity_change_reason":capacity_change_reason,
                "hard_cutoff_voltage_v":self.controller.state.hard_cutoff_voltage_v,
                "hard_cutoff_status":cutoff_action, "grid_w":snap.grid_w, "pv_w":snap.pv_w,
                "battery_v":snap.battery_v, "battery_a":snap.battery_a, "battery_w":snap.battery_w, "inverter_output_w":snap.inverter_output_w,
                "target_w":snap.target_w, "recommended_w":result.recommended_w, "applied_w":result.applied_w, "raw_target_w":result.raw_target_w,
                "effective_limit_w":result.effective_limit_w, "grid_error_w":result.grid_error_w, "predicted_load_w":result.predicted_load_w,
                "prediction_confidence":result.confidence, "response_gain":result.gain, "deadband_export_w":result.deadband_negative_w,
                "deadband_import_w":result.deadband_positive_w, "export_escalation":result.export_escalation, "forecast_trust":result.forecast_trust,
                "forecast_bias":result.forecast_bias, "corrected_remaining_kwh":result.corrected_forecast_remaining_kwh,
                "corrected_tomorrow_kwh":result.corrected_forecast_tomorrow_kwh, "seasonal_today_kwh":result.seasonal_expected_today_kwh,
                "seasonal_tomorrow_kwh":result.seasonal_expected_tomorrow_kwh, "seasonal_confidence":result.seasonal_confidence,
                "seasonal_history_days":self.controller.state.seasonal_history_days,
                "seasonal_history_coverage":round(min(1.0,self.controller.state.seasonal_history_days / 1100),4),
                "passive_pv_days":len(self.controller.state.passive_pv_daily_kwh),
                "passive_pv_expected_tomorrow_kwh":self._passive_pv_stats()[0],
                "passive_pv_theoretical_weight":self._passive_pv_stats()[1],
                "passive_pv_active_weight":0.0,
                "seasonal_week_samples":sum(float(v.get("count",0)) for v in self.controller.state.seasonal_buckets.values()),
                "seasonal_forecast_weight":round(max(0.05,result.seasonal_confidence*0.75)/(max(0.05,result.seasonal_confidence*0.75)+max(0.05,result.forecast_trust)),4) if result.seasonal_expected_tomorrow_kwh is not None and result.corrected_forecast_tomorrow_kwh is not None else (1.0 if result.seasonal_expected_tomorrow_kwh is not None else 0.0),
                "inverter_max_power_w":self.controller.state.inverter_max_power_w,
                "low_recovery_mode":self.controller.state.low_recovery_mode,
                "low_recovery_status":self.controller.state.low_recovery_last_status,
                "low_recovery_step":(self._low_recovery_session["step"]+1) if self._low_recovery_session else 0,
                "low_recovery_phase":self._low_recovery_session["phase"] if self._low_recovery_session else "idle",
                "rebound_valid_bins":self.controller.state.rebound_learning_model.get("valid_bins",0),
                "low_recovery_runs":len(self.controller.state.low_recovery_runs),
                "low_recovery_full_ts":self.controller.state.low_recovery_last_full_ts,
                "full_charge_v":result.learned_full_charge_voltage_v, "full_transition_v":result.learned_full_transition_voltage_v,
                "relaxation_drop_v":result.battery_relaxation_drop_v, "full_confidence":result.battery_full_confidence,
                "transition_confidence":result.transition_confidence, "battery_reserve":result.battery_reserve_fraction,
                "target_reserve":result.target_reserve_fraction, "learned_total_need_kwh":result.expected_total_need_kwh,
                "learned_battery_gap_kwh":result.learned_battery_gap_kwh, "learned_grid_gap_kwh":result.learned_grid_gap_kwh,
                "current_gap_total_kwh":result.current_gap_total_kwh, "demand_confidence":result.battery_demand_confidence,
                "energy_budget_kwh":result.energy_budget_kwh, "energy_budget_state":result.energy_budget_state,
                "energy_budget_confidence":result.energy_budget_confidence, "planner_reason":result.planner_reason,
                "pv_charge_state":result.pv_charge_state, "recovery_state":result.battery_recovery_state, "recovery_need":result.battery_recovery_need,
                "stored_energy_kwh":result.stored_energy_kwh, "usable_capacity_kwh":result.usable_capacity_kwh,
                "capacity_confidence":result.capacity_confidence, "energy_state_confidence":result.energy_state_confidence,
                "energy_delta_kwh":result.energy_delta_kwh, "measurement_quality":result.measurement_quality,
                "typical_gap_kwh":result.typical_gap_kwh, "recent_gap_kwh":result.recent_gap_kwh,
                "gap_classification":result.last_gap_classification, "surplus_available":result.surplus_available,
                "surplus_power_w":result.available_surplus_power_w, "surplus_energy_kwh":result.available_surplus_energy_kwh,
                "surplus_confidence":result.surplus_confidence, "measurement_spread_s":snap.measurement_spread_s,
                "battery_chemistry":result.battery_chemistry, "progressive_gamma":result.progressive_gamma,
                "progressive_release_factor":result.progressive_release_factor, "battery_power_envelope_w":result.battery_power_envelope_w,
                "power_envelope_confidence":result.power_envelope_confidence, "planning_confidence":result.planning_confidence,
                "planning_reserve_adjustment":result.planning_reserve_adjustment, "planner_evaluation":result.planner_evaluation,
                "horizon_24h_balance_kwh":result.horizon_24h_balance_kwh, "horizon_48h_balance_kwh":result.horizon_48h_balance_kwh,
                "horizon_72h_balance_kwh":result.horizon_72h_balance_kwh,
                "full_charge_priority":result.full_charge_priority, "full_charge_opportunity":result.full_charge_opportunity,
                "chemistry_strategy_state":result.chemistry_strategy_state, "days_since_full":result.days_since_full,
                "calibration_state":result.calibration_state, "blocked_reason":result.blocked_reason,
                "hard_cutoff_voltage_v":self.controller.state.hard_cutoff_voltage_v,
            "hard_cutoff_status":cutoff_action,
            "inverter_power_switch":inverter_switch_entity, "inverter_switch_state":inverter_switch_state,
                "inverter_full_lock_owned":self.controller.state.inverter_full_lock_owned, "inverter_switch_action":switch_action,
            })

        self._cycles_since_save += 1
        if self._cycles_since_save >= 20 or result.calibration_complete or capacity_change_reason != "unchanged" or cutoff_action == "cutoff_switch_off_sent":
            self._cycles_since_save=0; await self.store.async_save(self.controller.state)
        return data
