"""Parser for the internal product catalogue CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Mapping from CSV header variants → internal column names
_COL_MAP: dict[str, str] = {
    "Note": "note",
    "Code Article": "code_article",
    "Désignation": "designation",
    "Designation": "designation",
    "Famille": "famille",
    "Fournisseur": "fournisseur",
    "Ref Fournis": "ref_fournis",
}

_DROP = {"Sans Cdes"}

_KEEP = ["code_article", "designation", "famille", "fournisseur", "ref_fournis", "note"]


def parse_catalogue_csv(filepath: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """
    Parse the internal product catalogue CSV.

    Expected columns: Note, Code Article, Désignation, Famille, Fournisseur, Ref Fournis, Sans Cdes
    "Sans Cdes" is dropped; all others are imported.

    Returns (df, alertes) where df has columns: code_article, designation,
    famille, fournisseur, ref_fournis, note.
    """
    filepath = Path(filepath)
    alertes: list[str] = []

    # Auto-detect separator × encoding
    # French ERP exports are often Windows-1252 / Latin-1, not UTF-8
    df: pd.DataFrame | None = None
    for sep in [";", "\t", ","]:
        for enc in ["utf-8-sig", "cp1252", "latin-1"]:
            try:
                candidate = pd.read_csv(
                    filepath, sep=sep, dtype=str, encoding=enc, keep_default_na=False
                )
                if len(candidate.columns) >= 3:
                    df = candidate
                    break
            except Exception:
                continue
        if df is not None:
            break

    if df is None:
        raise ValueError("Format CSV non reconnu — séparateur ou encodage introuvable.")

    # Normalise column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]

    # Drop unwanted columns
    drop_found = [c for c in df.columns if c in _DROP]
    df = df.drop(columns=drop_found, errors="ignore")

    # Rename to internal names
    df = df.rename(columns={k: v for k, v in _COL_MAP.items() if k in df.columns})

    # Validate required columns
    missing = [c for c in ["code_article", "designation"] if c not in df.columns]
    if missing:
        raise ValueError(
            f"Colonnes obligatoires introuvables : {', '.join(missing)}. "
            f"Colonnes présentes : {', '.join(df.columns.tolist())}"
        )

    # Drop rows without a code_article
    before = len(df)
    df = df[df["code_article"].str.strip().astype(bool)]
    dropped = before - len(df)
    if dropped:
        alertes.append(f"{dropped} ligne(s) ignorée(s) : Code Article vide.")

    df["code_article"] = df["code_article"].str.strip()

    # Ensure all expected columns exist (fill missing optional ones with None)
    for col in _KEEP:
        if col not in df.columns:
            df[col] = None
        else:
            df[col] = df[col].replace("", None)

    df = df[_KEEP].copy()

    if df.empty:
        alertes.append("Aucun produit trouvé dans le fichier.")

    return df, alertes
