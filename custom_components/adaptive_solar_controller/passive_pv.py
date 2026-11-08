"""RC3 passive PV baseline. Deliberately isolated from the active seasonal learner."""
from __future__ import annotations
import csv
import io
import math
from collections import defaultdict
from datetime import date, datetime
from itertools import islice
from zoneinfo import ZoneInfo

MAX_BYTES = 3_000_000
MAX_ROWS = 70000
MAX_DAYS = 1100


def parse_csv(text: str, tz_name: str, today: date, entity_id: str | None = None) -> dict[str, float]:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("CSV exceeds 3 MB")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    fields = {x.strip().lower(): x for x in (reader.fieldnames or [])}
    time_key = next((fields[k] for k in ("last_changed", "last_updated", "timestamp", "datetime", "date") if k in fields), None)
    val_key = next((fields[k] for k in ("state", "value", "kwh", "energy_kwh", "pv_kwh") if k in fields), None)
    if not time_key or not val_key:
        raise ValueError("Expected date/timestamp and state/value/kwh columns")
    entity_key = fields.get("entity_id")
    local_tz = ZoneInfo(tz_name)
    try:
        rows = list(islice(reader, MAX_ROWS + 1))
    except csv.Error as exc:
        raise ValueError(f"CSV could not be read: {exc}") from exc
    if len(rows) > MAX_ROWS:
        raise ValueError("Too many CSV rows")
    selected = None
    if entity_key:
        found = {(r.get(entity_key) or "").strip() for r in rows} - {""}
        if entity_id and entity_id in found:
            selected = entity_id
        elif len(found) == 1:
            selected = next(iter(found))  # single-sensor export: accept renamed sensor
        elif found:
            raise ValueError(f"CSV contains several entities ({', '.join(sorted(found)[:5])}); expected {entity_id or 'one sensor'}")
    daily = {}
    for row in rows:
        if selected and (row.get(entity_key) or "").strip() != selected:
            continue
        raw_date = (row.get(time_key) or "").strip()
        try:
            if len(raw_date) == 10:
                d = date.fromisoformat(raw_date)
            else:
                ts = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=local_tz)
                d = ts.astimezone(local_tz).date()
            val = float((row.get(val_key) or "").replace(",", "."))
        except (ValueError, TypeError, OverflowError):
            continue
        if not math.isfinite(val) or not 0 <= val <= 100 or d >= today:
            continue
        key = d.isoformat()
        # Daily-energy sensor resets at 00:00, so the daily maximum is the day's yield.
        daily[key] = max(daily.get(key, 0.0), val)
    if not daily:
        raise ValueError("No valid past PV daily values found")
    if len(daily) > MAX_DAYS:
        raise ValueError("More than 1100 PV days: split or reduce CSV")
    return daily


def summary(days: dict[str, float], today: date) -> dict:
    import calendar
    by_month = defaultdict(list)
    by_year = defaultdict(set)
    for key, val in days.items():
        d = date.fromisoformat(key)
        by_month[d.month].append(val)
        by_year[d.year].add(d)
    full_years = [year for year, seen in by_year.items() if len(seen) == (366 if calendar.isleap(year) else 365)]
    # Fraction of days in the best-covered calendar year, not arbitrary 365-day span.
    coverage = max((len(seen) / (366 if calendar.isleap(year) else 365) for year, seen in by_year.items()), default=0)
    return {"days":len(days), "months":len(by_month), "full_calendar_years":sorted(full_years),
            "best_year_coverage":round(coverage, 4),
            "monthly_kwh":{str(m):round(sum(vals)/len(vals), 3) for m, vals in sorted(by_month.items())},
            "theoretical_weight":round(coverage if len(by_month)==12 else coverage*len(by_month)/12, 4),
            "active_weight":0.0}


def estimate(days: dict[str, float], target: date) -> float | None:
    """Mean of all stored days within +/-7 days of the target's day of year (circular,
    across all years). Falls back to the month mean if fewer than 3 days are in range."""
    doy = target.timetuple().tm_yday
    window: list[float] = []
    month: list[float] = []
    for key, val in days.items():
        d = date.fromisoformat(key)
        diff = abs(d.timetuple().tm_yday - doy)
        if min(diff, 366 - diff) <= 7:
            window.append(val)
        if d.month == target.month:
            month.append(val)
    values = window if len(window) >= 3 else month
    return round(sum(values) / len(values), 3) if values else None
