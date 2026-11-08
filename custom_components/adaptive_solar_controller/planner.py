from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .battery import BatteryEstimate
from .storage import LearningState

@dataclass
class EnergyPlan:
    energy_budget_kwh: float
    state: str
    confidence: float
    target_reserve_fraction: float
    limit_factor: float
    expected_need_kwh: float
    reason: str
    surplus_available: bool
    available_surplus_energy_kwh: float
    surplus_confidence: float
    horizon_24h_balance_kwh: float | None
    horizon_48h_balance_kwh: float | None
    horizon_72h_balance_kwh: float | None
    full_charge_priority: float
    full_charge_opportunity: str
    chemistry_strategy_state: str
    days_since_full: float | None

class EnergyPlanner:
    """v0.4.3 energy planner: adaptive reserve + multi-day energy horizon."""
    def __init__(self, state: LearningState) -> None:
        self.state = state
        # v0.4.4.1 Lead/PzS FULL mission.
        # Restore an unfinished mission from the already persisted 4.4 diagnostics.
        self._lead_full_mission = state.lead_full_opportunity in ("today", "building", "tomorrow")
        self._lead_full_mission_started_ts: float | None = None
        self._last_seen_full_anchor_ts = state.last_full_anchor_ts
        self._lead_full_hold_seconds = 3600.0
        self._lead_full_restart_lockout_seconds = 86400.0

    def plan(self, *, battery: BatteryEstimate, battery_a: float,
             corrected_remaining_kwh: float | None, corrected_tomorrow_kwh: float | None,
             forecast_trust: float, seasonal_today_kwh: float | None,
             seasonal_tomorrow_kwh: float | None, seasonal_confidence: float,
             calibration_enabled: bool, planning_confidence: float = 0.0) -> EnergyPlan:
        if calibration_enabled:
            return EnergyPlan(0.0, "calibration", 1.0, 1.0, 0.0, battery.learned_total_gap_kwh,
                              "battery_calibration", False, 0.0, 1.0, None, None, None,
                              0.0, "none", "calibration", self._days_since_full())

        expected_need = max(0.0, battery.learned_total_gap_kwh)
        demand_conf = battery.demand_confidence
        external_conf = max(0.0, min(1.0, forecast_trust * 0.65 + seasonal_confidence * 0.35))
        internal_conf = demand_conf * 0.40 + battery.energy_state_confidence * 0.45 + battery.capacity_confidence * 0.15
        confidence = max(0.0, min(1.0, internal_conf * (0.70 + 0.30 * external_conf)))
        if planning_confidence > 0:
            confidence = 0.55 * confidence + 0.45 * planning_confidence

        target = self._target_reserve(corrected_tomorrow_kwh, forecast_trust,
                                      seasonal_tomorrow_kwh, seasonal_confidence,
                                      battery.recovery_need)
        target += self.state.planning_reserve_adjustment
        # Low confidence adds a temporary uncertainty reserve; learned adjustment remains separate.
        target += max(0.0, 0.60 - planning_confidence) * 0.08
        target = max(0.06, min(0.48, target))

        target_energy = battery.usable_capacity_kwh * target
        budget = max(0.0, battery.stored_energy_kwh - target_energy)
        reserve_surplus = battery.reserve_fraction - target
        # Raw permission; v0.4.3 progressive release is applied by StrategyLearner.
        limit_factor = max(0.0, min(1.0, reserve_surplus / 0.25))

        if battery.energy_state_confidence < 0.20:
            limit_factor = min(limit_factor, 0.45)
        elif battery.energy_state_confidence < 0.40:
            limit_factor = min(limit_factor, 0.70)
        if battery_a > 0.5 and battery.recovery_need > 0.35 and battery.energy_state_confidence < 0.55:
            limit_factor *= max(0.20, 1.0 - battery.recovery_need * 0.70)
        if (budget > 0.0 and reserve_surplus > 0.01 and battery.recovery_need < 0.35
                and corrected_remaining_kwh is not None and seasonal_today_kwh and seasonal_today_kwh > 0.1):
            if corrected_remaining_kwh / seasonal_today_kwh >= 0.45 and confidence >= 0.18:
                limit_factor = min(1.0, limit_factor + 0.10)

        h24, h48, h72 = self._horizon(expected_need, corrected_tomorrow_kwh,
                                      seasonal_tomorrow_kwh, forecast_trust, seasonal_confidence)
        # If the next 48/72 h are expected to be energy-poor, preserve more today.
        multi_deficit = min(0.0, h48 if h48 is not None else 0.0, h72 if h72 is not None else 0.0)
        if multi_deficit < -expected_need * 0.6 and expected_need > 0.2:
            target = min(0.48, target + min(0.10, abs(multi_deficit) / max(1.0, expected_need) * 0.025))
            target_energy = battery.usable_capacity_kwh * target
            budget = max(0.0, battery.stored_energy_kwh - target_energy)
            reserve_surplus = battery.reserve_fraction - target
            limit_factor = min(limit_factor, max(0.0, min(1.0, reserve_surplus / 0.25)))

        # v0.4.4 chemistry strategy. LiFePO4 deliberately keeps the v0.4.3
        # energy strategy. Lead-acid adds a slow multi-day FULL objective.
        full_priority = 0.0
        full_opportunity = "none"
        chemistry_state = "lifepo4_v043" if self.state.battery_chemistry == "lifepo4" else "lead_normal"
        days_since_full = self._days_since_full()
        if self.state.battery_chemistry == "lead_acid":
            now = datetime.now().astimezone()
            now_ts = now.timestamp()
            today = now.date().isoformat()
            full_ts = self.state.last_full_anchor_ts
            full_age_s = None if not full_ts else max(0.0, now_ts - full_ts)
            new_full_anchor = bool(full_ts and (
                self._last_seen_full_anchor_ts is None or full_ts > self._last_seen_full_anchor_ts + 1.0
            ))
            if new_full_anchor:
                self._last_seen_full_anchor_ts = full_ts
                self._lead_full_mission = False
                self.state.lead_plan_day = ""  # FULL supersedes any old daily plan

            # Preserve the day's decisions across restarts and fluctuating forecasts.
            # Replan at most once per local calendar day, not every 15 seconds.
            if self.state.lead_plan_day != today:
                if self.state.lead_plan_day:
                    delta = battery.stored_energy_kwh - self.state.lead_plan_start_energy_kwh
                    self.state.lead_plan_last_evaluation = (
                        f"{self.state.lead_plan_day}: energy_change={delta:+.2f}kWh; "
                        f"peak={self.state.lead_plan_peak_fraction:.1%}; "
                        f"target={self.state.lead_plan_target_fraction:.1%}"
                    )
                age = 3.0 if days_since_full is None else days_since_full
                peak = max(0.0, min(1.0, battery.reserve_fraction))
                # Progressive time pressure independent of the intra-day forecast.
                if age < 3.0:
                    priority, floor = 0.0, target
                elif age < 6.0:
                    priority, floor = 0.40, max(target, 0.48)
                elif age < self.state.lead_full_target_days:
                    priority, floor = 0.70, max(target, 0.67)
                elif age < 8.0:
                    priority, floor = 0.82, max(target, 0.78)
                elif age < self.state.lead_emergency_days:
                    priority, floor = 0.93, max(target, 0.88)
                else:
                    priority, floor = 1.0, 1.0
                # A near-FULL battery must not lose the progress overnight.
                # Guard against an uncertain SOC estimate: never turn a guessed
                # 100% into a confirmed FULL anchor.
                if age >= 3.0 and battery.energy_state_confidence >= 0.45:
                    floor = max(floor, min(0.96, peak - 0.07))
                self.state.lead_plan_day = today
                self.state.lead_plan_target_fraction = min(1.0, floor)
                self.state.lead_plan_priority = priority
                self.state.lead_plan_start_energy_kwh = battery.stored_energy_kwh
                self.state.lead_plan_start_full_ts = full_ts
                self.state.lead_plan_peak_fraction = peak

            self.state.lead_plan_peak_fraction = max(
                self.state.lead_plan_peak_fraction, battery.reserve_fraction
            )
            age = days_since_full
            full_priority = self.state.lead_plan_priority
            full_opportunity = "daily_plan"
            chemistry_state = "lead_daily_full"

            if full_age_s is not None and full_age_s < self._lead_full_hold_seconds:
                full_priority = 1.0
                full_opportunity = "full_hold"
                chemistry_state = "lead_full_hold"
                self._lead_full_mission = False
            elif full_age_s is not None and full_age_s < self._lead_full_restart_lockout_seconds:
                full_priority = 0.0
                full_opportunity = "fulfilled"
                chemistry_state = "lead_post_full"
                self._lead_full_mission = False
            elif age is not None and age >= self.state.lead_emergency_days:
                full_priority = 1.0
                full_opportunity = "emergency"
                chemistry_state = "lead_full_emergency"
            elif full_priority >= 0.4:
                full_opportunity = "building"
                chemistry_state = "lead_daily_full"
            else:
                full_opportunity = "none"
                chemistry_state = "lead_normal"

            if chemistry_state == "lead_post_full":
                lead_target = target
            elif chemistry_state in ("lead_full_hold", "lead_full_emergency"):
                lead_target = 1.0
            else:
                lead_target = self.state.lead_plan_target_fraction
                if battery.energy_state_confidence >= 0.45 and full_priority >= 0.4:
                    lead_target = max(lead_target, min(0.96, self.state.lead_plan_peak_fraction - 0.07))

            if lead_target > target:
                target = lead_target
                target_energy = battery.usable_capacity_kwh * target
                budget = max(0.0, battery.stored_energy_kwh - target_energy)
                reserve_surplus = battery.reserve_fraction - target
                limit_factor = min(limit_factor, max(0.0, min(1.0, reserve_surplus / 0.25)))
            if chemistry_state in ("lead_full_hold", "lead_full_emergency"):
                limit_factor = 0.0
            self.state.lead_full_priority = full_priority
            self.state.lead_full_opportunity = full_opportunity
            self.state.lead_strategy_state = chemistry_state
        else:
            self.state.lead_full_priority = 0.0
            self.state.lead_full_opportunity = "none"
            self.state.lead_strategy_state = chemistry_state

        if battery.reserve_fraction <= target + 0.01:
            state, reason = "preserve", "target_energy_reserve_reached"
        elif battery.recovery_need >= 0.70:
            state, reason = "recovery", "battery_energy_recovery"
        elif reserve_surplus >= 0.25:
            state, reason = "use_energy", "healthy_energy_surplus"
        elif expected_need <= 0.05:
            state, reason = "learning", "learning_total_gap_demand"
        elif battery.energy_state_confidence < 0.20:
            state, reason = "learning", "learning_energy_state"
        else:
            state, reason = "balanced", "within_energy_corridor"

        if self.state.battery_chemistry == "lead_acid":
            if chemistry_state in ("lead_full_hold", "lead_full_emergency"):
                state, reason = "full_priority", "lead_full_charging_lock"
            elif full_priority >= 0.55 and state in ("preserve", "balanced"):
                reason = "lead_building_toward_full"

        surplus_available = budget >= 0.25 and confidence >= 0.20 and battery.reserve_fraction >= target + 0.05
        surplus_confidence = confidence if surplus_available else min(confidence, 0.49)
        self.state.energy_budget_kwh = budget
        self.state.energy_budget_state = state
        self.state.energy_budget_confidence = confidence
        self.state.target_reserve_fraction = target
        return EnergyPlan(round(budget,3), state, confidence, target, max(0.0,min(1.0,limit_factor)),
                          round(expected_need,3), reason, surplus_available, round(budget,3), surplus_confidence,
                          h24, h48, h72, round(full_priority,3), full_opportunity, chemistry_state, days_since_full)

    def _days_since_full(self) -> float | None:
        ts = self.state.last_full_anchor_ts
        if not ts:
            return None
        return max(0.0, (datetime.now().astimezone().timestamp() - ts) / 86400.0)

    def _lead_full_strategy(self, *, battery, corrected_remaining_kwh, corrected_tomorrow_kwh,
                            expected_need, days_since_full, forecast_trust):
        # Pressure grows slowly with time since a real FULL. If no FULL is known
        # after a reset, start moderately rather than immediately forcing 100 %.
        age = 3.0 if days_since_full is None else days_since_full
        age_pressure = max(0.0, min(1.0, age / 8.0))
        partial_pressure = max(0.0, min(1.0, (0.92 - battery.reserve_fraction) / 0.72))
        priority = max(0.0, min(1.0, 0.72 * age_pressure + 0.28 * partial_pressure))

        missing = max(0.0, battery.usable_capacity_kwh - battery.stored_energy_kwh)
        # Forecast must have a margin for simultaneous plant/house demand.
        today_required = missing + max(0.4, expected_need * 0.22)
        tomorrow_required = missing + max(0.7, expected_need * 0.35)
        opportunity = "none"
        if corrected_remaining_kwh is not None and forecast_trust >= 0.20 and corrected_remaining_kwh >= today_required:
            opportunity = "today"
            priority = max(priority, 0.82)
        elif corrected_tomorrow_kwh is not None and forecast_trust >= 0.20 and corrected_tomorrow_kwh >= tomorrow_required:
            opportunity = "tomorrow"
            priority = max(priority, 0.62)
        elif priority >= 0.70:
            opportunity = "building"

        if battery.reserve_fraction >= 0.97:
            state = "lead_near_full"
        elif opportunity == "today":
            state = "lead_full_priority"
        elif opportunity == "tomorrow":
            state = "lead_preserve_for_tomorrow"
        elif priority >= 0.55:
            state = "lead_building_toward_full"
        else:
            state = "lead_normal"
        return priority, opportunity, state

    def _target_reserve(self, corrected_tomorrow_kwh, forecast_trust, seasonal_tomorrow_kwh,
                        seasonal_confidence, recovery_need):
        expected = None
        if corrected_tomorrow_kwh is not None and seasonal_tomorrow_kwh is not None:
            fw=max(0.05,forecast_trust); sw=max(0.05,seasonal_confidence*0.75)
            expected=(corrected_tomorrow_kwh*fw+seasonal_tomorrow_kwh*sw)/(fw+sw)
        elif corrected_tomorrow_kwh is not None: expected=corrected_tomorrow_kwh
        elif seasonal_tomorrow_kwh is not None: expected=seasonal_tomorrow_kwh
        if expected is None: base=0.22
        elif expected<=1.0: base=0.32
        elif expected<=3.0: base=0.25
        elif expected<=6.0: base=0.18
        else: base=0.12
        return max(0.08,min(0.45,base+recovery_need*0.10))

    @staticmethod
    def _horizon(need, tomorrow, seasonal_tomorrow, forecast_trust, seasonal_conf):
        if need <= 0.05: return None, None, None
        pv1 = tomorrow if tomorrow is not None else seasonal_tomorrow
        if pv1 is None: return None, None, None
        # Day +2/+3 are deliberately seasonal proxies until dedicated forecast entities exist.
        proxy = seasonal_tomorrow if seasonal_tomorrow is not None else pv1
        h24 = pv1 - need
        h48 = h24 + proxy - need
        h72 = h48 + proxy - need
        return round(h24,2), round(h48,2), round(h72,2)
