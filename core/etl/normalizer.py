"""Unit normalization and PUM (Prix Unitaire Moyen) calculation."""

import re


def extract_unit_weight_kg(name: str) -> float | None:
    """
    Tries to extract the unit weight (in kg) from a product name.
    Returns None if the unit is already KG or weight can't be determined.
    """
    name_up = name.upper()

    # "BARQ.125G", "BARQ 125G", "(BARQ.125G)", "BARQ·125G"
    # [^\w]* handles any non-alphanumeric separator (ASCII dot, Unicode chars, spaces…)
    m = re.search(r"BARQ[^\w]*(\d+)\s*G", name_up)
    if m:
        return int(m.group(1)) / 1000

    # "5*100G", "12*160G", "5*125G"
    m = re.search(r"\d+\s*\*\s*(\d+)G", name_up)
    if m:
        return int(m.group(1)) / 1000

    # "4 POTS* 300G", "4 POTS * 300G", "6 POTS EN VERRE DE 700G"
    m = re.search(r"POTS?\b.*?(\d+)\s*G", name_up)
    if m:
        return int(m.group(1)) / 1000

    # "ETUIS * 4 GOURDES DE 90G"
    m = re.search(r"GOURDES?\s+DE\s+(\d+)\s*G", name_up)
    if m:
        return int(m.group(1)) / 1000

    # "* 5KG", "* 2,5KG", "x 2,5 KG", "COLIS DE 2 KG", "2,5 KG"
    m = re.search(r"[\*x]\s*(\d+[,.]\d+|\d+)\s*KG", name_up)
    if m:
        return float(m.group(1).replace(",", "."))

    # "Env. 600/780G" → average
    m = re.search(r"ENV\.\s*(\d+)\s*/\s*(\d+)\s*G", name_up)
    if m:
        return (int(m.group(1)) + int(m.group(2))) / 2 / 1000

    # "1 KG LA PIECE", "0,7 KG LA PIECE"
    m = re.search(r"(\d+[,.]\d+|\d+)\s*KG\s+LA\s+PIECE", name_up)
    if m:
        return float(m.group(1).replace(",", "."))

    # "(≈ 285 g/pièce)", "(≈ 250 g/pièce)"
    m = re.search(r"[≈~]\s*(\d+)\s*G\s*/\s*PI", name_up)
    if m:
        return int(m.group(1)) / 1000

    return None


def extract_pieces_per_colis(name: str) -> int | None:
    """
    Detect explicit piece count per colis from product name.
    Handles: 'x 27 PIECES', 'x 12 PCS', '× 6 UNITÉS', etc.
    Returns the count, or None if not found.
    """
    m = re.search(
        r"[x*×]\s*(\d+)\s*(?:PIECES?|PI[EÈ]CES?|PCS?|UNIT[EÉ]S?)\b",
        name,
        re.IGNORECASE,
    )
    if m:
        return int(m.group(1))
    return None


def compute_pum(
    prix_colis: float,
    colisage: float,
    unite: str,
    nom_produit: str,
) -> tuple[float | None, str, str | None]:
    """
    Returns (pum, unite_pum, alerte).
    - pum: Prix Unitaire Moyen
    - unite_pum: "€/kg" or "€/pce"
    - alerte: warning string or None
    """
    if not prix_colis or not colisage or colisage == 0:
        return None, "", "Colisage ou prix manquant"

    if unite == "KG":
        pum = prix_colis / colisage
        return round(pum, 4), "€/kg", None

    # Unite == "UN" — try to find the actual weight per unit → PUM en €/kg
    unit_weight_kg = extract_unit_weight_kg(nom_produit)
    if unit_weight_kg:
        pum_kg = prix_colis / (colisage * unit_weight_kg)
        return round(pum_kg, 4), "€/kg", None

    # No weight found — try to extract piece count from the name → PUM en €/pce
    piece_count = extract_pieces_per_colis(nom_produit)
    if piece_count and piece_count > 0:
        pum_pce = prix_colis / (colisage * piece_count)
        return round(pum_pce, 4), "€/pce", None

    # Unknown unit weight and no piece count — return PUM per declared unit only
    pum_pce = prix_colis / colisage
    return (
        round(pum_pce, 4),
        "€/pce",
        "Poids unitaire inconnu — PUM en €/pce uniquement",
    )
