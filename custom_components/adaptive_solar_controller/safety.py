"""Debounce logic for the battery under-voltage latch (no Home Assistant imports).

Why: a single glitchy sample (or a briefly unavailable sensor) must not switch the
inverter off, but a real deep discharge must still trip quickly.

Rules (all times in seconds, monotonic clock supplied by the caller):
* terminal voltage far below the emergency floor  -> trip immediately
* voltage at/below a limit                        -> trip after `confirm_s` AND `min_samples`
* voltage unavailable / not finite                -> trip after `invalid_confirm_s`
"""
from __future__ import annotations

import math

OK = "ok"
PENDING = "undervoltage_pending"
INVALID_PENDING = "sensor_invalid_pending"
TRIP = "trip_undervoltage"
TRIP_EMERGENCY = "trip_emergency"
TRIP_INVALID = "trip_sensor_invalid"

TRIP_RESULTS = (TRIP, TRIP_EMERGENCY, TRIP_INVALID)


class UndervoltageGuard:
    def __init__(
        self,
        confirm_s: float = 10.0,
        min_samples: int = 2,
        immediate_margin_v: float = 1.0,
        invalid_confirm_s: float = 120.0,
    ) -> None:
        self.confirm_s = confirm_s
        self.min_samples = min_samples
        self.immediate_margin_v = immediate_margin_v
        self.invalid_confirm_s = invalid_confirm_s
        self.reset()

    def reset(self) -> None:
        self._under_since: float | None = None
        self._under_samples = 0
        self._invalid_since: float | None = None

    def evaluate(
        self,
        now_s: float,
        battery_v: float | None,
        relaxed_v: float | None,
        cutoff_v: float,
        emergency_v: float,
    ) -> str:
        if battery_v is None or not math.isfinite(battery_v):
            self._under_since = None
            self._under_samples = 0
            if self._invalid_since is None:
                self._invalid_since = now_s
            if now_s - self._invalid_since >= self.invalid_confirm_s:
                return TRIP_INVALID
            return INVALID_PENDING

        self._invalid_since = None
        if relaxed_v is None or not math.isfinite(relaxed_v):
            relaxed_v = battery_v

        if battery_v <= emergency_v - self.immediate_margin_v:
            return TRIP_EMERGENCY

        if relaxed_v <= cutoff_v or battery_v <= emergency_v:
            if self._under_since is None:
                self._under_since = now_s
                self._under_samples = 0
            self._under_samples += 1
            if self._under_samples >= self.min_samples and now_s - self._under_since >= self.confirm_s:
                return TRIP
            return PENDING

        self._under_since = None
        self._under_samples = 0
        return OK
