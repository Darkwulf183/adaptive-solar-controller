from __future__ import annotations

DOMAIN = "adaptive_solar_controller"
VERSION = "0.4.6rc4"
PLATFORMS = ["sensor", "select", "switch", "number", "binary_sensor"]

CONF_GRID_SENSOR = "grid_sensor"
CONF_PV_SENSOR = "pv_sensor"
CONF_DAILY_PRODUCTION_SENSOR = "daily_production_sensor"
CONF_BATTERY_VOLTAGE_SENSOR = "battery_voltage_sensor"
CONF_BATTERY_CURRENT_SENSOR = "battery_current_sensor"
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor"
CONF_INVERTER_OUTPUT_SENSOR = "inverter_output_sensor"
CONF_TARGET_HELPER = "target_helper"
CONF_BATTERY_LOW_HELPER = "battery_low_helper"
CONF_BACKUP_INVERTER = "backup_inverter"
CONF_SOLAR_ENABLE = "solar_enable"
CONF_INVERTER_POWER_SWITCH = "inverter_power_switch"
CONF_GRID_TARGET = "grid_target"
CONF_BACKUP_BLOCK_W = "backup_block_w"
CONF_MIN_TARGET_W = "min_target_w"
CONF_MAX_STEP_W = "max_step_w"
CONF_HARD_MAX_W = "hard_max_w"
CONF_ABSORPTION_V = "absorption_voltage_v"
CONF_ABSORPTION_TOLERANCE_V = "absorption_tolerance_v"
CONF_ABSORPTION_MINUTES = "absorption_minutes"

# Optional Forecast.Solar inputs. ASC learns how much it can trust them.
CONF_FORECAST_POWER_NOW = "forecast_power_now"
CONF_FORECAST_POWER_NEXT_HOUR = "forecast_power_next_hour"
CONF_FORECAST_ENERGY_NEXT_HOUR = "forecast_energy_next_hour"
CONF_FORECAST_ENERGY_TODAY = "forecast_energy_today"
CONF_FORECAST_ENERGY_REMAINING = "forecast_energy_remaining"
CONF_FORECAST_ENERGY_TOMORROW = "forecast_energy_tomorrow"
CONF_FORECAST_PEAK_TIME_TODAY = "forecast_peak_time_today"

DEFAULTS = {
    CONF_GRID_SENSOR: "sensor.e320_power_in",
    CONF_PV_SENSOR: "sensor.solar_watt_aktuell",
    CONF_DAILY_PRODUCTION_SENSOR: "sensor.solar_tageserzeugung",
    CONF_BATTERY_VOLTAGE_SENSOR: "sensor.solar_average_voltage",
    CONF_BATTERY_CURRENT_SENSOR: "sensor.solar_complete_ampere",
    CONF_BATTERY_POWER_SENSOR: "",
    CONF_INVERTER_OUTPUT_SENSOR: "sensor.apsystems_output_average",
    CONF_TARGET_HELPER: "input_number.inverter_target_power",
    CONF_BATTERY_LOW_HELPER: "input_number.battery_voltage_low",
    CONF_BACKUP_INVERTER: "number.ez1_backup_apsystems_ez1_backup_max_output_power",
    CONF_SOLAR_ENABLE: "switch.input_solar",
    CONF_INVERTER_POWER_SWITCH: "",
    CONF_GRID_TARGET: 15.0,
    CONF_BACKUP_BLOCK_W: 40.0,
    CONF_MIN_TARGET_W: 30.0,
    CONF_MAX_STEP_W: 180.0,
    CONF_HARD_MAX_W: 660.0,
    CONF_ABSORPTION_V: 29.4,
    CONF_ABSORPTION_TOLERANCE_V: 0.4,
    CONF_ABSORPTION_MINUTES: 120.0,
    CONF_FORECAST_POWER_NOW: "sensor.power_production_now_2",
    CONF_FORECAST_POWER_NEXT_HOUR: "sensor.power_production_next_hour_2",
    CONF_FORECAST_ENERGY_NEXT_HOUR: "sensor.energy_next_hour_2",
    CONF_FORECAST_ENERGY_TODAY: "sensor.energy_production_today_2",
    CONF_FORECAST_ENERGY_REMAINING: "sensor.energy_production_today_remaining_2",
    CONF_FORECAST_ENERGY_TOMORROW: "sensor.energy_production_tomorrow_2",
    CONF_FORECAST_PEAK_TIME_TODAY: "sensor.power_highest_peak_time_today_2",
}

MODE_OFF = "off"
MODE_MONITOR = "monitor"
MODE_ADAPTIVE = "adaptive"
MODE_PREDICTIVE = "predictive"
MODES = [MODE_OFF, MODE_MONITOR, MODE_ADAPTIVE, MODE_PREDICTIVE]

PREDICTION_LEARNING = "learning"
PREDICTION_USABLE = "usable"
PREDICTION_MATURE = "mature"

DEFAULT_BATTERY_STRATEGY_MAX_V = 27.4
MIN_BATTERY_STRATEGY_MAX_V = 23.0
MAX_BATTERY_STRATEGY_MAX_V = 30.0

AUTHORS = "Darkwulf183 & ChatGPT"
