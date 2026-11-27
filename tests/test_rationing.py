"""v0.4.9: with several poor days ahead the battery budget is spread, not spent at full power in the first evening."""
import sys
import unittest
from datetime import datetime

import test_protection_flow  # noqa: F401

PKG = test_protection_flow.PKG
planner = sys.modules[f"{PKG}.planner"]
battery = sys.modules[f"{PKG}.battery"]
storage = sys.modules[f"{PKG}.storage"]


def est(**kw):
    base = dict(full_charge_voltage_v=29.4, full_transition_voltage_v=25.3, relaxation_drop_v=4.1, full_confidence=0.7,
                transition_confidence=1.0, reserve_fraction=0.95, recovery_need=0.0, recovery_state="normal",
                learned_total_gap_kwh=27.9, learned_battery_gap_kwh=20.0, learned_grid_gap_kwh=7.9,
                current_gap_total_kwh=0.0, demand_confidence=1.0, pv_charge_state="gap", calibration_state="off",
                calibration_complete=False, stored_energy_kwh=9.0, usable_capacity_kwh=9.5, capacity_confidence=1.0,
                energy_state_confidence=0.9, energy_delta_kwh=0.0, measurement_quality="synced", typical_gap_kwh=1.0,
                recent_gap_kwh=1.0, last_gap_classification="normal", events=())
    base.update(kw)
    return battery.BatteryEstimate(**base)


def plan(tomorrow_kwh, seasonal_kwh):
    st = storage.LearningState()
    st.battery_chemistry = "lead_acid"
    p = planner.EnergyPlanner(st)
    return p.plan(battery=est(), battery_a=-5.0, corrected_remaining_kwh=0.3, corrected_tomorrow_kwh=tomorrow_kwh,
                  forecast_trust=0.6, seasonal_today_kwh=1.0, seasonal_tomorrow_kwh=seasonal_kwh,
                  seasonal_confidence=0.6, calibration_enabled=False, planning_confidence=0.6)


class RationingFunction(unittest.TestCase):
    def test_budget_is_spread_over_the_hours_until_recharge(self):
        w, h = planner.rationing_limit_w(5.0, datetime(2026, 11, 24, 13, 0).astimezone(), deficit_days=0)
        self.assertAlmostEqual(h, 21.0, places=2)
        self.assertAlmostEqual(w, 5000 / 21.0, places=1)

    def test_every_poor_day_adds_24_hours(self):
        _, h0 = planner.rationing_limit_w(5.0, datetime(2026, 11, 24, 13, 0).astimezone(), 0)
        _, h2 = planner.rationing_limit_w(5.0, datetime(2026, 11, 24, 13, 0).astimezone(), 2)
        self.assertAlmostEqual(h2 - h0, 48.0, places=2)

    def test_morning_before_pv_uses_the_same_day(self):
        _, h = planner.rationing_limit_w(2.0, datetime(2026, 11, 25, 6, 0).astimezone(), 0)
        self.assertAlmostEqual(h, 6.0, places=2)  # also the minimum horizon

    def test_empty_budget_gives_zero_watts(self):
        w, _ = planner.rationing_limit_w(0.0, datetime(2026, 11, 24, 18, 0).astimezone(), 2)
        self.assertEqual(w, 0.0)


class PlannerIntegration(unittest.TestCase):
    def test_several_poor_days_activate_rationing(self):
        p = plan(tomorrow_kwh=0.7, seasonal_kwh=0.9)
        self.assertLess(p.horizon_48h_balance_kwh, 0)
        self.assertIsNotNone(p.rationing_limit_w)
        self.assertLess(p.rationing_limit_w, 300.0)

    def test_good_forecast_does_not_ration(self):
        p = plan(tomorrow_kwh=40.0, seasonal_kwh=40.0)
        self.assertIsNone(p.rationing_limit_w)


if __name__ == "__main__":
    unittest.main()
