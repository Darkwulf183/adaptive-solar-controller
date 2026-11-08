from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import CoreState, HomeAssistant

from .const import VERSION
from .start_marker import build_start_marker


FIELDS = [
    "timestamp","events","hard_cutoff_voltage_v","hard_cutoff_status","capacity_previous_kwh","capacity_current_kwh","capacity_change_reason","grid_w","pv_w","battery_v","battery_a","battery_w","inverter_output_w","target_w",
    "recommended_w","applied_w","raw_target_w","effective_limit_w","grid_error_w","predicted_load_w","prediction_confidence",
    "response_gain","deadband_export_w","deadband_import_w","export_escalation","forecast_trust","forecast_bias",
    "corrected_remaining_kwh","corrected_tomorrow_kwh","seasonal_today_kwh","seasonal_tomorrow_kwh","seasonal_confidence","seasonal_history_days","seasonal_history_coverage","passive_pv_days","passive_pv_expected_tomorrow_kwh","passive_pv_theoretical_weight","passive_pv_active_weight","seasonal_forecast_weight","seasonal_week_samples","inverter_max_power_w","low_recovery_mode","low_recovery_status","low_recovery_step","low_recovery_phase","rebound_valid_bins","low_recovery_runs","low_recovery_full_ts",
    "full_charge_v","full_transition_v","relaxation_drop_v","full_confidence","transition_confidence","battery_reserve",
    "target_reserve","learned_total_need_kwh","learned_battery_gap_kwh","learned_grid_gap_kwh","current_gap_total_kwh",
    "demand_confidence","energy_budget_kwh","energy_budget_state","energy_budget_confidence","planner_reason","pv_charge_state",
    "recovery_state","recovery_need","stored_energy_kwh","usable_capacity_kwh","capacity_confidence",
    "energy_state_confidence","energy_delta_kwh","measurement_quality","measurement_spread_s","typical_gap_kwh",
    "recent_gap_kwh","gap_classification","surplus_available","surplus_power_w","surplus_energy_kwh","surplus_confidence",
    "battery_chemistry","progressive_gamma","progressive_release_factor","battery_power_envelope_w",
    "power_envelope_confidence","planning_confidence","planning_reserve_adjustment","planner_evaluation",
    "horizon_24h_balance_kwh","horizon_48h_balance_kwh","horizon_72h_balance_kwh",
    "full_charge_priority","full_charge_opportunity","chemistry_strategy_state","days_since_full",
    "absorption_elapsed_min","absorption_required_min","absorption_remaining_min","absorption_status","full_anchor_source",
    "calibration_state","blocked_reason","inverter_power_switch","inverter_switch_state","inverter_full_lock_owned","inverter_switch_action",
]


class FlightRecorder:
    """Daily ASC flight recorder. Existing recorder files are never deleted or trimmed."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._ok_path: Path | None = None  # file whose header was already verified
        # Wird an das Feld `events` der ersten geschriebenen Zeile gehängt, damit
        # Neustarts und Neuladen in den Aufzeichnungen sichtbar sind (nicht nur als Lücke).
        self._start_marker: str | None = build_start_marker(
            VERSION, hass.state is CoreState.running, datetime.now().astimezone()
        )

    @property
    def path(self) -> Path:
        """Return today's recorder path using Home Assistant's local date."""
        day = datetime.now().astimezone().date().isoformat()
        return Path(
            self.hass.config.path(
                "adaptive_solar_controller",
                f"ASC_v0.4.6_FlightRecorder_{day}.csv",
            )
        )

    async def async_append(self, row: dict[str, Any]) -> None:
        await self.hass.async_add_executor_job(self._append_sync, row)

    def _append_sync(self, row: dict[str, Any]) -> None:
        if self._start_marker:
            events = str(row.get("events") or "")
            row = {**row, "events": f"{self._start_marker}|{events}" if events else self._start_marker}
            self._start_marker = None
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists() and path.stat().st_size > 0

        if exists and self._ok_path == path:
            pass  # header verified earlier today: no need to re-read it every cycle
        elif exists:
            try:
                with path.open("r", newline="", encoding="utf-8") as f:
                    header = next(csv.reader(f), [])
                if header != FIELDS:
                    # Never overwrite an incompatible file. Preserve it and create
                    # a fresh schema-compatible daily recorder for the same date.
                    suffix = 1
                    archive = path.with_name(path.stem + "_old.csv")
                    while archive.exists():
                        suffix += 1
                        archive = path.with_name(path.stem + f"_old{suffix}.csv")
                    path.replace(archive)
                    exists = False
            except (OSError, StopIteration):
                exists = False

        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in FIELDS})
        self._ok_path = path
