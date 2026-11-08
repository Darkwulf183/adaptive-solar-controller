from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from .battery import BatteryEstimator
from .rebound_learning import predicted_sag
from .const import MODE_ADAPTIVE, MODE_OFF, MODE_PREDICTIVE, PREDICTION_MATURE, PREDICTION_USABLE
from .forecast import SolarForecastLearner
from .learning import PatternLearner
from .planner import EnergyPlanner
from .seasonal import SeasonalProductionLearner
from .storage import LearningState
from .strategy import StrategyLearner


@dataclass
class PlantSnapshot:
    grid_w: float
    pv_w: float
    daily_production_kwh: float | None
    battery_v: float
    battery_a: float
    battery_w: float
    inverter_output_w: float
    target_w: float
    battery_low_v: float
    backup_w: float
    forecast_power_now_w: float | None = None
    forecast_power_next_hour_w: float | None = None
    forecast_energy_next_hour_kwh: float | None = None
    forecast_energy_today_kwh: float | None = None
    forecast_energy_remaining_kwh: float | None = None
    forecast_energy_tomorrow_kwh: float | None = None
    measurement_spread_s: float = 0.0


@dataclass
class ControlResult:
    recommended_w: float
    applied_w: float | None
    predicted_load_w: float | None
    current_load_w: float
    confidence: float
    prediction_maturity: str
    prediction_eval_samples: int
    gain: float
    effective_limit_w: float
    blocked: bool
    blocked_reason: str
    mode: str
    grid_error_w: float
    jump_detected: bool
    jump_confidence: float
    jump_target_w: float | None
    raw_target_w: float
    response_learning_eligible: bool
    saturation_reason: str
    deadband_negative_w: float
    deadband_positive_w: float
    deadband_maturity: float
    minimum_useful_delta_w: float
    export_escalation: str
    forecast_trust: float
    forecast_bias: float
    forecast_reputation: str
    corrected_forecast_remaining_kwh: float | None
    corrected_forecast_tomorrow_kwh: float | None
    seasonal_expected_today_kwh: float | None
    seasonal_expected_tomorrow_kwh: float | None
    seasonal_confidence: float
    battery_recovery_state: str
    battery_recovery_need: float
    battery_full_confidence: float
    learned_full_charge_voltage_v: float
    learned_full_transition_voltage_v: float
    battery_relaxation_drop_v: float
    transition_confidence: float
    energy_budget_kwh: float
    energy_budget_state: str
    energy_budget_confidence: float
    expected_total_need_kwh: float
    learned_battery_gap_kwh: float
    learned_grid_gap_kwh: float
    current_gap_total_kwh: float
    battery_demand_confidence: float
    battery_reserve_fraction: float
    target_reserve_fraction: float
    pv_charge_state: str
    planner_reason: str
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
    surplus_available: bool
    available_surplus_power_w: float
    available_surplus_energy_kwh: float
    surplus_confidence: float
    events: tuple[str, ...]
    battery_chemistry: str
    progressive_gamma: float
    progressive_release_factor: float
    battery_power_envelope_w: float
    power_envelope_confidence: float
    planning_confidence: float
    planning_reserve_adjustment: float
    planner_evaluation: str
    horizon_24h_balance_kwh: float | None
    horizon_48h_balance_kwh: float | None
    horizon_72h_balance_kwh: float | None
    full_charge_priority: float
    full_charge_opportunity: str
    chemistry_strategy_state: str
    days_since_full: float | None


class AdaptiveController:
    """ASC v0.4.4 orchestration: energy estimator -> planner -> fast controller."""

    def __init__(self, state: LearningState) -> None:
        self.state = state
        self.learner = PatternLearner(state)          # load/prediction + response estimator
        self.forecast = SolarForecastLearner(state)  # forecast estimator
        self.seasonal = SeasonalProductionLearner(state)
        self.battery = BatteryEstimator(state)        # physical battery estimator
        self.planner = EnergyPlanner(state)           # slow energy allowance
        self.strategy = StrategyLearner(state)        # v0.4.3 self-evaluation / power envelope
        self.mode = state.control_mode
        self.enabled = state.controller_enabled
        self._last_command_target: float | None = None
        self._last_command_grid: float | None = None
        self._last_command_learning_eligible = False
        self._previous_grid_w: float | None = None
        self._export_streak = 0

    def reset_transient(self) -> None:
        self.state.integral = 0.0
        self._last_command_target = None
        self._last_command_grid = None
        self._last_command_learning_eligible = False
        self._previous_grid_w = None
        self._export_streak = 0

    def calculate(
        self,
        snapshot: PlantSnapshot,
        now: datetime,
        grid_target_w: float,
        backup_block_w: float,
        min_target_w: float,
        max_step_w: float,
        hard_max_w: float,
    ) -> ControlResult:
        # -------------------- ESTIMATORS --------------------
        load_w = snapshot.inverter_output_w + snapshot.grid_w
        self.learner.observe_load(now, load_w)
        predicted_load, prediction_confidence, prediction_maturity = self.learner.predict_load(now, 2)

        response_cycle = self._last_command_target is not None and self._last_command_grid is not None
        if response_cycle:
            if self._last_command_learning_eligible:
                self.learner.observe_response(
                    self._last_command_target, snapshot.target_w,
                    self._last_command_grid, snapshot.grid_w,
                )
            self._last_command_target = None
            self._last_command_grid = None
            self._last_command_learning_eligible = False

        self.forecast.observe(now, snapshot.pv_w, snapshot.forecast_power_now_w, snapshot.forecast_energy_today_kwh)
        forecast_trust, forecast_bias, forecast_reputation = self.forecast.trust()
        corrected_remaining = None if snapshot.forecast_energy_remaining_kwh is None else max(0.0, snapshot.forecast_energy_remaining_kwh * forecast_bias)
        corrected_tomorrow = None if snapshot.forecast_energy_tomorrow_kwh is None else max(0.0, snapshot.forecast_energy_tomorrow_kwh * forecast_bias)

        self.seasonal.observe_daily_total(now, snapshot.daily_production_kwh)
        seasonal_today, seasonal_tomorrow, seasonal_confidence = self.seasonal.today_and_tomorrow(now)

        battery = self.battery.observe(
            now=now,
            battery_v=snapshot.battery_v,
            battery_a=snapshot.battery_a,
            battery_w=snapshot.battery_w,
            pv_w=snapshot.pv_w,
            grid_w=snapshot.grid_w,
            inverter_output_w=snapshot.inverter_output_w,
            hard_low_v=snapshot.battery_low_v,
            calibration_enabled=self.state.battery_calibration_enabled,
            measurement_spread_s=snapshot.measurement_spread_s,
        )

        # -------------------- v0.4.3 STRATEGY + ENERGY PLANNER --------------------
        # Evaluate the previous gap exactly when a new real PV charge phase begins.
        planner_evaluation = self.strategy.evaluate_cycle(
            battery.events, battery.reserve_fraction, self.state.target_reserve_fraction
        )
        envelope_w, envelope_conf = self.strategy.power_envelope(
            reserve=battery.reserve_fraction, battery_v=snapshot.battery_v, battery_a=snapshot.battery_a,
            hard_low_v=snapshot.battery_low_v, min_w=min_target_w, max_w=hard_max_w
        )
        planning_conf = self.strategy.planning_confidence(
            energy_conf=battery.energy_state_confidence, capacity_conf=battery.capacity_confidence,
            demand_conf=battery.demand_confidence, forecast_trust=forecast_trust,
            measurement_good=battery.measurement_quality == "synced", envelope_conf=envelope_conf
        )
        plan = self.planner.plan(
            battery=battery, battery_a=snapshot.battery_a,
            corrected_remaining_kwh=corrected_remaining, corrected_tomorrow_kwh=corrected_tomorrow,
            forecast_trust=forecast_trust, seasonal_today_kwh=seasonal_today,
            seasonal_tomorrow_kwh=seasonal_tomorrow, seasonal_confidence=seasonal_confidence,
            calibration_enabled=self.state.battery_calibration_enabled, planning_confidence=planning_conf,
        )

        # Generic planner-approved energy release for HA automations. Power is
        # immediate physical PV headroom; energy is the planner-approved battery
        # budget and can also be used for delayed/longer consumer decisions.
        immediate_pv_headroom_w = max(0.0, snapshot.pv_w - max(0.0, load_w))
        available_surplus_power_w = immediate_pv_headroom_w if plan.surplus_available else 0.0

        # Progressive release: low energy authority rises gently, then increasingly faster.
        progressive_factor = self.strategy.progressive_factor(plan.limit_factor)
        progressive_limit = min_target_w + progressive_factor * (hard_max_w - min_target_w)
        # Energy permission and chemistry-aware instantaneous battery capability are independent.
        effective_limit = min(progressive_limit, envelope_w)
        effective_limit = max(min_target_w, min(hard_max_w, effective_limit))
        # Provisional measured rebound curve: conservative *reduction only*
        # near LOW, without touching the established fast grid regulator.
        if (self.state.battery_chemistry == "lead_acid" and
                self.state.rebound_learning_model.get("valid_bins", 0) >= 5 and
                snapshot.battery_low_v < snapshot.battery_v <= snapshot.battery_low_v + 1.2):
            current_sag = predicted_sag(self.state.rebound_learning_model, snapshot.inverter_output_w)
            if current_sag is not None:
                estimated_relaxed_v = snapshot.battery_v + current_sag
                for candidate in range(int(effective_limit), int(min_target_w) - 1, -10):
                    sag = predicted_sag(self.state.rebound_learning_model, float(candidate))
                    if sag is not None and estimated_relaxed_v - sag >= snapshot.battery_low_v + 0.12:
                        effective_limit = min(effective_limit, max(min_target_w, candidate))
                        break
                else:
                    effective_limit = min_target_w
        if snapshot.battery_v <= snapshot.battery_low_v or self.state.battery_calibration_enabled:
            effective_limit = min_target_w

        lead_zero_target = (
            self.state.battery_chemistry == "lead_acid"
            and plan.chemistry_strategy_state in ("lead_full_hold", "lead_full_emergency")
        )
        if lead_zero_target:
            effective_limit = 0.0

        # -------------------- FAST GRID CONTROLLER --------------------
        blocked = False
        blocked_reason = ""
        if not self.enabled or self.mode == MODE_OFF:
            blocked, blocked_reason = True, "controller_off"
        elif snapshot.backup_w >= backup_block_w:
            blocked, blocked_reason = True, "backup_inverter_active"
        elif snapshot.inverter_output_w <= 28 and not self.state.battery_calibration_enabled:
            blocked, blocked_reason = True, "main_inverter_not_active"
        elif not all(math.isfinite(v) for v in (snapshot.grid_w, snapshot.battery_v, snapshot.target_w, effective_limit)):
            blocked, blocked_reason = True, "invalid_input"

        error = snapshot.grid_w - grid_target_w
        gain = max(0.35, min(1.5, self.state.gain))
        grid_jump_w = 0.0 if self._previous_grid_w is None else snapshot.grid_w - self._previous_grid_w
        jump_detected = not response_cycle and self._previous_grid_w is not None and abs(grid_jump_w) >= 180.0
        jump_confidence = self.learner.response_confidence()
        jump_target = None
        self._previous_grid_w = snapshot.grid_w

        deadband_neg, deadband_pos, deadband_maturity = self.learner.adaptive_deadband(grid_target_w)
        quiet_eligible = not blocked and not response_cycle and not jump_detected and effective_limit > min_target_w + 5 and snapshot.grid_w >= 0
        self.learner.observe_deadband(error, quiet_eligible)

        if abs(error) < 250:
            self.state.integral = max(-120.0, min(120.0, self.state.integral + error * 0.025))
        else:
            self.state.integral *= 0.85

        reactive_target = snapshot.target_w + error / gain + self.state.integral * 0.12
        theoretical_target = reactive_target

        if self.mode == MODE_PREDICTIVE and predicted_load is not None and prediction_maturity in (PREDICTION_USABLE, PREDICTION_MATURE):
            predictive_target = predicted_load - grid_target_w
            max_blend = 0.25 if prediction_maturity == PREDICTION_USABLE else 0.55
            blend = min(max_blend, max(0.0, prediction_confidence * max_blend))
            theoretical_target = reactive_target * (1.0 - blend) + predictive_target * blend

        if -deadband_neg <= error <= deadband_pos:
            theoretical_target = snapshot.target_w

        trusted_jump = jump_detected and jump_confidence >= 0.80 and abs(error) >= 120.0
        if trusted_jump:
            jump_target = snapshot.target_w + error / gain
            theoretical_target = jump_target

        export_escalation = "none"
        if snapshot.grid_w < -15.0:
            self._export_streak += 1
        else:
            self._export_streak = 0
        fast_export = snapshot.grid_w <= -50.0 or (snapshot.grid_w < -25.0 and self._export_streak >= 2)
        severe_export = snapshot.grid_w <= -150.0 or (snapshot.grid_w <= -80.0 and self._export_streak >= 2)
        if fast_export:
            export_escalation = "severe" if severe_export else "fast"
            theoretical_target = snapshot.target_w + error / gain
            self.state.integral = min(0.0, self.state.integral * 0.35)

        raw_target = theoretical_target
        if raw_target < min_target_w:
            response_learning_eligible = False; saturation_reason = "below_min_target"
        elif raw_target > effective_limit:
            response_learning_eligible = False; saturation_reason = "above_planner_limit"
        else:
            response_learning_eligible = True; saturation_reason = ""

        bypass_step = trusted_jump or severe_export
        if not bypass_step:
            delta = max(-max_step_w, min(max_step_w, theoretical_target - snapshot.target_w))
            recommended = snapshot.target_w + delta
        else:
            recommended = theoretical_target

        minimum_useful_delta = max(3.0, min(25.0, ((deadband_neg + deadband_pos) * 0.35) / gain))
        if not trusted_jump and not fast_export and abs(recommended - snapshot.target_w) < minimum_useful_delta:
            recommended = snapshot.target_w

        recommended = max(min_target_w, min(effective_limit, recommended))
        if snapshot.battery_v <= snapshot.battery_low_v:
            recommended = min_target_w
            response_learning_eligible = False
            saturation_reason = "battery_below_low"
        if self.state.battery_calibration_enabled:
            recommended = min_target_w
            response_learning_eligible = False
            saturation_reason = "battery_calibration"
        if lead_zero_target:
            recommended = 0.0
            response_learning_eligible = False
            saturation_reason = plan.chemistry_strategy_state
        if blocked:
            response_learning_eligible = False
            if not saturation_reason:
                saturation_reason = blocked_reason or "blocked"

        applied = None
        if not blocked and (self.mode in (MODE_ADAPTIVE, MODE_PREDICTIVE) or self.state.battery_calibration_enabled):
            applied = round(recommended)
            if applied != round(snapshot.target_w):
                self._last_command_target = snapshot.target_w
                self._last_command_grid = snapshot.grid_w
                self._last_command_learning_eligible = response_learning_eligible

        events = list(battery.events)
        if export_escalation == "fast": events.append("FAST_EXPORT")
        elif export_escalation == "severe": events.append("SEVERE_EXPORT")
        if plan.state == "preserve": events.append("BUDGET_LIMIT")
        if plan.state == "recovery": events.append("RECOVERY")

        return ControlResult(
            recommended_w=round(recommended, 1), applied_w=applied,
            predicted_load_w=None if predicted_load is None else round(predicted_load, 1),
            current_load_w=round(load_w, 1), confidence=round(prediction_confidence * 100.0, 1),
            prediction_maturity=prediction_maturity, prediction_eval_samples=self.state.prediction_eval_samples,
            gain=round(gain, 3), effective_limit_w=int(round(effective_limit)), blocked=blocked,
            blocked_reason=blocked_reason, mode=self.mode, grid_error_w=round(error, 1),
            jump_detected=jump_detected, jump_confidence=round(jump_confidence * 100.0, 1),
            jump_target_w=None if jump_target is None else round(jump_target, 1), raw_target_w=round(raw_target, 1),
            response_learning_eligible=response_learning_eligible, saturation_reason=saturation_reason,
            deadband_negative_w=deadband_neg, deadband_positive_w=deadband_pos,
            deadband_maturity=round(deadband_maturity * 100.0, 1), minimum_useful_delta_w=round(minimum_useful_delta, 1),
            export_escalation=export_escalation, forecast_trust=round(forecast_trust * 100.0, 1),
            forecast_bias=round(forecast_bias, 3), forecast_reputation=forecast_reputation,
            corrected_forecast_remaining_kwh=None if corrected_remaining is None else round(corrected_remaining, 3),
            corrected_forecast_tomorrow_kwh=None if corrected_tomorrow is None else round(corrected_tomorrow, 3),
            seasonal_expected_today_kwh=None if seasonal_today is None else round(seasonal_today, 2),
            seasonal_expected_tomorrow_kwh=None if seasonal_tomorrow is None else round(seasonal_tomorrow, 2),
            seasonal_confidence=round(seasonal_confidence * 100.0, 1),
            battery_recovery_state=battery.recovery_state, battery_recovery_need=round(battery.recovery_need * 100.0, 1),
            battery_full_confidence=round(battery.full_confidence * 100.0, 1),
            learned_full_charge_voltage_v=battery.full_charge_voltage_v,
            learned_full_transition_voltage_v=battery.full_transition_voltage_v,
            battery_relaxation_drop_v=battery.relaxation_drop_v,
            transition_confidence=round(battery.transition_confidence * 100.0, 1),
            energy_budget_kwh=plan.energy_budget_kwh, energy_budget_state=plan.state,
            energy_budget_confidence=round(plan.confidence * 100.0, 1), expected_total_need_kwh=plan.expected_need_kwh,
            learned_battery_gap_kwh=battery.learned_battery_gap_kwh, learned_grid_gap_kwh=battery.learned_grid_gap_kwh,
            current_gap_total_kwh=battery.current_gap_total_kwh,
            battery_demand_confidence=round(battery.demand_confidence * 100.0, 1),
            battery_reserve_fraction=round(battery.reserve_fraction * 100.0, 1),
            target_reserve_fraction=round(plan.target_reserve_fraction * 100.0, 1),
            pv_charge_state=battery.pv_charge_state, planner_reason=plan.reason,
            calibration_state=battery.calibration_state, calibration_complete=battery.calibration_complete,
            stored_energy_kwh=battery.stored_energy_kwh, usable_capacity_kwh=battery.usable_capacity_kwh,
            capacity_confidence=round(battery.capacity_confidence * 100.0, 1),
            energy_state_confidence=round(battery.energy_state_confidence * 100.0, 1),
            energy_delta_kwh=battery.energy_delta_kwh, measurement_quality=battery.measurement_quality,
            typical_gap_kwh=battery.typical_gap_kwh, recent_gap_kwh=battery.recent_gap_kwh,
            last_gap_classification=battery.last_gap_classification, surplus_available=plan.surplus_available,
            available_surplus_power_w=round(available_surplus_power_w, 1),
            available_surplus_energy_kwh=plan.available_surplus_energy_kwh,
            surplus_confidence=round(plan.surplus_confidence * 100.0, 1),
            events=tuple(events), battery_chemistry=self.state.battery_chemistry,
            progressive_gamma=round(self.state.progressive_gamma,3), progressive_release_factor=round(progressive_factor*100.0,1),
            battery_power_envelope_w=round(envelope_w,1), power_envelope_confidence=round(envelope_conf*100.0,1),
            planning_confidence=round(planning_conf*100.0,1),
            planning_reserve_adjustment=round(self.state.planning_reserve_adjustment*100.0,1),
            planner_evaluation=planner_evaluation, horizon_24h_balance_kwh=plan.horizon_24h_balance_kwh,
            horizon_48h_balance_kwh=plan.horizon_48h_balance_kwh, horizon_72h_balance_kwh=plan.horizon_72h_balance_kwh,
            full_charge_priority=round(plan.full_charge_priority * 100.0, 1),
            full_charge_opportunity=plan.full_charge_opportunity, chemistry_strategy_state=plan.chemistry_strategy_state,
            days_since_full=None if plan.days_since_full is None else round(plan.days_since_full, 2),
        )
