"""Fruits Advisor — Interface MVP Streamlit."""

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.etl.parsers import parse_email_text, parse_mercuriale
from db.database import SessionLocal, init_db
from db.repository import list_mercuriales, save_mercuriale

init_db()

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Fruits Advisor", layout="wide")
st.title("Fruits Advisor")
st.caption("Outil d'aide à la commande — Réseau magasins bio")

# ── Sidebar : import ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Importer une mercuriale")
    tab_file, tab_email = st.tabs(["Fichier", "Email"])

    with tab_file:
        uploaded = st.file_uploader(
            "Fichier fournisseur",
            type=["xlsx", "pdf"],
            help="Formats acceptés : Excel (.xlsx) et PDF",
        )
        date_tarif_file = st.date_input(
            "Date du tarif",
            value=date.today(),
            key="date_tarif_file",
        )

    with tab_email:
        fournisseur_email = st.text_input(
            "Nom du fournisseur",
            placeholder="Ex: Ferme Martin, Bio Local…",
            key="fournisseur_email",
        )
        email_text = st.text_area(
            "Coller le texte de l'email",
            height=200,
            placeholder="Carotte : 1.9 €/bts\nBetterave : 2.2 €/kg\n…",
            key="email_text",
        )
        date_tarif_email = st.date_input(
            "Date de l'email",
            value=date.today(),
            key="date_tarif_email",
        )
        parse_email_btn = st.button("Analyser l'email", use_container_width=True)

    st.divider()
    st.markdown("**Formats supportés**")
    st.markdown("- Presto'Bio (XLSX & PDF)")
    st.markdown("- Email texte libre")

# ── Parse ─────────────────────────────────────────────────────────────────────

result = None
date_tarif = date.today()

if uploaded:
    with st.spinner("Analyse en cours..."):
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            result = parse_mercuriale(tmp_path)
        except Exception as e:
            st.error(f"Erreur lors du parsing : {e}")
            st.stop()
        finally:
            os.unlink(tmp_path)
    date_tarif = date_tarif_file

elif parse_email_btn:
    if not fournisseur_email.strip():
        st.sidebar.error("Renseigne le nom du fournisseur avant d'analyser.")
    elif not email_text.strip():
        st.sidebar.error("Colle le texte de l'email avant d'analyser.")
    else:
        with st.spinner("Analyse en cours..."):
            result = parse_email_text(email_text, fournisseur=fournisseur_email.strip())
    date_tarif = date_tarif_email

if result is None:
    st.info("Importe une mercuriale dans le panneau de gauche pour commencer.")
    st.caption("Fichier XLSX ou PDF, ou colle directement le texte d'un email fournisseur.")

    # ── Historique des imports ─────────────────────────────────────────────
    with SessionLocal() as session:
        df_hist = list_mercuriales(session)

    if not df_hist.empty:
        st.divider()
        st.subheader("Historique des mercuriales enregistrées")
        df_hist = df_hist.rename(columns={
            "id": "ID", "fournisseur": "Fournisseur", "date_tarif": "Date tarif",
            "source_format": "Format", "imported_at": "Importé le", "nb_produits": "Produits",
        })
        st.dataframe(df_hist, hide_index=True, use_container_width=True)

    st.stop()

# ── Header info ───────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("Fournisseur", result["fournisseur"])
col2.metric("Date du tarif", date_tarif.strftime("%d/%m/%Y"))
col3.metric("Valide du", result["validite_du"] or "—")
col4.metric("Valide au", result["validite_au"] or "—")

# ── Alertes ETL ───────────────────────────────────────────────────────────────

if result["alertes"]:
    with st.expander(f"{len(result['alertes'])} alerte(s) ETL", expanded=False):
        for alerte in result["alertes"]:
            st.warning(alerte)

# ── Enregistrer en base ───────────────────────────────────────────────────────

nb_fl = len(result["produits_fl"])

save_col, info_col = st.columns([2, 8])
if save_col.button(
    f"Enregistrer en base ({nb_fl} produits)",
    type="primary",
    use_container_width=True,
):
    with SessionLocal() as session:
        merc_id = save_mercuriale(session, result, date_tarif)
    st.success(
        f"Mercuriale enregistrée — ID {merc_id} | {result['fournisseur']} | "
        f"{date_tarif.strftime('%d/%m/%Y')} | {nb_fl} produits"
    )

st.divider()

df_fl: pd.DataFrame = result["produits_fl"]

DISPLAY_COLS_FL = {
    "nom_produit": "Produit",
    "origine": "Origine",
    "local": "Local (FR)",
    "colisage": "Colisage",
    "unite": "Unité",
    "certification": "Certif.",
    "prix_colis_1_4": "Prix/colis (1-4)",
    "prix_colis_5_plus": "Prix/colis (5+)",
    "pum": "PUM",
    "unite_pum": "Unité PUM",
}


def render_table(df: pd.DataFrame, col_map: dict, key: str):
    if df.empty:
        st.info("Aucun produit dans cette catégorie.")
        return

    available = {k: v for k, v in col_map.items() if k in df.columns}
    display = df[list(available.keys())].rename(columns=available).copy()

    with st.expander("Filtres", expanded=False):
        fcol1, fcol2 = st.columns(2)
        search = fcol1.text_input("Recherche produit", key=f"search_{key}")
        if "Certif." in display.columns:
            certifs = ["Tous"] + sorted(display["Certif."].dropna().unique().tolist())
            certif_filter = fcol2.selectbox("Certification", certifs, key=f"certif_{key}")
        else:
            certif_filter = "Tous"
        if "Local (FR)" in display.columns:
            local_only = fcol1.checkbox("Local uniquement", key=f"local_{key}")
        else:
            local_only = False

    if search:
        display = display[display["Produit"].str.contains(search, case=False, na=False)]
    if certif_filter != "Tous":
        display = display[display["Certif."] == certif_filter]
    if local_only and "Local (FR)" in display.columns:
        display = display[display["Local (FR)"] == True]

    st.caption(f"{len(display)} produit(s) affiché(s)")
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "PUM": st.column_config.NumberColumn(format="%.4f"),
            "Prix/colis (1-4)": st.column_config.NumberColumn(format="%.2f €"),
            "Prix/colis (5+)": st.column_config.NumberColumn(format="%.2f €"),
            "Prix/colis": st.column_config.NumberColumn(format="%.2f €"),
        },
    )

    csv = display.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Exporter CSV",
        data=csv,
        file_name=f"mercuriale_{result['fournisseur']}_{key}.csv",
        mime="text/csv",
        key=f"dl_{key}",
    )


render_table(df_fl, DISPLAY_COLS_FL, "fl")
