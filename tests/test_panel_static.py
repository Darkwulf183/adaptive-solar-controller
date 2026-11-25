"""Panel must not carry personal entity ids; labels for all switch states must exist."""
import importlib.util
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components" / "adaptive_solar_controller"
JS = (COMP / "frontend" / "asc-panel.js").read_text(encoding="utf-8")


def load(name):
    spec = importlib.util.spec_from_file_location(name, COMP / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = load("panel_config")


class PanelStaticTests(unittest.TestCase):
    def test_no_personal_entity_ids_or_dashboard_path(self):
        for needle in ("sensor.e320", "sensor.solar_average", "sensor.solar_complete", "sensor.solar_watt",
                       "input_number.inverter_target_power", "/dashboard-solar"):
            self.assertNotIn(needle, JS)

    def test_every_non_asc_entity_comes_from_the_config(self):
        ids = set(re.findall(r'"((?:sensor|number|select|switch|binary_sensor|input_number|button)\.[a-z0-9_]+)"', JS))
        foreign = [i for i in ids if "adaptive_solar_controller" not in i]
        self.assertEqual(foreign, [])

    def test_switch_status_labels_exist_for_every_status_the_coordinator_can_return(self):
        src = (COMP / "coordinator.py").read_text(encoding="utf-8")
        body = src[src.index("async def _async_manage_full_lock"):src.index("def _measurement_spread_s")]
        statuses = set(re.findall(r'return "([a-z_]+)"', body))
        statuses |= set(re.findall(r'return (?:await )?[^\n]*"([a-z_]+)"', body))
        missing = sorted(s for s in statuses if not re.search(rf"\b{s}\b", JS))
        self.assertEqual(missing, [], f"no German label in the panel for: {missing}")

    def test_panel_shows_emergency_switch_reset_button_and_status_sensor(self):
        for needle in ("switch.adaptive_solar_controller_emergency_power_reserve",
                       "button.adaptive_solar_controller_reset_learned_full_charge_voltage",
                       "sensor.adaptive_solar_controller_inverter_switch_status"):
            self.assertIn(needle, JS)


class PanelConfigTests(unittest.TestCase):
    def test_configured_entities_are_passed_through(self):
        cfg = {"grid_sensor": "sensor.my_grid", "target_helper": "input_number.t", "battery_voltage_sensor": "sensor.v",
               "battery_current_sensor": "sensor.a", "pv_sensor": "sensor.pv"}
        self.assertEqual(pc.panel_entities(cfg), {"grid": "sensor.my_grid", "target": "input_number.t",
                                                  "battery": "sensor.v", "current": "sensor.a", "pv": "sensor.pv"})

    def test_missing_values_become_empty_strings(self):
        out = pc.panel_entities({"grid_sensor": None})
        self.assertTrue(all(v == "" for v in out.values()))
        self.assertEqual(set(out), {"grid", "target", "battery", "current", "pv"})


if __name__ == "__main__":
    unittest.main()
