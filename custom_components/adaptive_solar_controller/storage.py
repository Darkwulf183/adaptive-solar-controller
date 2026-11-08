from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DEFAULT_BATTERY_STRATEGY_MAX_V, DOMAIN, MODE_MONITOR

STORAGE_VERSION = 1


@dataclass
class LearningState:
    # Controller persistence
    control_mode: str = MODE_MONITOR
    controller_enabled: bool = True

    # Plant / response learning
    gain: float = 1.0
    integral: float = 0.0
    last_target: float | None = None
    last_grid: float | None = None
    last_load: float | None = None
    deadtime_s: float = 15.0
    samples: int = 0
    buckets: dict[str, dict[str, float]] = field(default_factory=dict)
    tod_buckets: dict[str, dict[str, float]] = field(default_factory=dict)
    response_samples: int = 0
    response_gain_variance: float = 0.0
    last_learning_decay_day: str | None = None

    # Prediction validation / maturity
    prediction_eval_samples: int = 0
    prediction_abs_error_ema: float = 1.0
    prediction_bias_ema: float = 0.0

    # Adaptive deadband learning
    noise_pos_ema: float = 10.0
    noise_neg_ema: float = 8.0
    noise_pos_samples: int = 0
    noise_neg_samples: int = 0

    # Forecast.Solar trust learning
    forecast_bias_ema: float = 1.0
    forecast_abs_error_ema: float = 0.5
    forecast_samples: int = 0
    forecast_daily_bias_ema: float = 1.0
    forecast_daily_error_ema: float = 0.5
    forecast_daily_samples: int = 0
    forecast_day: str | None = None
    forecast_today_anchor_kwh: float | None = None
    actual_pv_today_kwh: float = 0.0
    last_pv_ts: float | None = None
    average_actual_day_kwh: float = 0.0
    completed_pv_days: int = 0

    # Seasonal PV production learner
    seasonal_buckets: dict[str, dict[str, float]] = field(default_factory=dict)
    seasonal_history_bootstrapped: bool = False
    seasonal_history_days: int = 0
    seasonal_day: str | None = None
    seasonal_current_max_kwh: float = 0.0

    # RC3: independent passive CSV weather baseline; never read by the active planner.
    passive_pv_daily_kwh: dict[str, float] = field(default_factory=dict)
    passive_pv_imported_at: str | None = None
    passive_pv_import_count: int = 0

    # Battery model generation. v3 = ASC v0.4.2 energy-state estimator.
    battery_model_version: int = 3
    flight_recorder_enabled: bool = False
    battery_calibration_enabled: bool = False
    inverter_max_power_w: float = 660.0
    hard_cutoff_voltage_v: float = 22.8
    emergency_terminal_voltage_v: float = 22.0  # independent under-load emergency stop
    hard_cutoff_latched: bool = False
    low_recovery_mode: str = "Aus"
    low_recovery_runs: list[dict[str, Any]] = field(default_factory=list)
    low_recovery_last_full_ts: float | None = None
    low_recovery_last_status: str = "waiting_full"
    rebound_learning_reference: dict[str, Any] = field(default_factory=dict)  # Historical rebound samples, not capacity calibration
    rebound_learning_model: dict[str, Any] = field(default_factory=dict)
    low_recovery_last_abort: str = ""
    low_recovery_last_success_ts: float | None = None


    # Battery strategy / legacy fields kept only for storage compatibility/diagnostics.
    battery_strategy_max_v: float = DEFAULT_BATTERY_STRATEGY_MAX_V
    learned_battery_high_v: float = 23.7
    battery_strategy_samples: int = 0
    battery_strategy_confidence: float = 0.0
    battery_day: str | None = None
    battery_day_min_v: float | None = None
    battery_day_max_v: float | None = None
    battery_morning_min_v: float | None = None
    battery_last_ts: float | None = None

    learned_full_voltage_v: float = 27.0
    full_model_samples: int = 0
    battery_full_hold_seconds: float = 0.0
    battery_day_high_charge_seconds: float = 0.0
    battery_full_confidence: float = 0.0

    # Energy between sufficiently strong PV charging phases
    energy_gap_duration_s: float = 0.0
    energy_gap_discharge_kwh: float = 0.0
    learned_gap_energy_kwh: float = 0.0
    gap_energy_samples: int = 0

    # Optional learned usable capacity from full -> low cycles
    full_cycle_active: bool = False
    discharge_since_full_kwh: float = 0.0
    usable_capacity_estimate_kwh: float = 0.0
    capacity_samples: int = 0


    # Physical battery full/transition anchors (introduced in v0.4.1)
    learned_full_charge_voltage_v: float = 27.0
    learned_full_transition_voltage_v: float = 25.2
    full_charge_samples: int = 0
    full_transition_samples: int = 0
    full_charge_hold_seconds: float = 0.0
    full_charge_peak_v: float = 0.0
    full_charge_latched: bool = False
    full_seen_pending: bool = False
    transition_capture_active: bool = False
    transition_capture_seconds: float = 0.0
    transition_voltage_sum: float = 0.0
    transition_voltage_count: int = 0
    calibration_full_seen: bool = False

    # Real PV charge phase and total demand between charge phases
    pv_charge_active: bool = False
    pv_charge_on_seconds: float = 0.0
    pv_charge_off_seconds: float = 0.0
    current_gap_duration_s: float = 0.0
    current_gap_total_kwh: float = 0.0
    current_gap_battery_kwh: float = 0.0
    current_gap_grid_kwh: float = 0.0
    learned_total_gap_energy_kwh: float = 0.0
    learned_total_gap_typical_kwh: float = 0.0
    learned_total_gap_recent_kwh: float = 0.0
    learned_battery_gap_energy_kwh: float = 0.0
    learned_grid_gap_energy_kwh: float = 0.0
    total_gap_samples: int = 0
    last_completed_gap_total_kwh: float = 0.0
    last_completed_gap_battery_kwh: float = 0.0
    last_completed_gap_grid_kwh: float = 0.0
    gap_start_reserve_fraction: float | None = None
    battery_recent_min_v: float = 99.0


    # ASC v0.4.2 integrated battery energy state
    battery_capacity_start_kwh: float = 5.0
    stored_energy_kwh: float = -1.0
    energy_anchor_seen: bool = False
    energy_anchor_samples: int = 0
    energy_integrated_seconds: float = 0.0
    energy_integrated_kwh: float = 0.0
    energy_rejected_samples: int = 0
    low_anchor_hold_seconds: float = 0.0
    low_anchor_latched: bool = False
    low_anchor_release_seconds: float = 0.0
    relaxed_hold_seconds: float = 0.0
    last_capacity_sample_kwh: float = 0.0
    extraordinary_gap_samples: int = 0
    last_gap_classification: str = "unknown"

    # Current energy-budget diagnostics
    energy_budget_kwh: float = 0.0
    energy_budget_state: str = "learning"
    energy_budget_confidence: float = 0.0
    target_reserve_fraction: float = 0.20

    # ASC v0.4.3 strategy learning
    battery_chemistry: str = "lead_acid"
    progressive_gamma: float = 1.70
    planning_reserve_adjustment: float = 0.0
    planner_eval_samples: int = 0
    planner_reserve_error_ema: float = 0.0
    last_planner_evaluation: str = "learning"
    power_envelope_multiplier: float = 1.0
    power_envelope_samples: int = 0

    # ASC v0.4.4 chemistry-aware planning / confidence smoothing
    # Cumulative absorption: persisted across controller restarts.
    absorption_seconds: float = 0.0
    absorption_last_qualifying_ts: float | None = None
    absorption_started: bool = False
    absorption_status: str = "waiting"
    full_anchor_source: str = "unknown"
    last_full_anchor_ts: float | None = None
    lead_full_priority: float = 0.0
    lead_full_opportunity: str = "none"
    lead_strategy_state: str = "normal"
    # v0.4.5: persisted daily Lead/PzS FULL mission (no forecast-driven replanning)
    lead_plan_day: str = ""
    lead_plan_target_fraction: float = 0.0
    lead_plan_priority: float = 0.0
    lead_plan_start_energy_kwh: float = 0.0
    lead_plan_start_full_ts: float | None = None
    lead_plan_last_evaluation: str = "not_evaluated"
    lead_plan_peak_fraction: float = 0.0
    lead_emergency_days: float = 10.0
    lead_full_target_days: float = 7.0
    planning_confidence_ema: float = -1.0
    inverter_full_lock_owned: bool = False
    inverter_full_lock_entity: str = ""
    battery_energy_charged_total_kwh: float = 0.0
    battery_energy_discharged_total_kwh: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LearningState":
        if not data:
            return cls()
        kwargs = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        state = cls(**kwargs)
        # v0.4.1 keeps proven prediction/forecast/seasonal/response learning but
        # intentionally starts the redesigned battery estimator/planner fresh.
        if "battery_model_version" not in data or int(data.get("battery_model_version", 0)) < 2:
            state.battery_model_version = 2
            state.learned_full_charge_voltage_v = max(23.6, float(data.get("learned_full_voltage_v", 27.0)))
            state.learned_full_transition_voltage_v = max(23.2, min(state.learned_full_charge_voltage_v, 25.2))
            state.full_charge_samples = 0
            state.full_transition_samples = 0
            state.learned_total_gap_energy_kwh = 0.0
            state.learned_total_gap_typical_kwh = 0.0
            state.learned_total_gap_recent_kwh = 0.0
            state.learned_battery_gap_energy_kwh = 0.0
            state.learned_grid_gap_energy_kwh = 0.0
            state.total_gap_samples = 0
            state.energy_budget_kwh = 0.0
            state.energy_budget_state = "learning"
            state.energy_budget_confidence = 0.0
            state.battery_strategy_confidence = 0.0
        # v0.4.2 keeps v0.4.1 full/transition and demand learning, but starts
        # the integrated energy state with low confidence until a real full anchor.
        if int(data.get("battery_model_version", 0)) < 3:
            state.battery_model_version = 3
            if state.usable_capacity_estimate_kwh < 0.5:
                state.usable_capacity_estimate_kwh = state.battery_capacity_start_kwh
            state.stored_energy_kwh = -1.0
            state.energy_anchor_seen = False
            state.energy_anchor_samples = 0
            state.energy_integrated_seconds = 0.0
            state.energy_integrated_kwh = 0.0
            state.energy_rejected_samples = 0
            state.low_anchor_hold_seconds = 0.0
            state.relaxed_hold_seconds = 0.0
            state.capacity_samples = 0

        # Coerce values saved by older releases and preserve old learned state.
        for name in (
            "samples", "response_samples", "prediction_eval_samples",
            "forecast_samples", "forecast_daily_samples", "battery_strategy_samples",
            "seasonal_history_days", "full_model_samples", "gap_energy_samples", "capacity_samples",
            "battery_model_version", "full_charge_samples", "full_transition_samples", "total_gap_samples",
            "transition_voltage_count", "energy_anchor_samples", "energy_rejected_samples", "extraordinary_gap_samples",
            "planner_eval_samples", "power_envelope_samples",
        ):
            setattr(state, name, int(getattr(state, name)))
        for name in (
            "gain", "integral", "forecast_bias_ema", "forecast_abs_error_ema",
            "forecast_daily_bias_ema", "forecast_daily_error_ema", "learned_battery_high_v",
            "battery_strategy_max_v", "learned_full_voltage_v", "learned_gap_energy_kwh",
            "usable_capacity_estimate_kwh", "learned_full_charge_voltage_v",
            "learned_full_transition_voltage_v", "learned_total_gap_energy_kwh",
            "learned_battery_gap_energy_kwh", "learned_grid_gap_energy_kwh",
            "learned_total_gap_typical_kwh", "learned_total_gap_recent_kwh",
            "battery_capacity_start_kwh", "hard_cutoff_voltage_v", "stored_energy_kwh", "energy_integrated_seconds", "energy_integrated_kwh",
            "low_anchor_hold_seconds", "low_anchor_release_seconds", "relaxed_hold_seconds", "last_capacity_sample_kwh",
            "progressive_gamma", "planning_reserve_adjustment", "planner_reserve_error_ema", "power_envelope_multiplier",
            "lead_full_priority", "lead_plan_target_fraction", "lead_plan_priority", "lead_plan_start_energy_kwh", "lead_plan_peak_fraction", "lead_emergency_days", "lead_full_target_days", "planning_confidence_ema", "battery_energy_charged_total_kwh", "battery_energy_discharged_total_kwh", "absorption_seconds",
        ):
            setattr(state, name, float(getattr(state, name)))
        # v0.3.x could learn high above the new default strategy maximum. Clamp
        # only the diagnostic value; no historical response/prediction learning is lost.
        state.learned_battery_high_v = min(state.learned_battery_high_v, state.battery_strategy_max_v)
        state.hard_cutoff_voltage_v = max(20.0, min(25.0, state.hard_cutoff_voltage_v))
        # A missing/invalid capacity estimate must never replace valid prior learning.
        if not 0.5 <= state.usable_capacity_estimate_kwh <= 60.0:
            state.usable_capacity_estimate_kwh = max(0.5, min(60.0, state.battery_capacity_start_kwh))
        return state

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class LearningStore:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")

    async def async_load(self) -> LearningState:
        return LearningState.from_dict(await self._store.async_load())

    async def async_save(self, state: LearningState) -> None:
        await self._store.async_save(state.as_dict())
