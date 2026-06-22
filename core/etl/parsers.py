"""
ETL parsers for supplier price files.
Currently supports: Presto'Bio XLSX, Presto'Bio PDF, and free-form email text.
"""

from __future__ import annotations

import re
from pathlib import Path
import pandas as pd
import pdfplumber

from core.etl.normalizer import compute_pum

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPLIER_NAME = "Presto'Bio"

# Sheet in the Presto'Bio XLSX
SHEET_FL = "TARIF DEPART"

# Column indices in XLSX "TARIF DEPART" sheet
COL_NOM = 0
COL_ORIGINE = 1
COL_COLISAGE = 2
COL_UNITE = 3
COL_CERTIF = 4
COL_PRIX_1_4 = 6
COL_PRIX_5_PLUS = 7

VALID_CERTIFS = {"BIO", "EQ"}
VALID_UNITES = {"KG", "UN"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_product_row_fl(row: pd.Series) -> bool:
    """True if the row is a real F&L product (not a title or empty row)."""
    colisage = pd.to_numeric(row[COL_COLISAGE], errors="coerce")
    prix = pd.to_numeric(row[COL_PRIX_1_4], errors="coerce")
    return pd.notna(colisage) and pd.notna(prix)



def _clean_str(val) -> str:
    if pd.isna(val):
        return ""
    return str(val).strip()


def _to_float(val) -> float | None:
    if pd.isna(val):
        return None
    try:
        return float(str(val).replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        return None


def _extract_local_flag(origine: str) -> bool:
    """True if origin is France (local preference applies)."""
    origine_up = origine.upper()
    return "FRANCE" in origine_up


def _detect_validity_dates(raw: pd.DataFrame) -> tuple[str, str]:
    """Scan the top rows to extract Du/Au dates."""
    date_du = date_au = ""
    for _, row in raw.head(15).iterrows():
        for val in row:
            if pd.isna(val):
                continue
            s = str(val)
            if re.match(r"\d{4}-\d{2}-\d{2}", s):
                ts = pd.Timestamp(s)
                formatted = ts.strftime("%d/%m/%Y")
                if not date_du:
                    date_du = formatted
                elif not date_au:
                    date_au = formatted
    return date_du, date_au


# ── XLSX Parser ───────────────────────────────────────────────────────────────

def parse_prestobio_xlsx(filepath: str | Path) -> dict:
    """
    Parse a Presto'Bio XLSX mercuriale file.

    Returns a dict with keys:
      - "fournisseur": str
      - "validite_du": str
      - "validite_au": str
      - "produits_fl": pd.DataFrame   (F&L frais)
      - "produits_epicerie": pd.DataFrame
      - "alertes": list[str]
    """
    filepath = Path(filepath)
    alertes: list[str] = []

    xl = pd.ExcelFile(filepath, engine="openpyxl")

    if SHEET_FL not in xl.sheet_names:
        raise ValueError(f"Feuille '{SHEET_FL}' introuvable dans {filepath.name}")

    # ── Sheet 1 : F&L frais ───────────────────────────────────────────────
    raw_fl = xl.parse(SHEET_FL, header=None)
    date_du, date_au = _detect_validity_dates(raw_fl)

    records_fl = []
    for _, row in raw_fl.iterrows():
        if not _is_product_row_fl(row):
            continue

        nom = _clean_str(row[COL_NOM])
        if not nom:
            continue

        origine = _clean_str(row[COL_ORIGINE])
        colisage = _to_float(row[COL_COLISAGE])
        unite = _clean_str(row[COL_UNITE]).upper()
        certif = _clean_str(row[COL_CERTIF]).upper()
        prix_1_4 = _to_float(row[COL_PRIX_1_4])
        prix_5_plus = _to_float(row[COL_PRIX_5_PLUS])

        # "COL" = colis vendu à la pièce (ex: plateau de kiwis)
        if unite == "COL":
            unite = "UN"
        if unite not in VALID_UNITES:
            alertes.append(f"Unité inconnue '{unite}' sur : {nom[:60]}")
            unite = "UN"

        if certif not in VALID_CERTIFS:
            certif = "BIO"

        pum, unite_pum, alerte_pum = compute_pum(prix_1_4, colisage, unite, nom)
        if alerte_pum:
            alertes.append(f"{alerte_pum} — {nom[:60]}")

        records_fl.append({
            "fournisseur": SUPPLIER_NAME,
            "nom_produit": nom,
            "origine": origine,
            "local": _extract_local_flag(origine),
            "colisage": colisage,
            "unite": unite,
            "certification": certif,
            "prix_colis_1_4": prix_1_4,
            "prix_colis_5_plus": prix_5_plus,
            "pum": pum,
            "unite_pum": unite_pum,
            "categorie": "FL_FRAIS",
        })

    df_fl = pd.DataFrame(records_fl)

    return {
        "fournisseur": SUPPLIER_NAME,
        "validite_du": date_du,
        "validite_au": date_au,
        "source_format": "xlsx",
        "produits_fl": df_fl,
        "produits_epicerie": pd.DataFrame(),
        "alertes": alertes,
    }


# ── PDF Parser ────────────────────────────────────────────────────────────────

# Matches the data portion of a product line: colisage + unit + certif + price(s)
# colisage can be integer (5) or decimal (2,5)
_DATA_RE = re.compile(
    r"(\d+(?:[,.]\d+)?)"            # colisage
    r"\s+(KG|UN|COL)\s+"            # unite
    r"(BIO|EQ|DEM|REC)\s+"          # certification
    r"(\d+[,.]\d+)"                 # prix 1-4 colis
    r"(?:\s+(\d+[,.]\d+))?",        # prix 5+ colis (optional)
    re.IGNORECASE,
)

# Lines that are page headers, footers or structural noise — skip entirely
_SKIP_RE = re.compile(
    r"^(Page \d+|CLIENT:|Du\s*\d|Au\s*\d|DE 1 A|5 COLIS|QUANTITE|MONTANT|"
    r"Colisage|www\.|Grossiste|ROUEN|TARIF\s*$|NOMBRE DE COLIS|ATTENTION|"
    r"CE TARIF|TOUTE COMMANDE|KG=|DEM=|SAC |PRIX UNITAIRE|0,00 €$)",
    re.IGNORECASE,
)

# Section title lines — reset the product name buffer
_SECTION_RE = re.compile(
    r"^(LES |LA |L'|NOS |AIL\s*-\s*ECHALOTE|SAFRAN$)",
    re.IGNORECASE,
)

# Orphan lines that appear after a data line: leftover name fragments or lone country names
# e.g. "(35/45) - France", "France", "PORTUGAL", "- FRUITS DECLASSES..."
_ORPHAN_RE = re.compile(
    r"^[\(\-]"
    r"|^(France|Espagne|Itali[ae]|Portugal|Perou|Bresil|Colombie|Equateur|"
    r"Algerie|Israel|Maroc|Togo|Senegal|Nelle[- ]Z[eé]lande|Costa[\s]Rica)"
    r"(?:\s*/\s*[\w\s\-ÀÂÄÉÈÊËÎÏÔÙÛÜ]+)?\s*$",
    re.IGNORECASE,
)

# Origin markers to split "nom + origine" on single-line products
_ORIGIN_SPLIT_RE = re.compile(
    r"\s+((?:France|Espagne|Itali[ae]|Perou|Bresil|Colombie|"
    r"Nelle[- ]Z[eé]lande|Equateur|Costa[\s]Rica|Togo|Senegal|"
    r"Algerie|Israel|Maroc|Portugal|Pologne|Pays[\s-]Bas)"
    r"(?:\s*/\s*[\w\s\-ÀÂÄÉÈÊËÎÏÔÙÛÜ]+)?)"
    r"\s*$",
    re.IGNORECASE,
)


def _split_nom_origine(text: str) -> tuple[str, str]:
    """Split 'PRODUIT - France France / SUD-OUEST' into (nom, origine)."""
    m = _ORIGIN_SPLIT_RE.search(text)
    if m:
        return text[:m.start()].strip(), m.group(1).strip()
    return text.strip(), ""


def parse_prestobio_pdf(filepath: str | Path) -> dict:
    """
    Parse a Presto'Bio PDF mercuriale file (fallback when no XLSX available).

    Strategy: scan lines sequentially.
    - "Data lines" contain colisage + unit + certif + price(s) → identified by _DATA_RE.
    - Non-data lines preceding a data line are buffered as candidate product names.
    - Two layouts handled:
        A) Split: name on line N, data on line N+1 (origin at start of data line)
        B) Single: name + origin + data all on one line
    """
    filepath = Path(filepath)
    alertes: list[str] = []
    records: list[dict] = []
    date_du = date_au = ""

    # Collect all lines from all pages
    all_lines: list[str] = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_lines.extend(text.splitlines())

    pending: list[str] = []  # product name candidate lines
    skip_orphan = False       # True right after a data line to drop leftover fragments

    for raw_line in all_lines:
        line = raw_line.strip()
        if not line:
            continue

        # Extract validity dates (compact format "Du18/06/2026")
        m_date = re.search(r"Du\s*(\d{2}/\d{2}/\d{4})", line)
        if m_date and not date_du:
            date_du = m_date.group(1)
        m_date = re.search(r"Au\s*(\d{2}/\d{2}/\d{4})", line)
        if m_date and not date_au:
            date_au = m_date.group(1)

        if _SKIP_RE.search(line):
            continue

        if _SECTION_RE.search(line):
            pending = []
            skip_orphan = False
            continue

        m = _DATA_RE.search(line)
        if not m:
            # Drop orphan fragments that follow a data line (e.g. "(35/45) - France")
            if skip_orphan and _ORPHAN_RE.search(line):
                skip_orphan = False
                continue
            skip_orphan = False
            # Buffer as potential product name (keep last 2 lines max)
            pending.append(line)
            if len(pending) > 2:
                pending = pending[-2:]
            continue

        # ── Data line found ────────────────────────────────────────────────
        colisage  = _to_float(m.group(1))
        unite     = m.group(2).upper()
        certif    = m.group(3).upper()
        prix_1_4  = _to_float(m.group(4))
        prix_5_plus = _to_float(m.group(5)) if m.group(5) else None

        text_before = line[:m.start()].strip()

        if pending:
            # Layout A: name in buffer, origin at start of data line
            nom = " ".join(pending)
            origine = text_before
        else:
            # Layout B: name + origin merged on one line
            nom, origine = _split_nom_origine(text_before)

        pending = []

        if not nom:
            continue

        # Normalise
        if unite == "COL":
            unite = "UN"
        if unite not in VALID_UNITES:
            alertes.append(f"[PDF] Unité inconnue '{unite}' sur : {nom[:60]}")
            unite = "UN"
        if certif not in VALID_CERTIFS:
            certif = "BIO"

        pum, unite_pum, alerte_pum = compute_pum(prix_1_4, colisage, unite, nom)
        if alerte_pum:
            alertes.append(f"[PDF] {alerte_pum} — {nom[:60]}")

        records.append({
            "fournisseur": SUPPLIER_NAME,
            "nom_produit": nom,
            "origine": origine,
            "local": _extract_local_flag(origine) or _extract_local_flag(nom),
            "colisage": colisage,
            "unite": unite,
            "certification": certif,
            "prix_colis_1_4": prix_1_4,
            "prix_colis_5_plus": prix_5_plus,
            "pum": pum,
            "unite_pum": unite_pum,
            "categorie": "FL_FRAIS",
        })
        pending = []
        skip_orphan = True  # next line may be an orphan fragment

    if not records:
        alertes.append("Aucun produit extrait du PDF — vérifier le format.")

    return {
        "fournisseur": SUPPLIER_NAME,
        "validite_du": date_du,
        "validite_au": date_au,
        "source_format": "pdf",
        "produits_fl": pd.DataFrame(records),
        "produits_epicerie": pd.DataFrame(),
        "alertes": alertes,
    }


# ── Email / free-text parser ──────────────────────────────────────────────────

# Matches: "Produit (détail) : 1.90 €/kg"  or  "Produit: 0,95 €/p"
_EMAIL_LINE_RE = re.compile(
    r"^(.+?)\s*:\s*(\d+[,.]?\d*)\s*€\s*/\s*([\w]+)\s*$",
    re.IGNORECASE,
)

# Known unit abbreviations → internal standard
_EMAIL_UNIT_MAP: dict[str, str] = {
    "kg": "KG",
    "bts": "UN", "botte": "UN", "bottes": "UN",
    "p": "UN", "pce": "UN", "pièce": "UN", "piece": "UN", "pièces": "UN",
    "u": "UN", "un": "UN", "unité": "UN", "unites": "UN",
    "barq": "UN", "barquette": "UN",
    "sachet": "UN", "sac": "UN",
    "bch": "UN", "bouquet": "UN",
    "filet": "UN", "plateau": "UN",
    "pot": "UN", "pots": "UN",
    "tête": "UN", "tete": "UN",
}


def parse_email_text(text: str, fournisseur: str = "Email") -> dict:
    """
    Parse a free-form email mercuriale.

    Expected line format (one product per line):
        Carotte : 1.9 €/bts
        Betterave : 2.2 €/kg
        Feuille de chêne rouge: 0.95 €/p

    Header/footer lines that don't match are silently skipped.
    The price in the email is already the unit price (PUM), colisage = 1.
    """
    records: list[dict] = []
    alertes: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = _EMAIL_LINE_RE.match(line)
        if not m:
            continue

        nom = m.group(1).strip()
        prix_str = m.group(2).replace(",", ".")
        unite_raw = m.group(3).lower().strip()

        try:
            prix = float(prix_str)
        except ValueError:
            alertes.append(f"Prix invalide : {line[:60]}")
            continue

        unite = _EMAIL_UNIT_MAP.get(unite_raw)
        if unite is None:
            alertes.append(f"Unité non reconnue '{unite_raw}' — {nom[:50]} (traité comme UN)")
            unite = "UN"

        if unite == "KG":
            pum, unite_pum = round(prix, 4), "€/kg"
        else:
            # Try to extract weight from product name for €/kg conversion
            from core.etl.normalizer import extract_unit_weight_kg
            w = extract_unit_weight_kg(nom)
            if w:
                pum, unite_pum = round(prix / w, 4), "€/kg"
            else:
                pum, unite_pum = round(prix, 4), "€/pce"
                alertes.append(f"Poids unitaire inconnu — PUM en €/pce : {nom[:50]}")

        records.append({
            "fournisseur": fournisseur,
            "nom_produit": nom,
            "origine": "",
            "local": False,
            "colisage": 1.0,
            "unite": unite,
            "certification": "BIO",
            "prix_colis_1_4": prix,
            "prix_colis_5_plus": None,
            "pum": pum,
            "unite_pum": unite_pum,
            "categorie": "FL_FRAIS",
        })

    if not records:
        alertes.append("Aucun produit reconnu — vérifier le format (attendu : 'Nom : prix €/unité').")

    return {
        "fournisseur": fournisseur,
        "validite_du": "",
        "validite_au": "",
        "source_format": "email",
        "produits_fl": pd.DataFrame(records),
        "produits_epicerie": pd.DataFrame(),
        "alertes": alertes,
    }


# ── Public entry point ────────────────────────────────────────────────────────

def parse_mercuriale(filepath: str | Path) -> dict:
    """
    Auto-detect file format and route to the correct parser.
    Supports .xlsx and .pdf.
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    if ext == ".xlsx":
        return parse_prestobio_xlsx(filepath)
    elif ext == ".pdf":
        return parse_prestobio_pdf(filepath)
    else:
        raise ValueError(f"Format non supporté : '{ext}'. Acceptés : .xlsx, .pdf")
