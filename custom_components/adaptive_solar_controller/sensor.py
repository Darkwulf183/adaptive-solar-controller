from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfElectricPotential, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AUTHORS, DOMAIN, VERSION


@dataclass(frozen=True, kw_only=True)
class ASCSensorDescription(SensorEntityDescription):
    data_key: str


SENSORS = [
    ASCSensorDescription(key="absorption_elapsed", name="FULL absorption elapsed", native_unit_of_measurement="min", icon="mdi:timer-sand", data_key="absorption_elapsed_min"),
    ASCSensorDescription(key="absorption_remaining", name="FULL absorption remaining", native_unit_of_measurement="min", icon="mdi:timer-alert-outline", data_key="absorption_remaining_min"),
    ASCSensorDescription(key="absorption_status", name="FULL absorption status", icon="mdi:battery-clock", data_key="absorption_status"),
    ASCSensorDescription(key="full_anchor_source", name="FULL anchor source", icon="mdi:source-branch", data_key="full_anchor_source"),
    # Fast controller
    ASCSensorDescription(key="recommended_target", name="Recommended target", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:solar-power", data_key="recommended_w"),
    ASCSensorDescription(key="applied_target", name="Applied target", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:transmission-tower-export", data_key="applied_w"),
    ASCSensorDescription(key="effective_limit", name="Effective inverter limit", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:speedometer", data_key="effective_limit_w"),
    ASCSensorDescription(key="grid_error", name="Grid target error", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:transmission-tower", data_key="grid_error_w"),
    ASCSensorDescription(key="raw_target", name="Theoretical raw target", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:calculator-variant-outline", data_key="raw_target_w"),
    ASCSensorDescription(key="export_escalation", name="Export escalation", icon="mdi:transmission-tower-export", data_key="export_escalation"),
    ASCSensorDescription(key="deadband_negative", name="Adaptive deadband export side", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:arrow-collapse-left", data_key="deadband_negative_w"),
    ASCSensorDescription(key="deadband_positive", name="Adaptive deadband import side", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:arrow-collapse-right", data_key="deadband_positive_w"),
    ASCSensorDescription(key="deadband_maturity", name="Deadband learning maturity", native_unit_of_measurement=PERCENTAGE, icon="mdi:waveform", data_key="deadband_maturity"),
    ASCSensorDescription(key="minimum_useful_delta", name="Learned minimum useful target change", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:delta", data_key="minimum_useful_delta_w"),
    ASCSensorDescription(key="jump_confidence", name="Jump response confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:chart-bell-curve-cumulative", data_key="jump_confidence"),
    ASCSensorDescription(key="jump_target", name="Learned jump target", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:lightning-bolt", data_key="jump_target_w"),
    ASCSensorDescription(key="response_learning_eligible", name="Response learning eligible", icon="mdi:school-outline", data_key="response_learning_eligible"),
    ASCSensorDescription(key="saturation_reason", name="Response learning skip reason", icon="mdi:filter-off-outline", data_key="saturation_reason"),
    ASCSensorDescription(key="response_samples", name="Response learning samples", icon="mdi:counter", data_key="response_samples"),
    ASCSensorDescription(key="learned_gain", name="Learned response gain", icon="mdi:tune-vertical", data_key="gain"),

    # Load estimator / prediction
    ASCSensorDescription(key="predicted_load", name="Predicted load", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:chart-timeline-variant-shimmer", data_key="predicted_load_w"),
    ASCSensorDescription(key="current_load", name="Estimated house load", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:home-lightning-bolt", data_key="current_load_w"),
    ASCSensorDescription(key="confidence", name="Prediction confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:percent", data_key="confidence"),
    ASCSensorDescription(key="prediction_maturity", name="Prediction maturity", icon="mdi:sprout", data_key="prediction_maturity"),
    ASCSensorDescription(key="prediction_eval_samples", name="Prediction validation samples", icon="mdi:counter", data_key="prediction_eval_samples"),
    ASCSensorDescription(key="learning_samples", name="Learning samples", icon="mdi:brain", data_key="samples"),
    ASCSensorDescription(key="learned_buckets", name="Learned time buckets", icon="mdi:calendar-clock", data_key="bucket_count"),

    # Forecast / seasonal estimator
    ASCSensorDescription(key="forecast_trust", name="Solar forecast trust", native_unit_of_measurement=PERCENTAGE, icon="mdi:weather-partly-cloudy", data_key="forecast_trust"),
    ASCSensorDescription(key="forecast_bias", name="Solar forecast correction factor", icon="mdi:scale-balance", data_key="forecast_bias"),
    ASCSensorDescription(key="forecast_reputation", name="Solar forecast reputation", icon="mdi:shield-sun", data_key="forecast_reputation"),
    ASCSensorDescription(key="corrected_forecast_remaining", name="Corrected PV forecast remaining today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:solar-power", data_key="corrected_forecast_remaining_kwh"),
    ASCSensorDescription(key="corrected_forecast_tomorrow", name="Corrected PV forecast tomorrow", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:weather-sunset-up", data_key="corrected_forecast_tomorrow_kwh"),
    ASCSensorDescription(key="seasonal_expected_today", name="Seasonal expected PV today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:calendar-sun", data_key="seasonal_expected_today_kwh"),
    ASCSensorDescription(key="seasonal_expected_tomorrow", name="Seasonal expected PV tomorrow", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:calendar-arrow-right", data_key="seasonal_expected_tomorrow_kwh"),
    ASCSensorDescription(key="seasonal_confidence", name="Seasonal confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:calendar-check", data_key="seasonal_confidence"),
    ASCSensorDescription(key="seasonal_history_days", name="Seasonal history days", icon="mdi:calendar-range", data_key="seasonal_history_days"),
    ASCSensorDescription(key="hard_cutoff_status", name="Battery hard cutoff status", icon="mdi:battery-alert", data_key="hard_cutoff_status"),
    ASCSensorDescription(key="hard_cutoff_voltage", name="Battery hard cutoff voltage", native_unit_of_measurement="V", icon="mdi:battery-alert", data_key="hard_cutoff_voltage_v"),
    ASCSensorDescription(key="low_recovery_phase", name="LOW recovery phase", icon="mdi:timer-sand", data_key="low_recovery_phase"),
    ASCSensorDescription(key="low_recovery_remaining", name="LOW recovery remaining", native_unit_of_measurement="s", icon="mdi:timer-outline", data_key="low_recovery_remaining_s"),
    ASCSensorDescription(key="rebound_valid_bins", name="Rebound valid power bins", icon="mdi:chart-bell-curve", data_key="rebound_valid_bins"),
    ASCSensorDescription(key="rebound_predicted_sag", name="Rebound predicted voltage sag", native_unit_of_measurement="V", icon="mdi:chart-line", data_key="rebound_predicted_sag_v"),
    ASCSensorDescription(key="low_recovery_status", name="LOW recovery status", icon="mdi:battery-sync", data_key="low_recovery_status"),
    ASCSensorDescription(key="low_recovery_step", name="LOW recovery step", icon="mdi:counter", data_key="low_recovery_step"),
    ASCSensorDescription(key="low_recovery_runs", name="LOW recovery successful runs", icon="mdi:chart-bell-curve-cumulative", data_key="low_recovery_runs"),

    # Battery full/transition anchors
    ASCSensorDescription(key="battery_full_confidence", name="Battery full confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-check", data_key="battery_full_confidence"),
    ASCSensorDescription(key="full_charge_voltage", name="Learned full charge voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, icon="mdi:battery-charging-high", data_key="learned_full_charge_voltage_v"),
    ASCSensorDescription(key="full_transition_voltage", name="Learned full transition voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, icon="mdi:battery-arrow-down-outline", data_key="learned_full_transition_voltage_v"),
    ASCSensorDescription(key="relaxation_drop", name="Battery full relaxation drop", native_unit_of_measurement=UnitOfElectricPotential.VOLT, icon="mdi:arrow-collapse-down", data_key="battery_relaxation_drop_v"),
    ASCSensorDescription(key="transition_confidence", name="Full transition confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-sync", data_key="transition_confidence"),
    ASCSensorDescription(key="battery_reserve", name="Estimated battery reserve", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-60", data_key="battery_reserve_fraction"),
    ASCSensorDescription(key="battery_recovery_state", name="Battery recovery state", icon="mdi:battery-heart-variant", data_key="battery_recovery_state"),
    ASCSensorDescription(key="battery_recovery_need", name="Battery recovery need", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-alert-variant-outline", data_key="battery_recovery_need"),
    ASCSensorDescription(key="pv_charge_state", name="PV charge phase", icon="mdi:battery-charging", data_key="pv_charge_state"),
    ASCSensorDescription(key="calibration_state", name="Battery calibration state", icon="mdi:battery-sync-outline", data_key="calibration_state"),

    # Total demand learner / planner
    ASCSensorDescription(key="expected_total_need", name="Learned total energy until next PV charge", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:home-clock", data_key="expected_total_need_kwh"),
    ASCSensorDescription(key="learned_battery_gap", name="Learned battery energy until next PV charge", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:battery-minus", data_key="learned_battery_gap_kwh"),
    ASCSensorDescription(key="learned_grid_gap", name="Learned grid energy until next PV charge", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:transmission-tower-import", data_key="learned_grid_gap_kwh"),
    ASCSensorDescription(key="current_gap_total", name="Current energy since PV charge end", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:counter", data_key="current_gap_total_kwh"),
    ASCSensorDescription(key="battery_demand_confidence", name="Energy demand learning confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:chart-box-outline", data_key="battery_demand_confidence"),
    ASCSensorDescription(key="energy_budget", name="Battery energy budget", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:battery-clock", data_key="energy_budget_kwh"),
    ASCSensorDescription(key="energy_budget_state", name="Battery energy budget state", icon="mdi:battery-sync-outline", data_key="energy_budget_state"),
    ASCSensorDescription(key="energy_budget_confidence", name="Battery energy budget confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:percent-circle-outline", data_key="energy_budget_confidence"),
    ASCSensorDescription(key="target_reserve", name="Target reserve at next PV charge", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-arrow-down-outline", data_key="target_reserve_fraction"),
    ASCSensorDescription(key="planner_reason", name="Energy planner reason", icon="mdi:clipboard-text-clock-outline", data_key="planner_reason"),

    # Persistent Home Assistant Energy Dashboard battery counters
    ASCSensorDescription(key="battery_energy_charged_total", name="Battery Energy Charged Total", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:battery-plus", data_key="battery_energy_charged_total_kwh"),
    ASCSensorDescription(key="battery_energy_discharged_total", name="Battery Energy Discharged Total", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:battery-minus", data_key="battery_energy_discharged_total_kwh"),

    # ASC v0.4.2 integrated battery energy / universal energy release
    ASCSensorDescription(key="stored_energy", name="Estimated stored battery energy", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:battery", data_key="stored_energy_kwh"),
    ASCSensorDescription(key="usable_capacity", name="Learned usable battery capacity", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:battery-heart-variant", data_key="usable_capacity_kwh"),
    ASCSensorDescription(key="capacity_confidence", name="Battery capacity confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-check-outline", data_key="capacity_confidence"),
    ASCSensorDescription(key="energy_state_confidence", name="Battery energy state confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-sync", data_key="energy_state_confidence"),
    ASCSensorDescription(key="energy_delta", name="Battery energy delta last sample", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:delta", data_key="energy_delta_kwh"),
    ASCSensorDescription(key="measurement_quality", name="Battery measurement quality", icon="mdi:chart-timeline-variant", data_key="measurement_quality"),
    ASCSensorDescription(key="typical_gap_energy", name="Typical energy demand until next PV charge", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:home-lightning-bolt-outline", data_key="typical_gap_kwh"),
    ASCSensorDescription(key="recent_gap_energy", name="Recent energy demand until next PV charge", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:history", data_key="recent_gap_kwh"),
    ASCSensorDescription(key="last_gap_classification", name="Last demand gap classification", icon="mdi:shape-outline", data_key="last_gap_classification"),
    ASCSensorDescription(key="available_surplus_power", name="Available surplus power", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:flash", data_key="available_surplus_power_w"),
    ASCSensorDescription(key="available_surplus_energy", name="Available surplus energy", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:lightning-bolt-circle", data_key="available_surplus_energy_kwh"),
    ASCSensorDescription(key="surplus_confidence", name="Surplus confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:check-decagram-outline", data_key="surplus_confidence"),

    # ASC v0.4.3 strategy / planning intelligence
    ASCSensorDescription(key="progressive_gamma", name="Progressive release gamma", icon="mdi:chart-bell-curve-cumulative", data_key="progressive_gamma"),
    ASCSensorDescription(key="progressive_release_factor", name="Progressive release factor", native_unit_of_measurement=PERCENTAGE, icon="mdi:chart-areaspline", data_key="progressive_release_factor"),
    ASCSensorDescription(key="battery_power_envelope", name="Battery power envelope", native_unit_of_measurement=UnitOfPower.WATT, icon="mdi:battery-arrow-down", data_key="battery_power_envelope_w"),
    ASCSensorDescription(key="power_envelope_confidence", name="Battery power envelope confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-check", data_key="power_envelope_confidence"),
    ASCSensorDescription(key="planning_confidence", name="Planning confidence", native_unit_of_measurement=PERCENTAGE, icon="mdi:brain", data_key="planning_confidence"),
    ASCSensorDescription(key="planning_reserve_adjustment", name="Learned planning reserve adjustment", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-lock", data_key="planning_reserve_adjustment"),
    ASCSensorDescription(key="planner_evaluation", name="Last planner self evaluation", icon="mdi:clipboard-check-outline", data_key="planner_evaluation"),
    ASCSensorDescription(key="horizon_24h_balance", name="Energy horizon 24h balance", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:hours-24", data_key="horizon_24h_balance_kwh"),
    ASCSensorDescription(key="horizon_48h_balance", name="Energy horizon 48h balance", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:calendar-arrow-right", data_key="horizon_48h_balance_kwh"),
    ASCSensorDescription(key="horizon_72h_balance", name="Energy horizon 72h balance", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:calendar-range", data_key="horizon_72h_balance_kwh"),
    ASCSensorDescription(key="full_charge_priority", name="Lead full charge priority", native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-charging-high", data_key="full_charge_priority"),
    ASCSensorDescription(key="full_charge_opportunity", name="Full charge opportunity", icon="mdi:white-balance-sunny", data_key="full_charge_opportunity"),
    ASCSensorDescription(key="chemistry_strategy_state", name="Battery chemistry strategy", icon="mdi:battery-cog", data_key="chemistry_strategy_state"),
    ASCSensorDescription(key="days_since_full", name="Days since battery full", icon="mdi:calendar-clock", data_key="days_since_full"),
    ASCSensorDescription(key="corrected_forecast_today_total", name="Corrected PV forecast today total", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:solar-power", data_key="corrected_forecast_today_total_kwh"),
    ASCSensorDescription(key="actual_pv_today", name="Actual PV production today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:solar-panel-large", data_key="actual_pv_today_kwh"),

    # Diagnostics
    ASCSensorDescription(key="flight_recorder_path", name="Flight recorder file", icon="mdi:file-delimited-outline", data_key="flight_recorder_path"),
    ASCSensorDescription(key="events", name="ASC event marker", icon="mdi:flag-outline", data_key="events"),
    ASCSensorDescription(key="controller_state", name="Controller state", icon="mdi:information-outline", data_key="status"),
    ASCSensorDescription(key="blocked_reason", name="Blocked reason", icon="mdi:shield-alert-outline", data_key="blocked_reason"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AdaptiveSolarSensor(c, entry, d) for d in SENSORS])


class AdaptiveSolarSensor(CoordinatorEntity, SensorEntity):
    entity_description: ASCSensorDescription

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Adaptive Solar Controller",
            "manufacturer": AUTHORS, "model": f"ASC v{VERSION}",
        }

    @property
    def native_value(self):
        return None if not self.coordinator.data else self.coordinator.data.get(self.entity_description.data_key)
