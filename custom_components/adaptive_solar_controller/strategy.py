from __future__ import annotations
from dataclasses import dataclass
import math
from .storage import LearningState

CHEM_LEAD = "lead_acid"
CHEM_LFP = "lifepo4"
CHEMISTRIES = [CHEM_LEAD, CHEM_LFP]

@dataclass
class StrategyResult:
    progressive_factor: float
    progressive_gamma: float
    power_envelope_w: float
    power_envelope_confidence: float
    planning_confidence: float
    planning_reserve_adjustment: float
    evaluation: str

class StrategyLearner:
    """v0.4.3 slow self-evaluation and chemistry-aware battery power envelope.

    Energy remains the SOC authority. Voltage is only used to estimate safe
    instantaneous discharge power, especially for lead-acid batteries.
    """
    def __init__(self, state: LearningState) -> None:
        self.state = state

    def evaluate_cycle(self, events: tuple[str, ...], reserve: float, target: float) -> str:
        if "PV_CHARGE_START" not in events:
            return self.state.last_planner_evaluation
        error = reserve - target
        self.state.planner_eval_samples += 1
        alpha = 0.18 if self.state.planner_eval_samples < 5 else 0.08
        self.state.planner_reserve_error_ema += alpha * (error - self.state.planner_reserve_error_ema)
        # Positive error = too much usable energy left at PV start -> less conservative.
        if error > 0.08:
            self.state.progressive_gamma = max(1.15, self.state.progressive_gamma - 0.04)
            self.state.planning_reserve_adjustment = max(-0.10, self.state.planning_reserve_adjustment - 0.01)
            result = "too_conservative"
        elif error < -0.03:
            self.state.progressive_gamma = min(2.80, self.state.progressive_gamma + 0.04)
            self.state.planning_reserve_adjustment = min(0.12, self.state.planning_reserve_adjustment + 0.01)
            result = "too_aggressive"
        else:
            result = "on_target"
        self.state.last_planner_evaluation = result
        return result

    def power_envelope(self, *, reserve: float, battery_v: float, battery_a: float,
                       hard_low_v: float, min_w: float, max_w: float) -> tuple[float, float]:
        chemistry = self.state.battery_chemistry
        if battery_a >= -0.3 or reserve >= 0.45:
            return max_w, min(1.0, 0.35 + self.state.power_envelope_samples / 30.0)

        if chemistry == CHEM_LFP:
            # Flat voltage plateau: energy reserve dominates until the lower knee.
            energy_factor = max(0.08, min(1.0, (reserve / 0.30) ** 0.65))
            knee = max(0.08, min(1.0, (battery_v - hard_low_v) / 0.55))
            factor = min(energy_factor, knee if battery_v < hard_low_v + 0.55 else 1.0)
        else:
            # Lead-acid: terminal-voltage headroom under load is useful as a power signal.
            headroom = battery_v - hard_low_v
            voltage_factor = max(0.06, min(1.0, (headroom - 0.12) / 1.15))
            energy_factor = max(0.08, min(1.0, (reserve / 0.38) ** 0.70))
            factor = min(energy_factor, voltage_factor)

            # Learn observed sag gently. High W with little headroom lowers future authority;
            # recovery/healthy headroom slowly restores it. This multiplier is bounded.
            discharge_w = max(0.0, -battery_v * battery_a)
            if discharge_w >= 80.0:
                stress = max(0.0, min(1.0, (0.85 - headroom) / 0.85))
                observed = max(0.45, 1.0 - 0.35 * stress)
                a = 0.03
                self.state.power_envelope_multiplier += a * (observed - self.state.power_envelope_multiplier)
                self.state.power_envelope_samples += 1
            factor *= max(0.55, min(1.08, self.state.power_envelope_multiplier))

        limit = min_w + factor * (max_w - min_w)
        confidence = min(1.0, 0.25 + self.state.power_envelope_samples / 40.0)
        return max(min_w, min(max_w, limit)), confidence

    def progressive_factor(self, release_fraction: float) -> float:
        x = max(0.0, min(1.0, release_fraction))
        gamma = max(1.15, min(2.80, self.state.progressive_gamma))
        return x ** gamma

    def planning_confidence(self, *, energy_conf: float, capacity_conf: float,
                            demand_conf: float, forecast_trust: float,
                            measurement_good: bool, envelope_conf: float) -> float:
        q = 1.0 if measurement_good else 0.70
        raw = max(0.0, min(1.0,
            0.28 * energy_conf + 0.18 * capacity_conf + 0.18 * demand_conf +
            0.16 * forecast_trust + 0.12 * envelope_conf + 0.08 * q))
        # v0.4.4: one degraded V/A sample must not immediately yank the planner
        # authority. Fall slowly, recover a little faster. This does not make a
        # degraded sample valid for energy integration; it only de-jitters planning.
        if self.state.planning_confidence_ema < 0.0:
            self.state.planning_confidence_ema = raw
        alpha = 0.035 if raw < self.state.planning_confidence_ema else 0.10
        self.state.planning_confidence_ema += alpha * (raw - self.state.planning_confidence_ema)
        return max(0.0, min(1.0, self.state.planning_confidence_ema))
