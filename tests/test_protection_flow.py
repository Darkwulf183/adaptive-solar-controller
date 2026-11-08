"""Tests der Abschalt- und Sperrlogik des Coordinators mit simuliertem Home Assistant.

Home Assistant ist nicht nötig: die homeassistant-Module werden durch einfache Stubs ersetzt.
Run:  python3 -m unittest discover -s tests -v
"""
import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "adaptive_solar_controller"
PKG = "asc_under_test"


class _Dummy:
    def __init__(self, *a, **k): pass
    def __class_getitem__(cls, item): return cls


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = _Dummy
        setattr(self, name, value)
        return value


class _Notifications:
    def __init__(self): self.created, self.dismissed = [], []
    def async_create(self, hass, message, title=None, notification_id=None): self.created.append(notification_id)
    def async_dismiss(self, hass, notification_id): self.dismissed.append(notification_id)


def _load():
    notes = _Notifications()
    for name in ("homeassistant", "homeassistant.components", "homeassistant.components.recorder",
                 "homeassistant.components.http", "homeassistant.config_entries", "homeassistant.core",
                 "homeassistant.helpers", "homeassistant.helpers.event", "homeassistant.helpers.storage",
                 "homeassistant.helpers.update_coordinator", "homeassistant.util"):
        sys.modules.setdefault(name, _StubModule(name))
    sys.modules["homeassistant.core"].callback = lambda f: f
    sys.modules["homeassistant.components"].persistent_notification = notes
    sys.modules["homeassistant.util"].dt = _StubModule("homeassistant.util.dt")
    sys.modules["homeassistant.util.dt"] = sys.modules["homeassistant.util"].dt
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg
    spec = importlib.util.spec_from_file_location(f"{PKG}.coordinator", ROOT / "coordinator.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.persistent_notification = notes
    return mod, notes


coord_mod, NOTES = _load()
storage = sys.modules[f"{PKG}.storage"]
safety = sys.modules[f"{PKG}.safety"]
switch_confirm = sys.modules[f"{PKG}.switch_confirm"]

SWITCH = "switch.inverter_power"
OLD = "switch.old_name"


class _State:
    def __init__(self, state, attributes=None): self.state, self.attributes = state, attributes or {}


class FakeHass:
    def __init__(self):
        self.states = self
        self.data = {}
        self.calls = []
        self.services = self
        self.follow_command = True   # Schalter folgt dem turn_off-Befehl
        self.fail = False

    def get(self, entity_id): return self.data.get(entity_id)
    def set(self, entity_id, state): self.data[entity_id] = _State(state)

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data["entity_id"]))
        if self.fail:
            raise RuntimeError("boom")
        if service == "turn_off" and self.follow_command:
            self.data[data["entity_id"]] = _State("off")


class _Store:
    async def async_save(self, state): pass


class _Controller:
    def __init__(self):
        self.state = storage.LearningState()
        self.state.battery_chemistry = "lead_acid"
        self.enabled = True


def make(switch_state="on"):
    c = object.__new__(coord_mod.AdaptiveSolarCoordinator)
    c.hass = FakeHass()
    c.hass.set(SWITCH, switch_state)
    c.cfg = {"inverter_power_switch": SWITCH, "solar_enable": "switch.input_solar"}
    c.controller = _Controller()
    c.store = _Store()
    c._safety_lock = asyncio.Lock()
    c._guard = safety.UndervoltageGuard()
    c._cutoff_latched = False
    c._cutoff_notified = False
    c._cutoff_off = switch_confirm.SwitchOffTracker(confirm_after_s=15.0)
    c._lock_off = switch_confirm.SwitchOffTracker(confirm_after_s=15.0)
    c._test_mode = False
    c._test_started = 0.0
    return c


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class Clock:
    """Ersetzt time.monotonic im Coordinator."""
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def advance(self, s): self.t += s


class CutoffFlow(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self._orig = coord_mod.time.monotonic
        coord_mod.time.monotonic = self.clock
        NOTES.created.clear(); NOTES.dismissed.clear()

    def tearDown(self): coord_mod.time.monotonic = self._orig

    def cycle(self, c, v):
        r = run(c._async_manage_cutoff(v, -5.0, 300.0))
        self.clock.advance(10)
        return r

    def test_no_trip_at_normal_voltage(self):
        c = make()
        for _ in range(5): self.assertEqual(self.cycle(c, 25.5), "ok")
        self.assertEqual(c.hass.calls, [])

    def test_trip_debounced_and_switch_off_confirmed(self):
        c = make()
        results = [self.cycle(c, 22.5) for _ in range(4)]
        self.assertIn(("switch", "turn_off", SWITCH), c.hass.calls)
        self.assertEqual(c.hass.get(SWITCH).state, "off")
        self.assertTrue(c._cutoff_latched)
        self.assertIn("cutoff_switch_off_sent", results)
        self.assertIn("cutoff_switch_off_confirmed", results)
        self.assertEqual(self.cycle(c, 22.5), "cutoff_latched")

    def test_stuck_switch_is_retried_and_alerted(self):
        c = make()
        c.hass.follow_command = False       # Schalter bleibt 'on'
        statuses = [self.cycle(c, 22.5) for _ in range(14)]
        sends = [x for x in c.hass.calls if x[1] == "turn_off"]
        self.assertGreaterEqual(len(sends), 3)
        self.assertIn("asc_switch_off_unconfirmed", NOTES.created)
        self.assertIn("cutoff_switch_off_pending", statuses)
        self.assertIn("cutoff_switch_off_unconfirmed", statuses)

    def test_unavailable_switch_is_reported_not_switched(self):
        c = make("unavailable")
        statuses = [self.cycle(c, 22.5) for _ in range(4)]
        self.assertEqual(c.hass.calls, [])
        self.assertIn("cutoff_switch_unavailable", statuses)

    def test_switch_error_is_reported(self):
        c = make()
        c.hass.fail = True
        statuses = [self.cycle(c, 22.5) for _ in range(4)]
        self.assertIn("cutoff_switch_error", statuses)

    def test_invalid_sensor_does_not_switch_immediately(self):
        c = make()
        for _ in range(5):
            self.assertNotIn("cutoff_switch_off_sent", [self.cycle(c, None)])
        self.assertEqual(c.hass.calls, [])


class LockFlow(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self._orig = coord_mod.time.monotonic
        coord_mod.time.monotonic = self.clock
        NOTES.created.clear(); NOTES.dismissed.clear()

    def tearDown(self): coord_mod.time.monotonic = self._orig

    def cycle(self, c, chem="lead_full_emergency", mode="adaptive"):
        r = run(c._async_manage_full_lock(chem, mode))
        self.clock.advance(10)
        return r

    def test_emergency_turns_switch_off_and_confirms(self):
        c = make()
        self.assertEqual(self.cycle(c), "turn_off_sent")
        self.assertTrue(c.controller.state.inverter_full_lock_owned)
        self.assertEqual(self.cycle(c), "turn_off_confirmed")
        self.assertEqual(self.cycle(c), "locked_off")

    def test_slow_switch_is_not_mistaken_for_manual_override(self):
        c = make()
        c.hass.follow_command = False
        self.assertEqual(self.cycle(c), "turn_off_sent")
        self.assertEqual(self.cycle(c), "turn_off_pending")      # noch in der Wartezeit
        c.hass.set(SWITCH, "off")                                # Schalter zieht verspätet nach
        self.assertEqual(self.cycle(c), "turn_off_confirmed")
        self.assertTrue(c.controller.state.inverter_full_lock_owned)

    def test_stuck_switch_alerts(self):
        c = make()
        c.hass.follow_command = False
        statuses = [self.cycle(c) for _ in range(14)]
        self.assertIn("turn_off_retry", statuses)
        self.assertIn("turn_off_unconfirmed", statuses)
        self.assertIn("asc_switch_off_unconfirmed", NOTES.created)

    def test_manual_switch_on_during_lock_is_noticed_then_locked_again(self):
        c = make()
        self.cycle(c); self.cycle(c)                              # abgeschaltet und bestätigt
        c.hass.set(SWITCH, "on")                                  # Benutzer schaltet ein
        self.assertEqual(self.cycle(c), "manual_override_on")
        self.assertFalse(c.controller.state.inverter_full_lock_owned)
        self.assertEqual(self.cycle(c), "turn_off_sent")          # Notfallregel greift erneut

    def test_renamed_switch_stale_owner_released_then_locked(self):
        c = make("on")
        c.controller.state.inverter_full_lock_owned = True
        c.controller.state.inverter_full_lock_entity = OLD
        self.assertEqual(self.cycle(c), "stale_owner_released")
        self.assertEqual(self.cycle(c), "turn_off_sent")
        self.assertEqual(c.controller.state.inverter_full_lock_entity, SWITCH)

    def test_renamed_switch_already_off_is_adopted_without_commands(self):
        c = make("off")
        c.controller.state.inverter_full_lock_owned = True
        c.controller.state.inverter_full_lock_entity = OLD
        self.assertEqual(self.cycle(c), "owner_switch_adopted")
        self.assertEqual(c.hass.calls, [])
        self.assertEqual(self.cycle(c), "locked_off")

    def test_monitor_mode_never_switches(self):
        c = make()
        self.assertEqual(self.cycle(c, mode="monitor"), "monitor_no_action")
        self.assertEqual(c.hass.calls, [])

    def test_unavailable_switch_is_reported(self):
        c = make("unavailable")
        self.assertEqual(self.cycle(c), "switch_unavailable")
        self.assertEqual(c.hass.calls, [])

    def test_release_only_after_confirmed_full(self):
        c = make("off")
        c.controller.state.inverter_full_lock_owned = True
        c.controller.state.inverter_full_lock_entity = SWITCH
        self.assertEqual(self.cycle(c, chem="lead_daily_full"), "awaiting_confirmed_full")
        self.assertEqual(c.hass.calls, [])


class TrackerUnit(unittest.TestCase):
    def test_states(self):
        t = switch_confirm.SwitchOffTracker(confirm_after_s=15, alert_after_attempts=3)
        self.assertEqual(t.observe("on", 0), "idle")
        t.sent(0)
        self.assertEqual(t.observe("on", 5), "pending")
        self.assertEqual(t.observe("on", 20), "retry")
        self.assertEqual(t.observe("unavailable", 20), "unavailable")
        self.assertEqual(t.observe("off", 21), "confirmed_off")
        self.assertEqual(t.observe("off", 22), "idle")

class TestMode(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self._orig = coord_mod.time.monotonic
        coord_mod.time.monotonic = self.clock
        NOTES.created.clear(); NOTES.dismissed.clear()

    def tearDown(self): coord_mod.time.monotonic = self._orig

    def cycle(self, c, v):
        r = run(c._async_manage_cutoff(v, -8.0, 200.0))
        self.clock.advance(10)
        return r

    def test_normal_mode_24_2_volt_is_fine(self):
        c = make()
        for _ in range(4): self.assertEqual(self.cycle(c, 24.2), "ok")
        self.assertEqual(c.hass.calls, [])

    def test_test_mode_trips_at_raised_cutoff(self):
        c = make()
        c._set_test_mode_state(True)
        self.assertEqual(c._effective_limits(), (24.3, 24.1))
        results = [self.cycle(c, 24.2) for _ in range(4)]
        self.assertIn("cutoff_switch_off_sent", results)
        self.assertEqual(c.hass.get(SWITCH).state, "off")

    def test_test_mode_no_trip_above_raised_cutoff(self):
        c = make()
        c._set_test_mode_state(True)
        for _ in range(5): self.assertEqual(self.cycle(c, 24.5), "ok")
        self.assertEqual(c.hass.calls, [])

    def test_stored_limits_untouched_and_restored(self):
        c = make()
        stored = (c.controller.state.hard_cutoff_voltage_v, c.controller.state.emergency_terminal_voltage_v)
        c._set_test_mode_state(True)
        self.assertEqual((c.controller.state.hard_cutoff_voltage_v, c.controller.state.emergency_terminal_voltage_v), stored)
        c._set_test_mode_state(False)
        self.assertEqual(c._effective_limits(), stored)

    def test_toggle_clears_latch_so_each_test_starts_clean(self):
        c = make()
        c._set_test_mode_state(True)
        for _ in range(4): self.cycle(c, 24.2)
        self.assertTrue(c._cutoff_latched)
        c._set_test_mode_state(False)
        self.assertFalse(c._cutoff_latched)
        self.assertFalse(c.controller.state.hard_cutoff_latched)

    def test_lock_is_suspended_so_inverter_can_be_started(self):
        c = make("on")
        c._set_test_mode_state(True)
        r = run(c._async_manage_full_lock("lead_full_emergency", "adaptive"))
        self.assertEqual(r, "test_mode_lock_suspended")
        self.assertEqual(c.hass.calls, [])

    def test_fixed_output_200w_only_when_regulating(self):
        c = make()
        self.assertEqual(c._test_target(55, "adaptive", 400.0), 55)           # Testmodus aus
        c._set_test_mode_state(True)
        self.assertEqual(c._test_target(55, "adaptive", 400.0), 200)
        self.assertEqual(c._test_target(55, "predictive", 400.0), 200)
        self.assertEqual(c._test_target(None, "monitor", 400.0), None)        # Monitor schreibt nie
        self.assertEqual(c._test_target(55, "adaptive", 150.0), 150)          # nie über Wechselrichter-Maximum
        c._cutoff_latched = True
        self.assertEqual(c._test_target(55, "adaptive", 400.0), 55)           # nach Trip keine Festleistung


if __name__ == "__main__":
    unittest.main()
