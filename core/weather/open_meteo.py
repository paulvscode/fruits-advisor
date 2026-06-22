"""Open-Meteo historical weather connector — free, no API key required."""

from __future__ import annotations

import httpx
import pandas as pd


def fetch_monthly_weather(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Fetch daily data from Open-Meteo archive and aggregate to monthly.

    Returns DataFrame with columns:
        mois (Timestamp), temp_mean (°C), precip_sum (mm)
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "Europe/Paris",
    }
    r = httpx.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()["daily"]

    df = pd.DataFrame({
        "date": pd.to_datetime(data["time"]),
        "temp": data["temperature_2m_mean"],
        "precip": data["precipitation_sum"],
    })
    df["mois"] = df["date"].dt.to_period("M").dt.to_timestamp()

    return (
        df.groupby("mois")
        .agg(temp_mean=("temp", "mean"), precip_sum=("precip", "sum"))
        .reset_index()
        .assign(
            temp_mean=lambda d: d["temp_mean"].round(1),
            precip_sum=lambda d: d["precip_sum"].round(1),
        )
    )
