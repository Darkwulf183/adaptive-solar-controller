"""Tests for the HA-free parts. Run:  python3 -m unittest discover -s tests -v"""
import importlib.util
import pathlib
import unittest
from datetime import date, datetime

BASE = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "adaptive_solar_controller"


def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


safety = load("safety")
pv = load("passive_pv")
marker = load("start_marker")
lock_owner = load("lock_owner")
TODAY = date(2026, 11, 6)


class GuardTests(unittest.TestCase):
    def guard(self):
        return safety.UndervoltageGuard(confirm_s=10, min_samples=2, immediate_margin_v=1.0, invalid_confirm_s=120)

    def test_normal_voltage_ok(self):
        self.assertEqual(self.guard().evaluate(0, 25.0, 25.0, 22.8, 22.0), safety.OK)

    def test_single_glitch_does_not_trip(self):
        g = self.guard()
        self.assertEqual(g.evaluate(0, 21.9, 21.9, 22.8, 22.0), safety.PENDING)
        self.assertEqual(g.evaluate(3, 25.0, 25.0, 22.8, 22.0), safety.OK)   # recovered
        self.assertEqual(g.evaluate(4, 21.9, 21.9, 22.8, 22.0), safety.PENDING)  # timer restarted

    def test_sustained_undervoltage_trips(self):
        g = self.guard()
        self.assertEqual(g.evaluate(0, 22.5, 22.5, 22.8, 22.0), safety.PENDING)
        self.assertEqual(g.evaluate(5, 22.5, 22.5, 22.8, 22.0), safety.PENDING)
        self.assertEqual(g.evaluate(10, 22.5, 22.5, 22.8, 22.0), safety.TRIP)

    def test_needs_two_samples(self):
        g = self.guard()
        self.assertEqual(g.evaluate(0, 22.5, 22.5, 22.8, 22.0), safety.PENDING)
        self.assertEqual(g.evaluate(60, 22.5, 22.5, 22.8, 22.0), safety.TRIP)
        g2 = self.guard()
        self.assertEqual(g2.evaluate(100, 22.5, 22.5, 22.8, 22.0), safety.PENDING)  # 1 sample only

    def test_deep_emergency_trips_immediately(self):
        self.assertEqual(self.guard().evaluate(0, 20.9, 20.9, 22.8, 22.0), safety.TRIP_EMERGENCY)

    def test_rebound_credit_counts_through_relaxed_voltage(self):
        g = self.guard()
        g.evaluate(0, 23.0, 22.7, 22.8, 22.0)
        self.assertEqual(g.evaluate(10, 23.0, 22.7, 22.8, 22.0), safety.TRIP)

    def test_unavailable_sensor_is_not_zero_volt(self):
        g = self.guard()
        self.assertEqual(g.evaluate(0, None, None, 22.8, 22.0), safety.INVALID_PENDING)
        self.assertEqual(g.evaluate(60, None, None, 22.8, 22.0), safety.INVALID_PENDING)
        self.assertEqual(g.evaluate(120, None, None, 22.8, 22.0), safety.TRIP_INVALID)

    def test_sensor_back_resets_invalid_timer(self):
        g = self.guard()
        g.evaluate(0, None, None, 22.8, 22.0)
        self.assertEqual(g.evaluate(60, 25.0, 25.0, 22.8, 22.0), safety.OK)
        self.assertEqual(g.evaluate(100, None, None, 22.8, 22.0), safety.INVALID_PENDING)

    def test_nan_counts_as_invalid(self):
        self.assertEqual(self.guard().evaluate(0, float("nan"), None, 22.8, 22.0), safety.INVALID_PENDING)


class CsvTests(unittest.TestCase):
    HEAD = "entity_id,state,last_changed\n"

    def test_daily_max_with_midnight_reset(self):
        csv = self.HEAD + (
            "sensor.solar_tageserzeugung,9.0,2025-06-01T10:00:00.000Z\n"
            "sensor.solar_tageserzeugung,0.0,2025-06-01T22:00:00.000Z\n"   # = 00:00 local 2 June
            "sensor.solar_tageserzeugung,3.1,2025-06-02T16:00:00.000Z\n"
            "sensor.solar_tageserzeugung,unavailable,2025-06-02T16:01:00.000Z\n")
        out = pv.parse_csv(csv, "Europe/Berlin", TODAY, "sensor.solar_tageserzeugung")
        self.assertEqual(out, {"2025-06-01": 9.0, "2025-06-02": 3.1})

    def test_renamed_single_sensor_export_is_accepted(self):
        csv = self.HEAD + "sensor.pv_energy_today,4.2,2025-06-02T16:00:00.000Z\n"
        self.assertEqual(pv.parse_csv(csv, "Europe/Berlin", TODAY, "sensor.solar_tageserzeugung"), {"2025-06-02": 4.2})

    def test_several_entities_without_match_rejected(self):
        csv = self.HEAD + "sensor.a,1,2025-06-02T16:00:00Z\nsensor.b,2,2025-06-02T16:00:00Z\n"
        with self.assertRaises(ValueError):
            pv.parse_csv(csv, "Europe/Berlin", TODAY, "sensor.solar_tageserzeugung")

    def test_configured_entity_selected_among_several(self):
        csv = self.HEAD + "sensor.a,1,2025-06-02T16:00:00Z\nsensor.solar_tageserzeugung,2,2025-06-02T16:00:00Z\n"
        self.assertEqual(pv.parse_csv(csv, "Europe/Berlin", TODAY, "sensor.solar_tageserzeugung"), {"2025-06-02": 2.0})

    def test_today_and_future_ignored(self):
        csv = self.HEAD + "sensor.x,5,2026-11-06T10:00:00Z\n"
        with self.assertRaises(ValueError):
            pv.parse_csv(csv, "Europe/Berlin", TODAY, "sensor.x")

    def test_estimate_uses_seasonal_window_not_whole_month(self):
        days = {f"2025-06-{i:02d}": float(i) for i in range(1, 31)}
        early = pv.estimate(days, date(2026, 6, 1))
        late = pv.estimate(days, date(2026, 6, 30))
        self.assertLess(early, late)
        self.assertAlmostEqual(early, 4.5, places=1)   # mean of days 1..8

    def test_estimate_falls_back_to_month(self):
        self.assertEqual(pv.estimate({"2025-06-10": 10.0, "2025-06-20": 20.0}, date(2026, 6, 15)), 15.0)
        self.assertIsNone(pv.estimate({}, date(2026, 6, 15)))

class StartMarkerTests(unittest.TestCase):
    NOW = datetime(2026, 11, 8, 16, 12, 41)

    def test_ha_start(self):
        self.assertEqual(marker.build_start_marker("0.4.7", False, self.NOW), "ASC_START:0.4.7:ha_start@16:12:41")

    def test_reload(self):
        self.assertEqual(marker.build_start_marker("0.4.7", True, self.NOW), "ASC_START:0.4.7:setup_or_reload@16:12:41")

    def test_does_not_break_event_separators(self):
        m = marker.build_start_marker("0.4.7", False, self.NOW)
        self.assertNotIn(",", m)
        self.assertNotIn("|", m)

class LockOwnerTests(unittest.TestCase):
    R = staticmethod(lambda *a: lock_owner.reconcile_lock_owner(*a))

    def test_not_owned_changes_nothing(self):
        self.assertEqual(self.R(False, "", "switch.a", "on")[0], "not_owned")

    def test_same_entity(self):
        self.assertEqual(self.R(True, "switch.a", "switch.a", "off"), ("same", True, "switch.a"))

    def test_renamed_switch_is_off_adopted(self):
        self.assertEqual(self.R(True, "switch.old", "switch.new", "off"), ("owner_switch_adopted", True, "switch.new"))

    def test_renamed_switch_is_on_marker_dropped(self):
        self.assertEqual(self.R(True, "switch.old", "switch.new", "on"), ("stale_owner_released", False, ""))

    def test_empty_stored_entity_is_treated_as_changed(self):
        self.assertEqual(self.R(True, "", "switch.new", "on")[0], "stale_owner_released")

    def test_unavailable_switch_waits(self):
        for st in ("unavailable", "unknown", None):
            self.assertEqual(self.R(True, "switch.old", "switch.new", st), ("owner_switch_pending", True, "switch.old"))


if __name__ == "__main__":
    unittest.main()
