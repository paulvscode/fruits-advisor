"""Database read/write operations for mercuriales."""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import Fournisseur, Mercuriale, Produit, ProduitTarif


def list_fournisseurs(session: Session) -> pd.DataFrame:
    """Return all fournisseurs with their mercuriale count and latest date."""
    sql = text("""
        SELECT
            f.id,
            f.nom,
            COUNT(m.id)          AS nb_mercuriales,
            MAX(m.date_tarif)    AS derniere_mercuriale
        FROM fournisseurs f
        LEFT JOIN mercuriales m ON m.fournisseur_id = f.id
        GROUP BY f.id, f.nom
        ORDER BY f.nom
    """)
    with session.bind.connect() as conn:
        return pd.read_sql(sql, conn)


def rename_fournisseur(session: Session, fournisseur_id: int, new_name: str) -> None:
    """Rename a fournisseur in place."""
    f = session.get(Fournisseur, fournisseur_id)
    if f:
        f.nom = new_name
        session.commit()


def delete_mercuriale(session: Session, mercuriale_id: int) -> None:
    """Delete a mercuriale and all its ProduitTarif rows (cascade via ORM)."""
    m = session.get(Mercuriale, mercuriale_id)
    if m:
        session.delete(m)
        session.commit()


def get_mercuriale_produits(session: Session, mercuriale_id: int) -> pd.DataFrame:
    """Return all product lines for a given mercuriale."""
    sql = text("""
        SELECT
            pt.nom_produit,
            pt.origine,
            pt.local,
            pt.colisage,
            pt.unite,
            pt.certification,
            pt.prix_colis_1_4,
            pt.prix_colis_5_plus,
            pt.pum,
            pt.unite_pum
        FROM produits_tarif pt
        WHERE pt.mercuriale_id = :mid
        ORDER BY pt.nom_produit
    """)
    with session.bind.connect() as conn:
        return pd.read_sql(sql, conn, params={"mid": mercuriale_id})


def save_mercuriale(
    session: Session,
    result: dict,
    date_tarif: date,
) -> int:
    """
    Persist a parsed mercuriale result.
    Creates the Fournisseur row if it doesn't exist yet.
    Returns the new Mercuriale.id.
    """
    # Upsert fournisseur
    nom = result["fournisseur"]
    fournisseur = session.query(Fournisseur).filter_by(nom=nom).first()
    if not fournisseur:
        fournisseur = Fournisseur(nom=nom)
        session.add(fournisseur)
        session.flush()

    # Create mercuriale header
    mercuriale = Mercuriale(
        fournisseur_id=fournisseur.id,
        date_tarif=date_tarif,
        source_format=result.get("source_format", "inconnu"),
    )
    session.add(mercuriale)
    session.flush()

    # Insert product lines
    def _add_rows(df: pd.DataFrame, categorie: str) -> None:
        for _, row in df.iterrows():
            session.add(ProduitTarif(
                mercuriale_id=mercuriale.id,
                nom_produit=row.get("nom_produit", ""),
                origine=row.get("origine") or None,
                local=bool(row.get("local", False)),
                colisage=row.get("colisage") or None,
                unite=row.get("unite") or None,
                certification=row.get("certification") or None,
                prix_colis_1_4=row.get("prix_colis_1_4") or None,
                prix_colis_5_plus=row.get("prix_colis_5_plus") or None,
                pum=row.get("pum") or None,
                unite_pum=row.get("unite_pum") or None,
                categorie=categorie,
            ))

    df_fl = result.get("produits_fl")
    if df_fl is not None and not df_fl.empty:
        _add_rows(df_fl, "FL_FRAIS")

    df_epic = result.get("produits_epicerie")
    if df_epic is not None and not df_epic.empty:
        _add_rows(df_epic, "EPICERIE")

    session.commit()
    return mercuriale.id


def get_latest_prices(session: Session) -> pd.DataFrame:
    """
    Return the most recent price for each product per supplier.
    'Most recent' = highest date_tarif in mercuriales for that fournisseur.
    """
    sql = text("""
        SELECT
            f.nom           AS fournisseur,
            m.date_tarif,
            m.source_format,
            pt.nom_produit,
            pt.origine,
            pt.local,
            pt.colisage,
            pt.unite,
            pt.certification,
            pt.prix_colis_1_4,
            pt.prix_colis_5_plus,
            pt.pum,
            pt.unite_pum,
            pt.categorie
        FROM produits_tarif pt
        JOIN mercuriales m ON pt.mercuriale_id = m.id
        JOIN fournisseurs f ON m.fournisseur_id = f.id
        WHERE m.date_tarif = (
            SELECT MAX(m2.date_tarif)
            FROM mercuriales m2
            WHERE m2.fournisseur_id = m.fournisseur_id
        )
        ORDER BY f.nom, pt.nom_produit
    """)
    with session.bind.connect() as conn:
        return pd.read_sql(sql, conn)


def import_catalogue(session: Session, df: pd.DataFrame) -> int:
    """
    Upsert catalogue products from a parsed DataFrame.
    Existing rows (same code_article) are updated; new ones are inserted.
    Returns the number of rows processed.
    """
    for _, row in df.iterrows():
        session.merge(Produit(
            code_article=row["code_article"],
            designation=row.get("designation") or "",
            famille=row.get("famille") or None,
            fournisseur=row.get("fournisseur") or None,
            ref_fournis=row.get("ref_fournis") or None,
            note=row.get("note") or None,
        ))
    session.commit()
    return len(df)


def get_catalogue(session: Session) -> pd.DataFrame:
    """Return the full internal product catalogue."""
    sql = text("""
        SELECT
            code_article,
            designation,
            famille,
            fournisseur,
            ref_fournis,
            note,
            imported_at
        FROM produits
        ORDER BY famille, designation
    """)
    with session.bind.connect() as conn:
        return pd.read_sql(sql, conn)


def list_mercuriales(session: Session) -> pd.DataFrame:
    """Return a summary of all stored mercuriales."""
    sql = text("""
        SELECT
            m.id,
            f.nom           AS fournisseur,
            m.date_tarif,
            m.source_format,
            m.imported_at,
            COUNT(pt.id)    AS nb_produits
        FROM mercuriales m
        JOIN fournisseurs f ON m.fournisseur_id = f.id
        LEFT JOIN produits_tarif pt ON pt.mercuriale_id = m.id
        GROUP BY m.id, f.nom, m.date_tarif, m.source_format, m.imported_at
        ORDER BY m.date_tarif DESC, f.nom
    """)
    with session.bind.connect() as conn:
        return pd.read_sql(sql, conn)
