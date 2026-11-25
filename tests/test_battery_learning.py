"""Battery learning regressions found in the 24./25.11.2026 flight recorder."""
import sys
import unittest
from datetime import datetime, timedelta

import test_protection_flow  # noqa: F401  (loads the integration with a stubbed HA)

PKG = test_protection_flow.PKG
battery = sys.modules[f"{PKG}.battery"]
storage = sys.modules[f"{PKG}.storage"]
T0 = datetime(2026, 11, 24, 9, 0, 0).astimezone()


def make(**kw):
    st = storage.LearningState()
    for k, v in kw.items():
        setattr(st, k, v)
    return st, battery.BatteryEstimator(st)


def run(est, seconds, *, start, v, a, pv=400.0, out=0.0, low=22.8, step=10):
    now = start
    events = []
    for _ in range(int(seconds / step)):
        now += timedelta(seconds=step)
        est.observe(now=now, battery_v=v, battery_a=a, battery_w=v * a, pv_w=pv, grid_w=0.0,
                    inverter_output_w=out, hard_low_v=low, calibration_enabled=False)
    return now


class FullPeakTests(unittest.TestCase):
    def test_stale_outlier_peak_does_not_pull_learned_value_up(self):
        st, est = make(learned_full_charge_voltage_v=29.4, full_charge_peak_v=29.89, full_charge_samples=11)
        run(est, 1500, start=T0, v=29.0, a=10.0)
        self.assertLessEqual(st.learned_full_charge_voltage_v, 29.4 + 1e-6)
        self.assertLessEqual(st.full_charge_peak_v, 29.0 + 1e-6)

    def test_peak_is_reset_when_the_charge_episode_ends(self):
        st, est = make(learned_full_charge_voltage_v=29.4, full_charge_samples=11)
        now = run(est, 1000, start=T0, v=29.2, a=10.0)
        self.assertGreater(st.full_charge_peak_v, 0.0)
        run(est, 3000, start=now, v=26.0, a=-3.0, pv=0.0)
        self.assertEqual(st.full_charge_peak_v, 0.0)

    def test_peak_step_is_limited(self):
        st, est = make(learned_full_charge_voltage_v=28.0, full_charge_samples=11)
        run(est, 1200, start=T0, v=29.6, a=10.0)
        self.assertLessEqual(st.full_charge_peak_v, 28.0 + battery.BatteryEstimator.FULL_PEAK_STEP_V + 1e-6)


class FullCycleTests(unittest.TestCase):
    def open_cycle(self, **kw):
        base = dict(full_cycle_active=True, last_full_anchor_ts=T0.timestamp(),
                    stored_energy_kwh=8.0, usable_capacity_estimate_kwh=9.5, capacity_samples=4)
        base.update(kw)
        return make(**base)

    def test_short_pv_window_does_not_close_the_full_cycle(self):
        st, est = self.open_cycle(discharge_since_full_kwh=1.0)
        est._learn_partial_capacity_lower_bound([])
        self.assertTrue(st.full_cycle_active)
        self.assertEqual(st.discharge_since_full_kwh, 1.0)

    def test_charging_inside_open_cycle_reduces_net_discharge(self):
        st, est = self.open_cycle(discharge_since_full_kwh=1.0, stored_energy_kwh=5.0)
        est._integrate_energy(3600.0, 25.0, 8.0, 9.5, True)   # +0.2 kWh
        self.assertAlmostEqual(st.discharge_since_full_kwh, 0.8, places=3)

    def test_net_discharge_never_negative(self):
        st, est = self.open_cycle(discharge_since_full_kwh=0.05, stored_energy_kwh=5.0)
        est._integrate_energy(3600.0, 25.0, 8.0, 9.5, True)
        self.assertEqual(st.discharge_since_full_kwh, 0.0)

    def test_low_anchor_not_rejected_for_a_fresh_open_cycle(self):
        st, est = self.open_cycle(discharge_since_full_kwh=4.0, last_full_anchor_ts=__import__("time").time() - 3600)
        events = []
        for _ in range(12):
            est._learn_low_anchor(10.0, 22.9, -3.5, 70.0, 22.8, True, events)
        self.assertNotIn("LOW_ANCHOR_REJECTED_NO_FULL", events)

    def test_stale_full_anchor_is_rejected(self):
        st, est = self.open_cycle(last_full_anchor_ts=__import__("time").time() - 6 * 24 * 3600)
        events = []
        for _ in range(12):
            est._learn_low_anchor(10.0, 22.9, -3.5, 70.0, 22.8, True, events)
        self.assertIn("LOW_ANCHOR_REJECTED_NO_FULL", events)


class ResetFullVoltageTests(unittest.TestCase):
    def test_reset_clears_outlier_and_samples(self):
        c = test_protection_flow.make()
        c.async_request_refresh = lambda: __import__("asyncio").sleep(0)
        c.controller.reset_transient = lambda: None
        st = c.controller.state
        st.learned_full_charge_voltage_v, st.full_charge_peak_v, st.full_charge_samples = 29.89, 29.89, 11
        test_protection_flow.run(c.async_reset_full_voltage())
        self.assertEqual(st.full_charge_samples, 0)
        self.assertEqual(st.full_charge_peak_v, 0.0)
        self.assertLess(st.learned_full_charge_voltage_v, 29.0)


if __name__ == "__main__":
    unittest.main()
