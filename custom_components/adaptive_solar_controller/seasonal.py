from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import math

from homeassistant.core import State
from homeassistant.util import dt as dt_util

from .storage import LearningState


class SeasonalProductionLearner:
    """Learns the real seasonal PV yield from the plant's daily-production sensor.

    Historical recorder states are reduced to one daily maximum. The persistent model
    uses ISO-week buckets so changes in sun elevation are represented much more finely
    than a single monthly average, while neighbouring weeks provide a robust fallback.
    """

    def __init__(self, state: LearningState) -> None:
        self.state = state

    @staticmethod
    def _bucket_key(day: date) -> str:
        return f"w{day.isocalendar().week:02d}"

    def bootstrap_history(self, states: list[State], today: date) -> int:
        daily: dict[date, float] = {}
        for item in states:
            try:
                value = float(item.state)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value) or value < 0:
                continue
            local_day = dt_util.as_local(item.last_updated).date()
            if local_day >= today:
                continue
            daily[local_day] = max(value, daily.get(local_day, 0.0))

        if not daily:
            return 0

        # Rebuild the seasonal baseline once from history. This intentionally does
        # not add duplicate samples on every HA restart.
        buckets: dict[str, dict[str, float]] = {}
        for day, value in sorted(daily.items()):
            self._add_to_bucket(buckets, day, value)
        self.state.seasonal_buckets = buckets
        self.state.seasonal_history_days = len(daily)
        self.state.seasonal_history_bootstrapped = True
        return len(daily)

    def observe_daily_total(self, now: datetime, value_kwh: float | None) -> None:
        if value_kwh is None or not math.isfinite(value_kwh) or value_kwh < 0:
            return
        day = now.date().isoformat()
        if self.state.seasonal_day is None:
            self.state.seasonal_day = day
            self.state.seasonal_current_max_kwh = value_kwh
            return

        if self.state.seasonal_day != day:
            try:
                finished = date.fromisoformat(self.state.seasonal_day)
                previous = self.state.seasonal_current_max_kwh
                if previous >= 0.05:
                    self._add_to_bucket(self.state.seasonal_buckets, finished, previous)
                    self.state.seasonal_history_days += 1
            except ValueError:
                pass
            self.state.seasonal_day = day
            self.state.seasonal_current_max_kwh = value_kwh
        else:
            self.state.seasonal_current_max_kwh = max(
                self.state.seasonal_current_max_kwh, value_kwh
            )

    @staticmethod
    def _add_to_bucket(buckets: dict[str, dict[str, float]], day: date, value: float) -> None:
        key = SeasonalProductionLearner._bucket_key(day)
        bucket = buckets.setdefault(key, {"count": 0.0, "mean": 0.0, "m2": 0.0})
        count = float(bucket.get("count", 0.0)) + 1.0
        mean = float(bucket.get("mean", 0.0))
        m2 = float(bucket.get("m2", 0.0))
        delta = value - mean
        mean += delta / count
        m2 += delta * (value - mean)
        bucket.update(count=count, mean=mean, m2=m2)

    def expectation(self, day: date) -> tuple[float | None, float]:
        """Return expected kWh and confidence for a date.

        Current week is weighted most, adjacent weeks smooth weather/year anomalies.
        """
        week = day.isocalendar().week
        weighted = 0.0
        total_weight = 0.0
        counts = 0.0
        spread_weighted = 0.0

        for offset, weight in ((0, 1.0), (-1, 0.65), (1, 0.65), (-2, 0.30), (2, 0.30)):
            w = ((week - 1 + offset) % 53) + 1
            bucket = self.state.seasonal_buckets.get(f"w{w:02d}")
            if not bucket:
                continue
            count = float(bucket.get("count", 0.0))
            mean = float(bucket.get("mean", 0.0))
            if count <= 0:
                continue
            var = float(bucket.get("m2", 0.0)) / max(1.0, count - 1.0)
            weighted += mean * weight
            total_weight += weight
            counts += count * weight
            spread_weighted += math.sqrt(max(0.0, var)) * weight

        if total_weight <= 0:
            return None, 0.0

        expected = weighted / total_weight
        spread = spread_weighted / total_weight
        count_conf = min(1.0, counts / 24.0)
        spread_conf = 1.0 / (1.0 + spread / max(expected, 1.0))
        confidence = max(0.0, min(1.0, count_conf * spread_conf))
        return expected, confidence

    def today_and_tomorrow(self, now: datetime) -> tuple[float | None, float | None, float]:
        today, c1 = self.expectation(now.date())
        tomorrow, c2 = self.expectation(now.date() + timedelta(days=1))
        return today, tomorrow, min(c1, c2) if today is not None and tomorrow is not None else max(c1, c2)
