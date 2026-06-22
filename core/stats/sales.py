"""
Sales CSV parser.
Expected format: Code ; Designation ; MM YY ; MM YY ; ...
Month headers like "06 26" = June 2026.
"""

from __future__ import annotations

import calendar
import re
from pathlib import Path

import pandas as pd


_MONTH_HEADER_RE = re.compile(r"^(\d{2})\s+(\d{2})$")


def _parse_month_header(header: str) -> pd.Timestamp | None:
    """Parse '06 26' → Timestamp('2026-06-01')."""
    m = _MONTH_HEADER_RE.match(header.strip())
    if not m:
        return None
    month, year_short = int(m.group(1)), int(m.group(2))
    year = 2000 + year_short
    if not (1 <= month <= 12):
        return None
    return pd.Timestamp(year=year, month=month, day=1)


def _days_in_month(ts: pd.Timestamp) -> int:
    return calendar.monthrange(ts.year, ts.month)[1]


def _to_numeric(val) -> float | None:
    """Convert values like '30,515 kg', '0,295 kg', '12.5', '0' to float."""
    if pd.isna(val):
        return None
    # Strip unit suffixes (kg, pce, €, etc.) and whitespace
    s = re.sub(r"[a-zA-Z€]+", "", str(val)).strip()
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_sales_csv(filepath: str | Path, separator: str = ";") -> dict:
    """
    Parse a sales CSV file.

    Returns:
        {
          "df_long":   pd.DataFrame  (tidy format: one row per product×month),
          "df_wide":   pd.DataFrame  (original wide format, cleaned),
          "months":    list[pd.Timestamp]  (chronological),
          "alertes":   list[str],
        }

    df_long columns:
        code, designation, mois (Timestamp), valeur, valeur_par_jour, jours_mois
    """
    filepath = Path(filepath)
    alertes: list[str] = []

    # Try encodings in order: UTF-8 with BOM (Excel), then Windows-1252 (French Excel default)
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            raw = pd.read_csv(
                filepath,
                sep=separator,
                header=0,
                dtype=str,
                encoding=encoding,
            )
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise ValueError("Impossible de lire le fichier : encodage non reconnu (essayé utf-8, cp1252, latin-1).")

    # Normalize column names
    raw.columns = [str(c).strip() for c in raw.columns]

    # Identify the first two columns (Code + Designation) — flexible on exact names
    if len(raw.columns) < 3:
        raise ValueError("Le fichier doit avoir au moins 3 colonnes : Code, Désignation, et au moins un mois.")

    col_code = raw.columns[0]
    col_designation = raw.columns[1]
    month_cols_raw = raw.columns[2:]

    # Parse month headers
    month_map: dict[str, pd.Timestamp] = {}
    for col in month_cols_raw:
        ts = _parse_month_header(col)
        if ts is not None:
            month_map[col] = ts
        else:
            alertes.append(f"Colonne ignorée (format mois non reconnu) : '{col}'")

    if not month_map:
        raise ValueError("Aucune colonne mois reconnue. Format attendu : 'MM YY' (ex: '06 26').")

    # Build clean wide DataFrame
    keep_cols = [col_code, col_designation] + list(month_map.keys())
    df_wide = raw[keep_cols].copy()
    df_wide = df_wide.rename(columns={col_code: "code", col_designation: "designation"})

    # Drop rows with no designation
    df_wide = df_wide[df_wide["designation"].notna() & (df_wide["designation"].str.strip() != "")]
    df_wide["code"] = df_wide["code"].fillna("").str.strip()
    df_wide["designation"] = df_wide["designation"].str.strip()

    # Build long (tidy) DataFrame
    records = []
    for _, row in df_wide.iterrows():
        code = row["code"]
        designation = row["designation"]
        for col, ts in month_map.items():
            valeur = _to_numeric(row[col])
            if valeur is None:
                continue
            jours = _days_in_month(ts)
            records.append({
                "code": code,
                "designation": designation,
                "mois": ts,
                "valeur": valeur,
                "valeur_par_jour": round(valeur / jours, 4),
                "jours_mois": jours,
            })

    df_long = pd.DataFrame(records)
    if not df_long.empty:
        df_long = df_long.sort_values(["designation", "mois"]).reset_index(drop=True)

    months_sorted = sorted(month_map.values())

    return {
        "df_long": df_long,
        "df_wide": df_wide,
        "months": months_sorted,
        "alertes": alertes,
    }
