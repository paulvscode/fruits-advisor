"""Page Catalogue — import et visualisation du catalogue produits interne."""

import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.etl.catalogue import parse_catalogue_csv
from db.database import SessionLocal, init_db
from db.repository import get_catalogue, import_catalogue

init_db()

st.set_page_config(page_title="Catalogue — StockSage", layout="wide")
st.title("Catalogue produits")
st.caption("Référentiel interne des articles — base du matching avec les mercuriales")

# ── Sidebar : import ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Importer un catalogue")
    uploaded = st.file_uploader(
        "Fichier catalogue (CSV)",
        type=["csv"],
        help="Colonnes attendues : Note, Code Article, Désignation, Famille, Fournisseur, Ref Fournis",
    )

# ── Parse & preview ───────────────────────────────────────────────────────────

if uploaded:
    with st.spinner("Lecture du fichier..."):
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            df_preview, alertes = parse_catalogue_csv(tmp_path)
        except Exception as e:
            st.error(f"Erreur de parsing : {e}")
            st.stop()
        finally:
            os.unlink(tmp_path)

    if alertes:
        for a in alertes:
            st.warning(a)

    # Stats
    nb_familles = df_preview["famille"].nunique()
    c1, c2, c3 = st.columns(3)
    c1.metric("Articles", len(df_preview))
    c2.metric("Familles", nb_familles)
    c3.metric("Fournisseurs", df_preview["fournisseur"].nunique())

    st.subheader("Aperçu")
    st.dataframe(
        df_preview.rename(columns={
            "code_article": "Code Article",
            "designation": "Désignation",
            "famille": "Famille",
            "fournisseur": "Fournisseur",
            "ref_fournis": "Ref Fournis",
            "note": "Note",
        }),
        hide_index=True,
        use_container_width=True,
    )

    st.divider()

    if st.button(
        f"Importer {len(df_preview)} articles en base",
        type="primary",
        disabled=df_preview.empty,
    ):
        with SessionLocal() as session:
            n = import_catalogue(session, df_preview)
        st.success(f"{n} articles importés (ajouts + mises à jour).")
        st.rerun()

    st.stop()

# ── Catalogue existant ────────────────────────────────────────────────────────

with SessionLocal() as session:
    df_cat = get_catalogue(session)

if df_cat.empty:
    st.info("Aucun article dans le catalogue. Importe un fichier CSV depuis le panneau de gauche.")
    st.stop()

# Summary metrics
c1, c2, c3 = st.columns(3)
c1.metric("Articles", len(df_cat))
c2.metric("Familles", df_cat["famille"].nunique())
c3.metric("Fournisseurs", df_cat["fournisseur"].nunique())

st.divider()

# Filters
with st.expander("Filtres", expanded=False):
    fc1, fc2 = st.columns(2)
    search = fc1.text_input("Recherche (désignation, code, ref)", key="cat_search")
    familles = ["Toutes"] + sorted(df_cat["famille"].dropna().unique().tolist())
    famille_filter = fc2.selectbox("Famille", familles, key="cat_famille")

df_view = df_cat.copy()
if search:
    mask = (
        df_view["designation"].str.contains(search, case=False, na=False)
        | df_view["code_article"].str.contains(search, case=False, na=False)
        | df_view["ref_fournis"].str.contains(search, case=False, na=False)
    )
    df_view = df_view[mask]
if famille_filter != "Toutes":
    df_view = df_view[df_view["famille"] == famille_filter]

st.caption(f"{len(df_view)} article(s) affiché(s)")
st.dataframe(
    df_view.drop(columns=["imported_at"]).rename(columns={
        "code_article": "Code Article",
        "designation": "Désignation",
        "famille": "Famille",
        "fournisseur": "Fournisseur",
        "ref_fournis": "Ref Fournis",
        "note": "Note",
    }),
    hide_index=True,
    use_container_width=True,
)
