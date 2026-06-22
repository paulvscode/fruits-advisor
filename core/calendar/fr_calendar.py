"""French public holidays and school holidays."""

from __future__ import annotations

import calendar as _cal
from typing import Optional

import httpx
import pandas as pd

try:
    import holidays as _hlib
    _HAS_HOLIDAYS = True
except ImportError:
    _HAS_HOLIDAYS = False


def public_holidays_by_month(
    months: list[pd.Timestamp],
) -> dict[pd.Timestamp, list[str]]:
    """
    Returns {month_start_ts: [holiday_name, ...]} for French public holidays.
    Requires the `holidays` package.
    """
    if not _HAS_HOLIDAYS:
        return {ts.replace(day=1): [] for ts in months}

    years = {ts.year for ts in months}
    fr = _hlib.France(years=years)

    result: dict[pd.Timestamp, list[str]] = {}
    for ts in months:
        key = ts.replace(day=1)
        _, n_days = _cal.monthrange(ts.year, ts.month)
        month_end = ts.replace(day=n_days).date()
        result[key] = [
            name for d, name in sorted(fr.items())
            if key.date() <= d <= month_end
        ]
    return result


def school_holidays_by_month(
    months: list[pd.Timestamp],
    zone: str = "B",
) -> dict[pd.Timestamp, Optional[str]]:
    """
    Returns {month_start_ts: period_label | None}.
    Fetches from the French government open data API (calendrier scolaire).
    """
    if not months:
        return {}

    start_str = min(ts.replace(day=1) for ts in months).strftime("%Y-%m-%d")
    end_ts = max(months)
    _, n = _cal.monthrange(end_ts.year, end_ts.month)
    end_str = end_ts.replace(day=n).strftime("%Y-%m-%d")

    url = (
        "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets"
        "/fr-en-calendrier-scolaire/records"
    )
    params = {
        "where": f'zones="{zone}" AND end_date>="{start_str}" AND start_date<="{end_str}"',
        "limit": 50,
        "order_by": "start_date",
    }
    try:
        r = httpx.get(url, params=params, timeout=10)
        r.raise_for_status()
        records = r.json().get("results", [])
    except Exception:
        return {ts.replace(day=1): None for ts in months}

    periods: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []
    for rec in records:
        try:
            s = pd.Timestamp(rec["start_date"][:10])
            e = pd.Timestamp(rec["end_date"][:10])
            desc = rec.get("description", "Vacances scolaires")
            periods.append((s, e, desc))
        except Exception:
            continue

    result: dict[pd.Timestamp, Optional[str]] = {}
    for ts in months:
        key = ts.replace(day=1)
        _, n = _cal.monthrange(ts.year, ts.month)
        month_end = ts.replace(day=n)
        label = next(
            (name for ps, pe, name in periods if ps <= month_end and pe >= key),
            None,
        )
        result[key] = label
    return result
