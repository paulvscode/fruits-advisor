"""Page Feuille de route — état de l'application et prochaines étapes."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

st.set_page_config(page_title="Feuille de route — StockSage", layout="wide")
st.title("Feuille de route")
st.caption("Ce que l'application fait aujourd'hui, et ce qui arrive ensuite.")

st.divider()

# ── MVP — en production ───────────────────────────────────────────────────────

with st.container(border=True):
    st.subheader("MVP — En production")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Import des mercuriales**")
        st.markdown(
            "- Presto'Bio XLSX (feuille F&L)\n"
            "- Presto'Bio PDF (fallback)\n"
            "- Email texte libre (format `Produit : prix €/unité`)\n"
            "- Date du tarif configurable à l'import\n"
            "- Sauvegarde en base SQLite horodatée par fournisseur"
        )

        st.markdown("**Normalisation ETL**")
        st.markdown(
            "- Calcul PUM en €/kg si le poids est connu\n"
            "- Détection du poids via `BARQ.125G`, `x 2,5 KG`, `4*300G`…\n"
            "- Détection du nombre de pièces via `x 27 PIECES`\n"
            "- Alertes sur unités inconnues et lignes incomplètes\n"
            "- Unité `COL` normalisée en `UN`"
        )

    with col2:
        st.markdown("**Gestion des données**")
        st.markdown(
            "- Page **Fournisseurs** : renommage, suppression de mercuriale, visualisation détaillée\n"
            "- Page **Catalogue** : import du référentiel produits interne (Code Article, Désignation, Famille, Ref Fournis)\n"
            "- Ré-import catalogue = mise à jour sans doublon (upsert)\n"
            "- Cache de la session email pour éviter la perte de données au clic"
        )

        st.markdown("**Statistiques de ventes**")
        st.markdown(
            "- Import CSV ventes mensuel (format magasin)\n"
            "- Vue globale : classement produits sur 3 / 6 / 12 mois\n"
            "- Détail produit : sélection multiple, recherche par mot-clé\n"
            "- Meilleurs mois mis en avant (top 3)\n"
            "- Onglet **Météo & Calendrier** : température, précipitations, jours fériés, vacances scolaires"
        )

# ── V1 — prochaine itération ──────────────────────────────────────────────────

with st.container(border=True):
    st.subheader("V1 — Prochaine itération")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Matching mercuriale ↔ catalogue**")
        st.markdown(
            "- Rapprochement automatique entre `nom_produit` (fournisseur) et `Désignation` (catalogue interne)\n"
            "- Passe 1 : matching lexical rapide via **rapidfuzz** (seuil ≥ 85)\n"
            "- Passe 2 : matching sémantique via **sentence-transformers** si score < 85\n"
            "- Alerte manuelle si aucun match > 70\n"
            "- Interface de validation / correction du matching"
        )

        st.markdown("**Alertes ETL avancées**")
        st.markdown(
            "- Prix anormal (> ±40 % vs moyenne des 4 dernières semaines pour ce SKU)\n"
            "- Rupture fournisseur détectée"
        )

    with col2:
        st.markdown("**Moteur de prévision des ventes**")
        st.markdown(
            "- Calcul de `Vm` (moyenne des 4 derniers jours identiques)\n"
            "- Coefficient météo `C_meteo` (Open-Meteo J+1 vs normale 5 ans)\n"
            "- Coefficient calendrier `C_calendrier` (veille férié × 1.40, vacances × 0.80)\n"
            "- Quantité suggérée : `Q = Ve + S_sécurité − S_initial`\n"
            "- Stock de sécurité : `S_s = 0.5 × Vm`"
        )

        st.markdown("**Infrastructure**")
        st.markdown(
            "- Migration SQLite → **PostgreSQL 16 + TimescaleDB**\n"
            "- File de traitement asynchrone **Celery + Redis**\n"
            "- Parser PDF multi-fournisseurs"
        )

# ── V2 — horizon ─────────────────────────────────────────────────────────────

with st.container(border=True):
    st.subheader("V2 — Horizon")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Arbitrage automatique des achats**")
        st.markdown(
            "- Sélection du meilleur fournisseur par PUM (avec priorité local ≤ 110 % du prix import)\n"
            "- Optimisation du franco : réallocation des lignes non critiques pour éviter les frais de port\n"
            "- Journalisation de chaque décision d'arbitrage (audit + apprentissage)"
        )

        st.markdown("**Multi-magasins**")
        st.markdown(
            "- Authentification par magasin\n"
            "- Franco configurable par couple (fournisseur, magasin)\n"
            "- Zones scolaires et paramètres météo par magasin"
        )

    with col2:
        st.markdown("**Alertes & supervision**")
        st.markdown(
            "- Alerte franco critique (< 15 % du seuil)\n"
            "- Alerte démarque prévue (stock > vente estimée)\n"
            "- Dashboard de suivi en temps réel"
        )

        st.markdown("**Intégration**")
        st.markdown(
            "- API **FastAPI** exposée pour connexion ERP / caisse\n"
            "- Export tableau de commande prêt à envoyer au fournisseur\n"
            "- Frontend **Next.js** si besoin multi-utilisateurs"
        )
