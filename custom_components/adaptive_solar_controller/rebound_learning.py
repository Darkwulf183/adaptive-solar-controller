"""Passive voltage-rebound characterization from measured load/relaxation pairs.

These data describe loaded terminal voltage near LOW; they are NOT a capacity
calibration and never establish a FULL anchor. Provenance is retained in storage.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
import math


def rebuild_reference_model(reference: dict) -> dict:
    points = reference.get("points", []) if isinstance(reference, dict) else []
    by_step = defaultdict(lambda: defaultdict(list))
    for p in points:
        try:
            step = int(p.get("step", 0))
            phase = str(p.get("phase", ""))
            v = float(p.get("voltage_v"))
            w = float(p.get("actual_w", 0))
            age = float(p.get("voltage_age_s", 0))
            if step > 0 and phase in ("load", "relaxation") and math.isfinite(v) and math.isfinite(w) and age <= 30:
                by_step[step][phase].append((v, w))
        except (TypeError, ValueError):
            continue
    bins = []
    for step, phases in sorted(by_step.items()):
        load, relax = phases["load"], phases["relaxation"]
        if len(load) < 4 or len(relax) < 10:
            continue
        load_v = median(x[0] for x in load[-5:])
        relaxed_v = median(x[0] for x in relax[-5:])
        actual_w = median(x[1] for x in load[-5:])
        sag = relaxed_v - load_v
        if actual_w >= 75 and 0.02 <= sag <= 1.5:
            bins.append({"step": step, "actual_w": round(actual_w, 1),
                         "load_v": round(load_v, 3), "relaxed_v": round(relaxed_v, 3),
                         "sag_v": round(sag, 3), "samples": len(load) + len(relax)})
    return {"schema": 1, "quality": "provisional_no_full_anchor", "bins": bins,
            "valid_bins": len(bins), "source_sha256": reference.get("source_sha256", "")}


def predicted_sag(model: dict, power_w: float) -> float | None:
    bins = sorted(model.get("bins", []), key=lambda x: x["actual_w"])
    if not bins or not math.isfinite(power_w) or power_w < 0:
        return None
    if power_w <= bins[0]["actual_w"]:
        return round(bins[0]["sag_v"] * power_w / bins[0]["actual_w"], 3)
    for lo, hi in zip(bins, bins[1:]):
        if lo["actual_w"] <= power_w <= hi["actual_w"]:
            t = (power_w - lo["actual_w"]) / max(1, hi["actual_w"] - lo["actual_w"])
            return round(lo["sag_v"] + t * (hi["sag_v"] - lo["sag_v"]), 3)
    return round(bins[-1]["sag_v"], 3)  # no extrapolation above measured range
