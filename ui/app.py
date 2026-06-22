"""Fruits Advisor — Interface MVP Streamlit."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.etl.parsers import parse_mercuriale

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Fruits Advisor",
    layout="wide",
)

st.title("Fruits Advisor")
st.caption("Outil d'aide à la commande — Réseau magasins bio")

# ── Sidebar : upload ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Importer une mercuriale")
    uploaded = st.file_uploader(
        "Fichier fournisseur",
        type=["xlsx", "pdf"],
        help="Formats acceptés : Excel (.xlsx) et PDF",
    )
    st.divider()
    st.markdown("**Fournisseurs supportés**")
    st.markdown("- Presto'Bio (XLSX & PDF)")
    st.markdown("- *D'autres à venir...*")

# ── Main content ──────────────────────────────────────────────────────────────

if not uploaded:
    st.info("Glisse un fichier mercuriale dans le panneau de gauche pour commencer.")
    st.stop()

# Parse the uploaded file
with st.spinner("Analyse en cours..."):
    import tempfile, os

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

# ── Header info ───────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
col1.metric("Fournisseur", result["fournisseur"])
col2.metric("Valide du", result["validite_du"] or "—")
col3.metric("Valide au", result["validite_au"] or "—")

# ── Alertes ETL ───────────────────────────────────────────────────────────────

if result["alertes"]:
    with st.expander(f"{len(result['alertes'])} alerte(s) ETL", expanded=False):
        for alerte in result["alertes"]:
            st.warning(alerte)

# ── Tabs : F&L frais / Épicerie ───────────────────────────────────────────────

df_fl: pd.DataFrame = result["produits_fl"]
df_epic: pd.DataFrame = result["produits_epicerie"]

tab_fl, tab_epic = st.tabs([
    f"Fruits & Légumes frais ({len(df_fl)} produits)",
    f"Épicerie ({len(df_epic)} produits)",
])

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

DISPLAY_COLS_EPIC = {
    "nom_produit": "Produit",
    "colisage": "Colisage",
    "unite": "Unité",
    "certification": "Certif.",
    "prix_colis_1_4": "Prix/colis",
    "pum": "PUM",
    "unite_pum": "Unité PUM",
}


def render_table(df: pd.DataFrame, col_map: dict, key: str):
    if df.empty:
        st.info("Aucun produit dans cette catégorie.")
        return

    available = {k: v for k, v in col_map.items() if k in df.columns}
    display = df[list(available.keys())].rename(columns=available).copy()

    # Filters
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

    # Export CSV
    csv = display.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Exporter CSV",
        data=csv,
        file_name=f"mercuriale_{result['fournisseur']}_{key}.csv",
        mime="text/csv",
        key=f"dl_{key}",
    )


with tab_fl:
    render_table(df_fl, DISPLAY_COLS_FL, "fl")

with tab_epic:
    render_table(df_epic, DISPLAY_COLS_EPIC, "epic")
