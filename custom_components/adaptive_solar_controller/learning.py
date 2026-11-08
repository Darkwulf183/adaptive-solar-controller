from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import math

from .const import PREDICTION_LEARNING, PREDICTION_MATURE, PREDICTION_USABLE
from .storage import LearningState


class PatternLearner:
    """Persistent load/response learner with empirical prediction validation."""

    def __init__(self, state: LearningState) -> None:
        self.state = state
        self._pending_predictions: deque[tuple[datetime, float]] = deque(maxlen=16)
        self._last_prediction_queued: datetime | None = None

    @staticmethod
    def _bucket_key(now: datetime) -> str:
        slot = (now.hour * 60 + now.minute) // 5
        return f"{now.weekday()}:{slot}"

    @staticmethod
    def _tod_key(now: datetime) -> str:
        slot = (now.hour * 60 + now.minute) // 15
        return str(slot)

    @staticmethod
    def _update_bucket(bucket: dict[str, float], value: float) -> None:
        count = float(bucket.get("count", 0.0))
        mean = float(bucket.get("mean", value))
        var = float(bucket.get("var", 0.0))
        alpha = 0.16 if count < 40 else 0.04
        delta = value - mean
        mean2 = mean + alpha * delta
        var2 = (1.0 - alpha) * (var + alpha * delta * delta)
        bucket.update(mean=mean2, var=max(0.0, var2), count=min(count + 1.0, 100000.0))

    def observe_load(self, now: datetime, load_w: float) -> None:
        self._apply_aging(now)
        if not math.isfinite(load_w) or load_w < -1000 or load_w > 30000:
            return
        key = self._bucket_key(now)
        bucket = self.state.buckets.setdefault(key, {"mean": load_w, "var": 0.0, "count": 0.0})
        self._update_bucket(bucket, load_w)
        tod_key = self._tod_key(now)
        tod = self.state.tod_buckets.setdefault(tod_key, {"mean": load_w, "var": 0.0, "count": 0.0})
        self._update_bucket(tod, load_w)
        self.state.last_load = load_w
        self.state.samples += 1
        self._evaluate_due_predictions(now, load_w)


    def _apply_aging(self, now: datetime) -> None:
        """Soft forgetting for fast-changing plant behaviour. Seasonal data is separate.

        Means remain, but effective sample counts slowly decay so changed habits can
        regain influence instead of the model becoming permanently 'fully learned'.
        """
        day = now.date().isoformat()
        if self.state.last_learning_decay_day == day:
            return
        days = 1
        if self.state.last_learning_decay_day:
            try:
                days = max(1, min(365, (now.date() - datetime.fromisoformat(self.state.last_learning_decay_day).date()).days))
            except ValueError:
                days = 1
        self.state.last_learning_decay_day = day
        bucket_factor = 0.995 ** days
        response_factor = 0.997 ** days
        for collection in (self.state.buckets, self.state.tod_buckets):
            for bucket in collection.values():
                bucket["count"] = max(1.0, float(bucket.get("count", 1.0)) * bucket_factor)
        self.state.response_samples = max(0, int(self.state.response_samples * response_factor))
        self.state.noise_pos_samples = max(0, int(self.state.noise_pos_samples * bucket_factor))
        self.state.noise_neg_samples = max(0, int(self.state.noise_neg_samples * bucket_factor))

    def _evaluate_due_predictions(self, now: datetime, actual_load: float) -> None:
        while self._pending_predictions and self._pending_predictions[0][0] <= now:
            _, predicted = self._pending_predictions.popleft()
            scale = max(abs(actual_load), abs(predicted), 250.0)
            rel_error = min(2.0, abs(actual_load - predicted) / scale)
            bias = max(-2.0, min(2.0, (predicted - actual_load) / scale))
            alpha = 0.12 if self.state.prediction_eval_samples < 30 else 0.05
            if self.state.prediction_eval_samples == 0:
                self.state.prediction_abs_error_ema = rel_error
                self.state.prediction_bias_ema = bias
            else:
                self.state.prediction_abs_error_ema += alpha * (rel_error - self.state.prediction_abs_error_ema)
                self.state.prediction_bias_ema += alpha * (bias - self.state.prediction_bias_ema)
            self.state.prediction_eval_samples += 1

    @staticmethod
    def _bucket_quality(bucket: dict[str, float] | None) -> tuple[float | None, float]:
        if not bucket:
            return None, 0.0
        mean = float(bucket.get("mean", 0.0))
        var = max(0.0, float(bucket.get("var", 0.0)))
        count = float(bucket.get("count", 0.0))
        spread = math.sqrt(var)
        count_conf = min(1.0, count / 80.0)
        stability = 1.0 / (1.0 + spread / max(abs(mean) * 1.5, 300.0))
        return mean, max(0.0, min(1.0, count_conf * stability))

    def predict_load(self, now: datetime, horizon_minutes: int = 2) -> tuple[float | None, float, str]:
        future = now + timedelta(minutes=horizon_minutes)
        exact_mean, exact_q = self._bucket_quality(self.state.buckets.get(self._bucket_key(future)))
        tod_mean, tod_q = self._bucket_quality(self.state.tod_buckets.get(self._tod_key(future)))

        if exact_mean is not None and tod_mean is not None:
            structural = max(exact_q, tod_q * 0.8)
            weight = 0.65 if exact_q >= 0.2 else 0.35
            predicted = exact_mean * weight + tod_mean * (1.0 - weight)
        elif exact_mean is not None:
            predicted, structural = exact_mean, exact_q
        elif tod_mean is not None:
            predicted, structural = tod_mean, tod_q * 0.85
        else:
            predicted = self.state.last_load
            structural = 0.05 if predicted is not None else 0.0

        empirical_count = min(1.0, self.state.prediction_eval_samples / 80.0)
        empirical_accuracy = max(0.0, 1.0 - min(1.0, self.state.prediction_abs_error_ema))
        empirical = empirical_count * empirical_accuracy
        confidence = max(0.0, min(1.0, structural * 0.35 + empirical * 0.65))

        if self.state.prediction_eval_samples >= 120 and confidence >= 0.70:
            maturity = PREDICTION_MATURE
        elif self.state.prediction_eval_samples >= 20 and confidence >= 0.45:
            maturity = PREDICTION_USABLE
        else:
            maturity = PREDICTION_LEARNING

        # Validate prediction at most once per minute, independent of the 15 s meter cadence.
        if predicted is not None and (
            self._last_prediction_queued is None
            or (now - self._last_prediction_queued).total_seconds() >= 60
        ):
            self._pending_predictions.append((future, predicted))
            self._last_prediction_queued = now

        return predicted, confidence, maturity

    def observe_response(self, old_target: float, new_target: float, old_grid: float, new_grid: float) -> None:
        delta_target = new_target - old_target
        delta_grid = new_grid - old_grid
        if abs(delta_target) < 20:
            return
        observed_gain = -delta_grid / delta_target
        if not 0.25 <= observed_gain <= 1.75:
            return
        previous_gain = max(0.35, min(1.5, self.state.gain))
        residual = observed_gain - previous_gain
        alpha = 0.18 if self.state.response_samples < 20 else 0.08
        self.state.gain = max(0.35, min(1.5, previous_gain + alpha * residual))
        self.state.response_gain_variance = max(
            0.0,
            (1.0 - alpha) * (self.state.response_gain_variance + alpha * residual * residual),
        )
        self.state.response_samples = min(self.state.response_samples + 1, 100000)

    def response_confidence(self) -> float:
        count_conf = min(1.0, self.state.response_samples / 24.0)
        spread = math.sqrt(max(0.0, self.state.response_gain_variance))
        spread_conf = 1.0 / (1.0 + spread / 0.18)
        return max(0.0, min(1.0, count_conf * spread_conf))

    def observe_deadband(self, error_w: float, eligible: bool) -> None:
        if not eligible or not math.isfinite(error_w) or abs(error_w) > 60.0:
            return
        if error_w >= 0:
            alpha = 0.08 if self.state.noise_pos_samples < 40 else 0.025
            self.state.noise_pos_ema += alpha * (abs(error_w) - self.state.noise_pos_ema)
            self.state.noise_pos_samples += 1
        else:
            alpha = 0.08 if self.state.noise_neg_samples < 40 else 0.025
            self.state.noise_neg_ema += alpha * (abs(error_w) - self.state.noise_neg_ema)
            self.state.noise_neg_samples += 1

    def adaptive_deadband(self, grid_target_w: float) -> tuple[float, float, float]:
        # Until enough quiet samples exist, remain close to the old 18 W deadband.
        pos_ready = min(1.0, self.state.noise_pos_samples / 80.0)
        neg_ready = min(1.0, self.state.noise_neg_samples / 80.0)
        learned_pos = max(8.0, min(40.0, self.state.noise_pos_ema * 1.55 + 3.0))
        learned_neg = max(4.0, min(24.0, self.state.noise_neg_ema * 1.35 + 2.0))
        positive = 18.0 * (1.0 - pos_ready) + learned_pos * pos_ready
        negative = 18.0 * (1.0 - neg_ready) + learned_neg * neg_ready
        # Prefer import to export: with a positive target, don't let the learned lower
        # deadband extend materially into real grid export.
        if grid_target_w > 3.0:
            negative = min(negative, max(4.0, grid_target_w - 2.0))
        maturity = min(pos_ready, neg_ready)
        return round(negative, 1), round(positive, 1), maturity
