from __future__ import annotations

from datetime import datetime
import math

from .storage import LearningState


class SolarForecastLearner:
    """Learns bias and trust of Forecast.Solar against the real PV plant."""

    def __init__(self, state: LearningState) -> None:
        self.state = state

    def observe(self, now: datetime, actual_pv_w: float, forecast_now_w: float | None, forecast_today_kwh: float | None) -> None:
        ts = now.timestamp()
        day = now.date().isoformat()

        if self.state.forecast_day is None:
            self.state.forecast_day = day
            self.state.last_pv_ts = ts

        if self.state.forecast_day != day:
            self._finish_day()
            self.state.forecast_day = day
            self.state.actual_pv_today_kwh = 0.0
            self.state.forecast_today_anchor_kwh = None
            self.state.last_pv_ts = ts

        if self.state.last_pv_ts is not None and math.isfinite(actual_pv_w):
            dt = max(0.0, min(90.0, ts - self.state.last_pv_ts))
            self.state.actual_pv_today_kwh += max(0.0, actual_pv_w) * dt / 3_600_000.0
        self.state.last_pv_ts = ts

        if (
            self.state.forecast_today_anchor_kwh is None
            and forecast_today_kwh is not None
            and forecast_today_kwh > 0.05
            and now.hour <= 10
        ):
            self.state.forecast_today_anchor_kwh = forecast_today_kwh

        if forecast_now_w is not None and forecast_now_w >= 100.0 and actual_pv_w >= 0.0:
            raw_ratio = max(0.0, min(2.5, actual_pv_w / forecast_now_w))
            corrected = forecast_now_w * self.state.forecast_bias_ema
            scale = max(actual_pv_w, corrected, 250.0)
            rel_error = min(1.5, abs(actual_pv_w - corrected) / scale)
            alpha = 0.08 if self.state.forecast_samples < 40 else 0.025
            if self.state.forecast_samples == 0:
                self.state.forecast_bias_ema = raw_ratio
                self.state.forecast_abs_error_ema = rel_error
            else:
                self.state.forecast_bias_ema += alpha * (raw_ratio - self.state.forecast_bias_ema)
                self.state.forecast_abs_error_ema += alpha * (rel_error - self.state.forecast_abs_error_ema)
            self.state.forecast_samples += 1

    def _finish_day(self) -> None:
        actual = self.state.actual_pv_today_kwh
        forecast = self.state.forecast_today_anchor_kwh
        if actual > 0.1:
            n = self.state.completed_pv_days
            self.state.average_actual_day_kwh = (
                actual if n == 0 else self.state.average_actual_day_kwh * 0.8 + actual * 0.2
            )
            self.state.completed_pv_days += 1
        if forecast is None or forecast <= 0.1:
            return
        ratio = max(0.0, min(2.5, actual / forecast))
        corrected = forecast * self.state.forecast_daily_bias_ema
        rel_error = min(1.5, abs(actual - corrected) / max(actual, corrected, 0.5))
        alpha = 0.25 if self.state.forecast_daily_samples < 5 else 0.12
        if self.state.forecast_daily_samples == 0:
            self.state.forecast_daily_bias_ema = ratio
            self.state.forecast_daily_error_ema = rel_error
        else:
            self.state.forecast_daily_bias_ema += alpha * (ratio - self.state.forecast_daily_bias_ema)
            self.state.forecast_daily_error_ema += alpha * (rel_error - self.state.forecast_daily_error_ema)
        self.state.forecast_daily_samples += 1

    def trust(self) -> tuple[float, float, str]:
        sample_conf = min(1.0, self.state.forecast_samples / 160.0)
        current_accuracy = max(0.0, 1.0 - min(1.0, self.state.forecast_abs_error_ema))
        current_trust = sample_conf * current_accuracy

        if self.state.forecast_daily_samples > 0:
            daily_count = min(1.0, self.state.forecast_daily_samples / 7.0)
            daily_accuracy = max(0.0, 1.0 - min(1.0, self.state.forecast_daily_error_ema))
            daily_trust = daily_count * daily_accuracy
            trust = current_trust * 0.7 + daily_trust * 0.3
            bias = self.state.forecast_bias_ema * 0.7 + self.state.forecast_daily_bias_ema * 0.3
        else:
            trust = current_trust
            bias = self.state.forecast_bias_ema

        trust = max(0.0, min(1.0, trust))
        if trust >= 0.82 and self.state.forecast_samples >= 160:
            reputation = "trusted"
        elif trust >= 0.58 and self.state.forecast_samples >= 80:
            reputation = "reliable"
        elif self.state.forecast_samples >= 20:
            reputation = "learning"
        else:
            reputation = "unknown"
        return trust, max(0.35, min(1.8, bias)), reputation
