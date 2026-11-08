from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from .storage import LearningState
from .rebound_learning import predicted_sag


@dataclass
class BatteryEstimate:
    full_charge_voltage_v: float
    full_transition_voltage_v: float
    relaxation_drop_v: float
    full_confidence: float
    transition_confidence: float
    reserve_fraction: float
    recovery_need: float
    recovery_state: str
    learned_total_gap_kwh: float
    learned_battery_gap_kwh: float
    learned_grid_gap_kwh: float
    current_gap_total_kwh: float
    demand_confidence: float
    pv_charge_state: str
    calibration_state: str
    calibration_complete: bool
    stored_energy_kwh: float
    usable_capacity_kwh: float
    capacity_confidence: float
    energy_state_confidence: float
    energy_delta_kwh: float
    measurement_quality: str
    typical_gap_kwh: float
    recent_gap_kwh: float
    last_gap_classification: str
    events: tuple[str, ...]


class BatteryEstimator:
    """ASC v0.4.2 energy-state battery estimator.

    Battery state is primarily integrated energy (V*A*dt). Voltage is retained as
    a full/low calibration and plausibility signal, never as a continuously direct
    SOC mapping while charge current raises terminal voltage.
    """

    START_PV_W = 180.0
    START_BATTERY_A = 1.0
    STOP_PV_W = 100.0
    STOP_BATTERY_A = 0.2
    START_CONFIRM_S = 120.0
    STOP_CONFIRM_S = 180.0
    MIN_GAP_S = 3 * 3600.0
    MIN_GAP_KWH = 0.08
    MAX_ENERGY_DT_S = 45.0
    GOOD_MEASUREMENT_SPREAD_S = 5.0
    RELAXED_CURRENT_A = 0.8
    RELAXED_CONFIRM_S = 600.0
    LOW_ANCHOR_MARGIN_V = 0.25
    LOW_ANCHOR_CONFIRM_S = 90.0
    LOW_ANCHOR_RELEASE_MARGIN_V = 0.55
    LOW_ANCHOR_RELEASE_CONFIRM_S = 180.0

    def __init__(self, state: LearningState) -> None:
        self.state = state
        self.absorption_voltage_v = 29.4
        self.absorption_tolerance_v = 0.4
        self.absorption_minutes = 120.0

    def observe(
        self,
        *,
        now: datetime,
        battery_v: float,
        battery_a: float,
        battery_w: float,
        pv_w: float,
        grid_w: float,
        inverter_output_w: float,
        hard_low_v: float,
        calibration_enabled: bool,
        measurement_spread_s: float = 0.0,
    ) -> BatteryEstimate:
        values = (battery_v, battery_a, battery_w, pv_w, grid_w, inverter_output_w, hard_low_v, measurement_spread_s)
        if not all(math.isfinite(v) for v in values):
            return self._fallback(hard_low_v, calibration_enabled)

        events: list[str] = []
        dt = self._dt(now)
        quality_ok = measurement_spread_s <= self.GOOD_MEASUREMENT_SPREAD_S and 0.0 <= dt <= self.MAX_ENERGY_DT_S
        measurement_quality = "synced" if quality_ok else "degraded"

        if self.state.battery_recent_min_v > 60.0:
            self.state.battery_recent_min_v = battery_v
        elif battery_v < self.state.battery_recent_min_v:
            self.state.battery_recent_min_v = battery_v
        else:
            self.state.battery_recent_min_v = min(battery_v, self.state.battery_recent_min_v + dt * 0.00003)

        self._update_charge_state(dt, battery_a, pv_w, events)
        self._integrate_gap(dt, battery_w, grid_w, inverter_output_w)
        self._learn_full_charge(dt, battery_v, battery_a, pv_w, hard_low_v, events)
        if self.state.battery_chemistry == "lead_acid":
            self._observe_absorption(now, dt, battery_v, battery_a, quality_ok, events)

        capacity = self._effective_capacity()
        self._bootstrap_energy_if_needed(battery_v, battery_a, hard_low_v, capacity)
        energy_delta = self._integrate_energy(dt, battery_v, battery_a, capacity, quality_ok)

        if "BATTERY_FULL_DETECTED" in events:
            self.state.full_anchor_source = "absorption_time" if "FULL_BY_ABSORPTION_TIME" in events else "voltage_current"
            self.state.absorption_seconds = 0.0
            self.state.absorption_started = False
            self.state.absorption_status = "full_confirmed"
            self.state.absorption_last_qualifying_ts = None
            self.state.stored_energy_kwh = capacity
            self.state.energy_anchor_seen = True
            self.state.full_cycle_active = True
            self.state.discharge_since_full_kwh = 0.0
            self.state.energy_anchor_samples += 1
            self.state.last_full_anchor_ts = now.timestamp()
            self.state.lead_full_priority = 0.0
            self.state.lead_full_opportunity = "fulfilled"
            self.state.lead_strategy_state = "full_reached"
            events.append("ENERGY_FULL_ANCHOR")

        capacity_changed = self._learn_low_anchor(dt, battery_v, battery_a, inverter_output_w, hard_low_v, quality_ok, events)
        if capacity_changed:
            capacity = self._effective_capacity()

        self._passive_voltage_plausibility(dt, battery_v, battery_a, hard_low_v, capacity, quality_ok)

        calibration_complete = self._learn_transition(
            dt, battery_v, battery_a, pv_w, hard_low_v, calibration_enabled, events
        )

        full_charge_v = max(hard_low_v + 1.0, self.state.learned_full_charge_voltage_v)
        transition_v = max(hard_low_v + 0.6, min(full_charge_v, self.state.learned_full_transition_voltage_v))
        capacity = self._effective_capacity()
        stored = max(0.0, min(capacity, self.state.stored_energy_kwh if self.state.stored_energy_kwh >= 0 else 0.0))
        reserve = stored / max(0.5, capacity)

        full_conf = self._full_confidence(battery_v, battery_a, full_charge_v, transition_v, hard_low_v)
        transition_conf = min(1.0, self.state.full_transition_samples / 4.0)
        demand_conf = min(1.0, self.state.total_gap_samples / 6.0)
        capacity_conf = min(1.0, self.state.capacity_samples / 5.0)
        anchor_conf = min(1.0, self.state.energy_anchor_samples / 3.0)
        integration_conf = min(1.0, self.state.energy_integrated_seconds / (12 * 3600.0))
        energy_conf = min(1.0, anchor_conf * 0.60 + integration_conf * 0.25 + capacity_conf * 0.15)
        if not self.state.energy_anchor_seen:
            energy_conf = min(0.20, energy_conf)
        if not quality_ok:
            energy_conf *= 0.90

        # Energy reserve drives recovery. Voltage only adds a hard-low warning.
        target_floor = 0.15
        reserve_recovery = max(0.0, min(1.0, (target_floor - reserve) / target_floor))
        low_voltage_warning = max(0.0, min(1.0, (hard_low_v + 0.45 - battery_v) / 0.45)) if battery_a < -0.3 else 0.0
        recovery_need = max(reserve_recovery, low_voltage_warning)
        recovery_state = "strong_recovery" if recovery_need >= 0.70 else "recovery" if recovery_need >= 0.35 else "normal"

        if calibration_enabled:
            if self.state.calibration_full_seen and self.state.transition_capture_active:
                calibration_state = "learning_transition"
            elif self.state.calibration_full_seen:
                calibration_state = "waiting_for_discharge"
            else:
                calibration_state = "charging_to_full"
        else:
            calibration_state = "off"

        return BatteryEstimate(
            full_charge_voltage_v=round(full_charge_v, 2),
            full_transition_voltage_v=round(transition_v, 2),
            relaxation_drop_v=round(max(0.0, full_charge_v - transition_v), 2),
            full_confidence=full_conf,
            transition_confidence=transition_conf,
            reserve_fraction=max(0.0, min(1.0, reserve)),
            recovery_need=recovery_need,
            recovery_state=recovery_state,
            learned_total_gap_kwh=round(self.state.learned_total_gap_energy_kwh, 3),
            learned_battery_gap_kwh=round(self.state.learned_battery_gap_energy_kwh, 3),
            learned_grid_gap_kwh=round(self.state.learned_grid_gap_energy_kwh, 3),
            current_gap_total_kwh=round(self.state.current_gap_total_kwh, 3),
            demand_confidence=demand_conf,
            pv_charge_state="charging" if self.state.pv_charge_active else "gap",
            calibration_state=calibration_state,
            calibration_complete=calibration_complete,
            stored_energy_kwh=round(stored, 3),
            usable_capacity_kwh=round(capacity, 3),
            capacity_confidence=capacity_conf,
            energy_state_confidence=energy_conf,
            energy_delta_kwh=round(energy_delta, 5),
            measurement_quality=measurement_quality,
            typical_gap_kwh=round(self.state.learned_total_gap_typical_kwh, 3),
            recent_gap_kwh=round(self.state.learned_total_gap_recent_kwh, 3),
            last_gap_classification=self.state.last_gap_classification,
            events=tuple(events),
        )

    def _effective_capacity(self) -> float:
        learned = self.state.usable_capacity_estimate_kwh
        return max(0.5, learned if learned >= 0.5 else self.state.battery_capacity_start_kwh)

    def _dt(self, now: datetime) -> float:
        ts = now.timestamp()
        if self.state.battery_last_ts is None:
            self.state.battery_last_ts = ts
            return 0.0
        dt = max(0.0, min(90.0, ts - self.state.battery_last_ts))
        self.state.battery_last_ts = ts
        return dt

    def _bootstrap_energy_if_needed(self, battery_v: float, battery_a: float, hard_low_v: float, capacity: float) -> None:
        if self.state.stored_energy_kwh >= 0.0:
            return
        transition = max(hard_low_v + 0.6, self.state.learned_full_transition_voltage_v)
        voltage_fraction = max(0.0, min(1.0, (battery_v - hard_low_v) / max(0.6, transition - hard_low_v)))
        # Only a startup estimate until a real full anchor exists. Charging voltage
        # is explicitly prevented from producing the v0.4.1 90-100% illusion.
        if battery_a > 0.5:
            voltage_fraction = min(0.65, voltage_fraction)
        self.state.stored_energy_kwh = capacity * voltage_fraction

    def _integrate_energy(self, dt: float, battery_v: float, battery_a: float, capacity: float, quality_ok: bool) -> float:
        if dt <= 0.0 or not quality_ok:
            self.state.energy_rejected_samples += 1
            return 0.0
        delta = battery_v * battery_a * dt / 3_600_000.0
        # Persistent lifetime counters for Home Assistant Energy Dashboard.
        # They use exactly the same accepted V*A*dt samples as Stored Energy,
        # but are never clamped and never reset by battery learning.
        if delta > 0.0:
            self.state.battery_energy_charged_total_kwh += delta
        elif delta < 0.0:
            self.state.battery_energy_discharged_total_kwh += -delta
        before = self.state.stored_energy_kwh
        self.state.stored_energy_kwh = max(0.0, min(capacity, before + delta))
        actual_delta = self.state.stored_energy_kwh - before
        self.state.energy_integrated_seconds += dt
        self.state.energy_integrated_kwh += abs(delta)
        # Capacity learning must keep counting physical discharge even if the
        # provisional stored-energy estimate already hit zero. This is how an
        # underestimated start capacity can learn upward.
        if delta < 0.0 and self.state.full_cycle_active:
            self.state.discharge_since_full_kwh += -delta
        return actual_delta

    def _learn_low_anchor(self, dt: float, battery_v: float, battery_a: float, inverter_output_w: float, hard_low_v: float, quality_ok: bool, events: list[str]) -> bool:
        # A low anchor is a state transition, not an event that may retrigger
        # every controller cycle. Release the latch only after sustained, real
        # voltage recovery (or charging), so load-induced voltage bounce cannot
        # create a 30 W / higher-limit oscillation.
        if self.state.low_anchor_latched:
            recovered = quality_ok and (
                battery_a >= 0.5 or battery_v >= hard_low_v + self.LOW_ANCHOR_RELEASE_MARGIN_V
            )
            if recovered:
                self.state.low_anchor_release_seconds += dt
            else:
                self.state.low_anchor_release_seconds = max(0.0, self.state.low_anchor_release_seconds - dt)
            if self.state.low_anchor_release_seconds >= self.LOW_ANCHOR_RELEASE_CONFIRM_S:
                self.state.low_anchor_latched = False
                self.state.low_anchor_release_seconds = 0.0
                self.state.low_anchor_hold_seconds = 0.0
            return False

        low = quality_ok and battery_a <= -0.5 and battery_v <= hard_low_v + self.LOW_ANCHOR_MARGIN_V
        if low:
            self.state.low_anchor_hold_seconds += dt
        else:
            self.state.low_anchor_hold_seconds = max(0.0, self.state.low_anchor_hold_seconds - dt * 2.0)
        if self.state.low_anchor_hold_seconds < self.LOW_ANCHOR_CONFIRM_S:
            return False

        # Only a confirmed FULL->LOW cycle may establish an energy anchor.
        # The terminal voltage under load alone is not a capacity measurement.
        if not self.state.full_cycle_active or self.state.last_full_anchor_ts is None:
            self.state.low_anchor_hold_seconds = 0.0
            events.append("LOW_ANCHOR_REJECTED_NO_FULL")
            return False
        # The imported rebound curve is provisional. Use only a conservative
        # lower estimate of the relaxed voltage for anchor confirmation.
        sag = predicted_sag(self.state.rebound_learning_model, max(0.0, inverter_output_w))
        if sag is None:
            self.state.low_anchor_hold_seconds = 0.0
            events.append("LOW_ANCHOR_REJECTED_NO_REBOUND")
            return False
        relaxed_lower_v = battery_v + max(0.0, sag - 0.20)
        if relaxed_lower_v > hard_low_v:
            self.state.low_anchor_hold_seconds = 0.0
            events.append("LOW_ANCHOR_REJECTED_LOAD_SAG")
            return False
        self.state.stored_energy_kwh = 0.0
        self.state.low_anchor_latched = True
        self.state.low_anchor_release_seconds = 0.0
        self.state.energy_anchor_seen = True
        self.state.energy_anchor_samples += 1
        events.append("ENERGY_LOW_ANCHOR")
        changed = False
        if self.state.full_cycle_active and self.state.discharge_since_full_kwh >= 0.5:
            sample = self.state.discharge_since_full_kwh
            old = self._effective_capacity()
            if self.state.capacity_samples < 2:
                alpha = 0.40
            elif sample < old:
                alpha = 0.24  # capacity loss is safety relevant: accept faster
            else:
                alpha = 0.12  # capacity gain requires repeated confirmation
            learned = old + alpha * (sample - old)
            self.state.usable_capacity_estimate_kwh = max(0.5, min(60.0, learned))
            self.state.capacity_samples += 1
            self.state.last_capacity_sample_kwh = sample
            events.append("USABLE_CAPACITY_LEARNED")
            changed = True
        self.state.full_cycle_active = False
        self.state.discharge_since_full_kwh = 0.0
        self.state.low_anchor_hold_seconds = 0.0
        return changed

    def _passive_voltage_plausibility(self, dt: float, battery_v: float, battery_a: float, hard_low_v: float, capacity: float, quality_ok: bool) -> None:
        if quality_ok and abs(battery_a) <= self.RELAXED_CURRENT_A:
            self.state.relaxed_hold_seconds += dt
        else:
            self.state.relaxed_hold_seconds = 0.0
        if self.state.relaxed_hold_seconds < self.RELAXED_CONFIRM_S or not self.state.energy_anchor_seen:
            return
        transition = max(hard_low_v + 0.6, self.state.learned_full_transition_voltage_v)
        voltage_fraction = max(0.0, min(1.0, (battery_v - hard_low_v) / max(0.6, transition - hard_low_v)))
        energy_fraction = self.state.stored_energy_kwh / max(0.5, capacity)
        error = voltage_fraction - energy_fraction
        # Tiny drift correction only after 10 minutes near zero current. This
        # cannot recreate the old charge-current voltage bias.
        correction = max(-0.01, min(0.01, error * 0.02)) * capacity
        self.state.stored_energy_kwh = max(0.0, min(capacity, self.state.stored_energy_kwh + correction))

    def _update_charge_state(self, dt: float, battery_a: float, pv_w: float, events: list[str]) -> None:
        start_ok = pv_w >= self.START_PV_W and battery_a >= self.START_BATTERY_A
        stop_ok = pv_w <= self.STOP_PV_W or battery_a <= self.STOP_BATTERY_A
        if start_ok:
            self.state.pv_charge_on_seconds += dt
        else:
            self.state.pv_charge_on_seconds = max(0.0, self.state.pv_charge_on_seconds - dt * 1.5)
        if stop_ok:
            self.state.pv_charge_off_seconds += dt
        else:
            self.state.pv_charge_off_seconds = 0.0
        if not self.state.pv_charge_active and self.state.pv_charge_on_seconds >= self.START_CONFIRM_S:
            self.state.pv_charge_active = True
            self.state.pv_charge_off_seconds = 0.0
            events.append("PV_CHARGE_START")
            self._learn_partial_capacity_lower_bound(events)
            self._finish_gap(events)
        elif self.state.pv_charge_active and self.state.pv_charge_off_seconds >= self.STOP_CONFIRM_S:
            self.state.pv_charge_active = False
            self.state.pv_charge_on_seconds = 0.0
            self._start_gap()
            events.append("PV_CHARGE_END")


    def _learn_partial_capacity_lower_bound(self, events: list[str]) -> None:
        """Use incomplete full->charge cycles only as a conservative lower bound.

        A partial cycle cannot prove that capacity is smaller, but if measured
        discharge already exceeds the current estimate it can safely nudge it up.
        """
        if not self.state.full_cycle_active or self.state.discharge_since_full_kwh < 0.5:
            return
        sample = self.state.discharge_since_full_kwh
        old = self._effective_capacity()
        if sample > old * 1.03:
            self.state.usable_capacity_estimate_kwh = min(60.0, old + 0.05 * (sample - old))
            self.state.last_capacity_sample_kwh = sample
            events.append("PARTIAL_CAPACITY_LOWER_BOUND")
        self.state.full_cycle_active = False
        self.state.discharge_since_full_kwh = 0.0

    def _start_gap(self) -> None:
        self.state.current_gap_duration_s = 0.0
        self.state.current_gap_total_kwh = 0.0
        self.state.current_gap_battery_kwh = 0.0
        self.state.current_gap_grid_kwh = 0.0
        self.state.gap_start_reserve_fraction = None

    def _integrate_gap(self, dt: float, battery_w: float, grid_w: float, inverter_output_w: float) -> None:
        if dt <= 0 or self.state.pv_charge_active:
            return
        house_w = max(0.0, inverter_output_w + grid_w)
        self.state.current_gap_duration_s += dt
        self.state.current_gap_total_kwh += house_w * dt / 3_600_000.0
        self.state.current_gap_battery_kwh += max(0.0, -battery_w) * dt / 3_600_000.0
        self.state.current_gap_grid_kwh += max(0.0, grid_w) * dt / 3_600_000.0

    def _finish_gap(self, events: list[str]) -> None:
        if self.state.current_gap_duration_s < self.MIN_GAP_S or self.state.current_gap_total_kwh < self.MIN_GAP_KWH:
            self._start_gap(); return
        sample = self.state.current_gap_total_kwh
        typical_current = self.state.learned_total_gap_typical_kwh
        ratio = sample / typical_current if typical_current > 0.2 else 1.0
        extraordinary = self.state.total_gap_samples >= 2 and ratio >= 1.55
        self.state.last_gap_classification = "extraordinary" if extraordinary else "typical"
        if extraordinary:
            self.state.extraordinary_gap_samples += 1
            events.append("EXTRAORDINARY_LOAD_GAP")

        recent_alpha = 0.45 if self.state.total_gap_samples < 3 else 0.28
        self.state.learned_total_gap_recent_kwh = self._ema(self.state.learned_total_gap_recent_kwh, sample, recent_alpha, self.state.total_gap_samples)
        typical_alpha = 0.28 if self.state.total_gap_samples < 3 else (0.04 if extraordinary else 0.12)
        typical_sample = sample
        if extraordinary and typical_current > 0.2:
            typical_sample = min(sample, typical_current * 1.15)
        self.state.learned_total_gap_typical_kwh = self._ema(typical_current, typical_sample, typical_alpha, self.state.total_gap_samples)
        self.state.learned_total_gap_energy_kwh = self.state.learned_total_gap_typical_kwh * 0.75 + self.state.learned_total_gap_recent_kwh * 0.25
        alpha = 0.35 if self.state.total_gap_samples < 3 else (0.08 if extraordinary else 0.18)
        self.state.learned_battery_gap_energy_kwh = self._ema(self.state.learned_battery_gap_energy_kwh, self.state.current_gap_battery_kwh, alpha, self.state.total_gap_samples)
        self.state.learned_grid_gap_energy_kwh = self._ema(self.state.learned_grid_gap_energy_kwh, self.state.current_gap_grid_kwh, alpha, self.state.total_gap_samples)
        self.state.total_gap_samples += 1
        self.state.last_completed_gap_total_kwh = self.state.current_gap_total_kwh
        self.state.last_completed_gap_battery_kwh = self.state.current_gap_battery_kwh
        self.state.last_completed_gap_grid_kwh = self.state.current_gap_grid_kwh
        events.append("GAP_ENERGY_LEARNED")
        self._start_gap()

    @staticmethod
    def _ema(current: float, sample: float, alpha: float, samples: int) -> float:
        return sample if samples <= 0 or current <= 0.0 else current + alpha * (sample - current)

    def _observe_absorption(self, now: datetime, dt: float, voltage: float, current: float,
                            quality_ok: bool, events: list[str]) -> None:
        """Conservative, cumulative lead absorption clock; never changes EPEVER charging.

        The 0.4 V tolerance is a *counting band*, not an instrument calibration.
        Require actual positive charge, valid synchronized samples, and first entry
        at the configured absorption voltage. Pause on short cloud interruptions;
        discard stale time after 8 h without qualifying absorption voltage.
        """
        state = self.state
        ts = now.timestamp()
        # Avoid a second FULL anchor during the 24 h post-FULL lockout.
        if state.last_full_anchor_ts is not None and 0 <= ts - state.last_full_anchor_ts < 24 * 3600:
            state.absorption_seconds = 0.0
            state.absorption_started = False
            state.absorption_last_qualifying_ts = None
            state.absorption_status = "full_lockout"
            return
        last = state.absorption_last_qualifying_ts
        if last is not None and (ts < last or ts - last > 8 * 3600):
            state.absorption_seconds = 0.0
            state.absorption_started = False
            state.absorption_last_qualifying_ts = None
            state.absorption_status = "reset_stale"
        if current < -0.5 and dt > 0:
            # Discharge pauses rather than accruing absorption time.
            state.absorption_status = "paused_discharge"
            return
        target = max(26.0, min(31.0, float(self.absorption_voltage_v)))
        tolerance = max(0.0, min(1.0, float(self.absorption_tolerance_v)))
        required = max(30.0, min(360.0, float(self.absorption_minutes))) * 60
        if voltage >= target and current >= 0.5 and quality_ok:
            state.absorption_started = True
        qualifying = (state.absorption_started and voltage >= target - tolerance
                      and current >= 0.5 and quality_ok and 0 < dt <= self.MAX_ENERGY_DT_S)
        if not qualifying:
            state.absorption_status = "paused" if state.absorption_started else "waiting_voltage"
            return
        state.absorption_seconds = min(required, max(0.0, state.absorption_seconds) + dt)
        state.absorption_last_qualifying_ts = ts
        state.absorption_status = "counting"
        if state.absorption_seconds >= required and "BATTERY_FULL_DETECTED" not in events:
            events.extend(("FULL_BY_ABSORPTION_TIME", "BATTERY_FULL_DETECTED"))

    def _learn_full_charge(self, dt: float, battery_v: float, battery_a: float, pv_w: float, hard_low_v: float, events: list[str]) -> None:
        if dt <= 0: return
        strong_charge = battery_a >= 0.5  # FULL is chemistry/terminal-state based; charging source may be PV or external
        threshold = max(hard_low_v + 2.0, self.state.learned_full_charge_voltage_v - 0.8)
        if strong_charge and battery_v >= threshold:
            self.state.full_charge_hold_seconds += dt
            self.state.full_charge_peak_v = max(self.state.full_charge_peak_v, battery_v)
        else:
            self.state.full_charge_hold_seconds = max(0.0, self.state.full_charge_hold_seconds - dt * 0.5)
        if strong_charge and self.state.full_charge_hold_seconds >= 900.0:
            candidate = max(battery_v, self.state.full_charge_peak_v)
            alpha = 0.32 if self.state.full_charge_samples < 3 else 0.12
            old = self.state.learned_full_charge_voltage_v
            learned = candidate if self.state.full_charge_samples == 0 or old <= hard_low_v + 1.0 else old + alpha * (candidate - old)
            self.state.learned_full_charge_voltage_v = max(hard_low_v + 1.2, min(31.5, learned))
            if not self.state.full_seen_pending: events.append("BATTERY_FULL_DETECTED")
            self.state.full_seen_pending = True
            self.state.calibration_full_seen = True
            if not self.state.full_charge_latched:
                self.state.full_charge_samples += 1
                self.state.full_charge_latched = True
        elif not strong_charge and self.state.full_charge_hold_seconds <= 30.0:
            self.state.full_charge_latched = False

    def _learn_transition(self, dt: float, battery_v: float, battery_a: float, pv_w: float, hard_low_v: float, calibration_enabled: bool, events: list[str]) -> bool:
        if not self.state.full_seen_pending: return False
        discharge_started = battery_a <= -0.5 and not self.state.pv_charge_active
        if discharge_started and not self.state.transition_capture_active:
            self.state.transition_capture_active = True
            self.state.transition_capture_seconds = 0.0
            self.state.transition_voltage_sum = 0.0
            self.state.transition_voltage_count = 0
            events.append("FULL_TRANSITION_START")
        if not self.state.transition_capture_active or dt <= 0: return False
        self.state.transition_capture_seconds += dt
        if 300.0 <= self.state.transition_capture_seconds <= 900.0 and battery_a <= -0.3:
            self.state.transition_voltage_sum += battery_v
            self.state.transition_voltage_count += 1
        if self.state.transition_capture_seconds < 900.0: return False
        if self.state.transition_voltage_count >= 4:
            candidate = self.state.transition_voltage_sum / self.state.transition_voltage_count
            full_charge = max(hard_low_v + 1.0, self.state.learned_full_charge_voltage_v)
            candidate = max(hard_low_v + 0.5, min(full_charge, candidate))
            alpha = 0.40 if self.state.full_transition_samples < 3 else 0.15
            old = self.state.learned_full_transition_voltage_v
            self.state.learned_full_transition_voltage_v = candidate if self.state.full_transition_samples == 0 or old <= hard_low_v + 0.5 else old + alpha * (candidate - old)
            self.state.full_transition_samples += 1
            events.append("FULL_TRANSITION_LEARNED")
            completed = bool(calibration_enabled and self.state.calibration_full_seen)
        else:
            completed = False
        self.state.full_seen_pending = False
        self.state.transition_capture_active = False
        self.state.transition_capture_seconds = 0.0
        self.state.transition_voltage_sum = 0.0
        self.state.transition_voltage_count = 0
        self.state.calibration_full_seen = False
        return completed

    def _full_confidence(self, battery_v: float, battery_a: float, full_charge_v: float, transition_v: float, hard_low_v: float) -> float:
        model = min(1.0, self.state.full_charge_samples / 4.0) * 0.40
        transition = min(1.0, self.state.full_transition_samples / 4.0) * 0.30
        if battery_a > 0.3:
            voltage_score = max(0.0, min(1.0, (battery_v - (full_charge_v - 0.8)) / 0.8))
        else:
            voltage_score = max(0.0, min(1.0, (battery_v - hard_low_v) / max(0.6, transition_v - hard_low_v)))
        hold = min(1.0, self.state.full_charge_hold_seconds / 1200.0) * 0.30
        return max(0.0, min(1.0, model + transition + max(hold, voltage_score * 0.22)))

    def _fallback(self, hard_low_v: float, calibration_enabled: bool) -> BatteryEstimate:
        capacity = self._effective_capacity()
        stored = max(0.0, min(capacity, self.state.stored_energy_kwh if self.state.stored_energy_kwh >= 0 else 0.0))
        return BatteryEstimate(
            full_charge_voltage_v=round(max(hard_low_v + 1.0, self.state.learned_full_charge_voltage_v), 2),
            full_transition_voltage_v=round(max(hard_low_v + 0.6, self.state.learned_full_transition_voltage_v), 2),
            relaxation_drop_v=0.0, full_confidence=0.0,
            transition_confidence=min(1.0, self.state.full_transition_samples / 4.0),
            reserve_fraction=stored / max(0.5, capacity), recovery_need=1.0, recovery_state="strong_recovery",
            learned_total_gap_kwh=self.state.learned_total_gap_energy_kwh,
            learned_battery_gap_kwh=self.state.learned_battery_gap_energy_kwh,
            learned_grid_gap_kwh=self.state.learned_grid_gap_energy_kwh,
            current_gap_total_kwh=self.state.current_gap_total_kwh,
            demand_confidence=min(1.0, self.state.total_gap_samples / 6.0), pv_charge_state="unknown",
            calibration_state="charging_to_full" if calibration_enabled else "off", calibration_complete=False,
            stored_energy_kwh=stored, usable_capacity_kwh=capacity,
            capacity_confidence=min(1.0, self.state.capacity_samples / 5.0), energy_state_confidence=0.0,
            energy_delta_kwh=0.0, measurement_quality="invalid",
            typical_gap_kwh=self.state.learned_total_gap_typical_kwh, recent_gap_kwh=self.state.learned_total_gap_recent_kwh,
            last_gap_classification=self.state.last_gap_classification, events=(),
        )
