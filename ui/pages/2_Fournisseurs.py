"""Page Fournisseurs — gestion des fournisseurs et mercuriales enregistrées."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from db.database import SessionLocal, init_db
from db.repository import (
    delete_mercuriale,
    get_mercuriale_produits,
    list_fournisseurs,
    list_mercuriales,
    rename_fournisseur,
)

init_db()

st.set_page_config(page_title="Fournisseurs — StockSage", layout="wide")
st.title("Fournisseurs")
st.caption("Gestion des fournisseurs et des mercuriales enregistrées")

# ── Load data ─────────────────────────────────────────────────────────────────

with SessionLocal() as session:
    df_fourn = list_fournisseurs(session)
    df_merc = list_mercuriales(session)

if df_fourn.empty:
    st.info("Aucun fournisseur enregistré. Importe une mercuriale depuis la page principale.")
    st.stop()

# ── Section 1 : Fournisseurs ──────────────────────────────────────────────────

st.subheader("Fournisseurs")

display_fourn = df_fourn.rename(columns={
    "nom": "Fournisseur",
    "nb_mercuriales": "Mercuriales",
    "derniere_mercuriale": "Dernière mercuriale",
})[["Fournisseur", "Mercuriales", "Dernière mercuriale"]]

st.dataframe(display_fourn, hide_index=True, use_container_width=True)

with st.expander("Renommer un fournisseur"):
    fourn_ids = dict(zip(df_fourn["nom"], df_fourn["id"]))
    selected = st.selectbox("Fournisseur à renommer", list(fourn_ids), key="rename_select")
    new_name = st.text_input("Nouveau nom", value=selected, key="rename_input")

    if st.button("Renommer", key="rename_btn"):
        new_name = new_name.strip()
        if not new_name:
            st.error("Le nom ne peut pas être vide.")
        elif new_name == selected:
            st.warning("Le nom est identique — aucune modification.")
        else:
            with SessionLocal() as session:
                rename_fournisseur(session, fourn_ids[selected], new_name)
            st.success(f'Renommé : "{selected}" → "{new_name}"')
            st.rerun()

st.divider()

# ── Section 2 : Mercuriales ───────────────────────────────────────────────────

st.subheader("Mercuriales enregistrées")

pending = st.session_state.get("_pending_delete")
viewing = st.session_state.get("_viewing_mercuriale")

# Confirmation banner
if pending:
    st.warning(
        f"Supprimer la mercuriale **{pending['label']}** "
        f"({pending['nb_produits']} produits) ? Cette action est irréversible."
    )
    c1, c2, _ = st.columns([2, 2, 6])
    if c1.button("Confirmer la suppression", type="primary", key="confirm_del"):
        with SessionLocal() as session:
            delete_mercuriale(session, pending["id"])
        st.session_state.pop("_pending_delete", None)
        st.session_state.pop("_viewing_mercuriale", None)
        st.rerun()
    if c2.button("Annuler", key="cancel_del"):
        st.session_state.pop("_pending_delete", None)
        st.rerun()
    st.divider()

# Table header
h0, h1, h2, h3, h4, h5 = st.columns([3, 2, 2, 1, 1, 1])
h0.caption("Fournisseur")
h1.caption("Date du tarif")
h2.caption("Importé le")
h3.caption("Produits")
h4.caption("")
h5.caption("")

# One row per mercuriale
for _, row in df_merc.iterrows():
    merc_id = int(row["id"])
    is_pending = pending and pending["id"] == merc_id
    is_viewing = viewing and viewing["id"] == merc_id

    c0, c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1, 1])
    c0.write(row["fournisseur"])
    c1.write(str(row["date_tarif"]))
    c2.write(str(row["imported_at"])[:10] if row["imported_at"] else "—")
    c3.write(str(int(row["nb_produits"])))

    # "Voir" button
    voir_label = "Fermer" if is_viewing else "Voir"
    if c4.button(voir_label, key=f"voir_{merc_id}"):
        if is_viewing:
            st.session_state.pop("_viewing_mercuriale", None)
        else:
            st.session_state["_viewing_mercuriale"] = {
                "id": merc_id,
                "label": f"{row['fournisseur']} — {row['date_tarif']}",
            }
        st.rerun()

    # "Supprimer" button
    if not is_pending:
        if c5.button("Supprimer", key=f"del_{merc_id}"):
            st.session_state["_pending_delete"] = {
                "id": merc_id,
                "label": f"{row['fournisseur']} — {row['date_tarif']}",
                "nb_produits": int(row["nb_produits"]),
            }
            st.rerun()
    else:
        c5.markdown("**...**")

# ── Section 3 : Détail mercuriale ─────────────────────────────────────────────

if viewing:
    st.divider()
    st.subheader(viewing["label"])

    with SessionLocal() as session:
        df_produits = get_mercuriale_produits(session, viewing["id"])

    if df_produits.empty:
        st.info("Aucun produit dans cette mercuriale.")
    else:
        df_display = df_produits.rename(columns={
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
        })
        st.caption(f"{len(df_display)} produit(s)")
        st.dataframe(
            df_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "PUM": st.column_config.NumberColumn(format="%.4f"),
                "Prix/colis (1-4)": st.column_config.NumberColumn(format="%.2f €"),
                "Prix/colis (5+)": st.column_config.NumberColumn(format="%.2f €"),
            },
        )
