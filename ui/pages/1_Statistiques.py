"""Page Statistiques — visualisation des ventes historiques par produit."""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.stats.sales import parse_sales_csv

# ── Config ────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Statistiques — Fruits Advisor", layout="wide")
st.title("Statistiques des ventes")
st.caption("Analyse de l'historique des ventes par produit")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Importer les ventes")
    uploaded = st.file_uploader(
        "Fichier CSV des ventes",
        type=["csv"],
        help="Format attendu : Code | Désignation | MM AA | MM AA | …",
    )
    sep_choice = st.selectbox(
        "Séparateur",
        options=["Auto-détection", "Tabulation (\\t)", "Point-virgule (;)", "Virgule (,)"],
        index=0,
    )
    st.divider()
    unite_label = st.text_input(
        "Unité des valeurs", value="kg", help="Ex: kg, pièces, €"
    )

if not uploaded:
    st.info("Importe un fichier CSV de ventes dans le panneau de gauche pour commencer.")
    st.caption("Format attendu des colonnes : `Code ; Désignation ; 06 26 ; 05 26 ; 04 26 ; …`")
    st.stop()

# ── Parse ─────────────────────────────────────────────────────────────────────

with st.spinner("Chargement des données…"):
    import tempfile, os

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    sep_map = {
        "Auto-détection": None,
        "Tabulation (\\t)": "\t",
        "Point-virgule (;)": ";",
        "Virgule (,)": ",",
    }
    sep = sep_map[sep_choice]

    # Auto-detect: try tab then semicolon
    if sep is None:
        import csv as _csv
        raw_bytes = open(tmp_path, "rb").read(2048)
        sample = raw_bytes.decode("utf-8-sig", errors="replace")
        dialect = _csv.Sniffer().sniff(sample, delimiters="\t;,")
        sep = dialect.delimiter

    try:
        result = parse_sales_csv(tmp_path, separator=sep)
    except Exception as e:
        st.error(f"Erreur lors du parsing : {e}")
        st.stop()
    finally:
        os.unlink(tmp_path)

df: pd.DataFrame = result["df_long"]
months: list[pd.Timestamp] = result["months"]

if df.empty:
    st.warning("Aucune donnée exploitable dans ce fichier.")
    st.stop()

if result["alertes"]:
    with st.expander(f"{len(result['alertes'])} alerte(s)", expanded=False):
        for a in result["alertes"]:
            st.warning(a)

# ── Summary metrics ───────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
col1.metric("Produits", df["designation"].nunique())
col2.metric("Période", f"{months[0].strftime('%m/%Y')} → {months[-1].strftime('%m/%Y')}")
col3.metric("Mois couverts", len(months))

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_global, tab_detail = st.tabs(["Vue globale", "Détail produit"])

# ── Helpers ───────────────────────────────────────────────────────────────────

_MONTHS_FR = {
    1: "Janv.", 2: "Févr.", 3: "Mars", 4: "Avr.",
    5: "Mai", 6: "Juin", 7: "Juil.", 8: "Août",
    9: "Sept.", 10: "Oct.", 11: "Nov.", 12: "Déc.",
}

def month_label(ts: pd.Timestamp) -> str:
    return f"{_MONTHS_FR[ts.month]} {ts.year % 100:02d}"


def render_chart(
    df_pivot: pd.DataFrame,
    chart_type: str,
    y_title: str = "",
    height: int = 380,
) -> None:
    """
    Render a bar or line chart from a pivoted DataFrame.
    df_pivot : index = mois_label (str), columns = product names, values = metric.
    chart_type : "Barres" | "Courbe"
    Explicit sort order on x-axis = insertion order of the DataFrame rows.
    """
    if df_pivot.empty or df_pivot.shape[1] == 0:
        return

    x_order = df_pivot.index.tolist()
    index_name = df_pivot.index.name or "Mois"

    df_plot = (
        df_pivot.reset_index()
        .melt(id_vars=index_name, var_name="Produit", value_name="Valeur")
        .dropna(subset=["Valeur"])
    )

    if df_plot.empty:
        return

    x_enc = alt.X(
        index_name,
        sort=x_order,
        title="Mois",
        axis=alt.Axis(labelAngle=-45, labelOverlap=False),
    )
    y_enc = alt.Y("Valeur:Q", title=y_title)
    # Hide legend when too many products (Vega-Lite cap ~29 symbols)
    legend = alt.Legend() if df_pivot.shape[1] <= 25 else None
    color_enc = alt.Color("Produit:N", legend=legend)

    base = alt.Chart(df_plot).encode(x=x_enc, y=y_enc, color=color_enc)

    if chart_type == "Courbe":
        chart = base.mark_line(point=True)
    else:
        chart = base.mark_bar()

    st.altair_chart(chart.properties(height=height), use_container_width=True)


MONTH_RANGE_OPTIONS = {
    "3 derniers mois": 3,
    "6 derniers mois": 6,
    "12 derniers mois": 12,
    "Tout l'historique": len(months),
}

# ── TAB 1 : Vue globale ───────────────────────────────────────────────────────

with tab_global:
    st.subheader("Classement des produits")

    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 2, 2, 2])
    periode_label = ctrl1.selectbox("Période", list(MONTH_RANGE_OPTIONS.keys()), index=1)
    n_mois = MONTH_RANGE_OPTIONS[periode_label]
    top_n = ctrl2.slider("Nombre de produits affichés", 5, 50, 20)
    mode = ctrl3.radio("Valeur affichée", ["Brute (total mois)", "Par jour (moyenne)"], horizontal=True)
    chart_type_global = ctrl4.radio("Vue évolution", ["Barres", "Courbe"], horizontal=True, key="chart_global")

    # Filter to selected period
    cutoff = months[-1] - pd.DateOffset(months=n_mois - 1)
    df_period = df[df["mois"] >= cutoff]

    value_col = "valeur" if mode.startswith("Brute") else "valeur_par_jour"
    y_label = f"{unite_label} (total)" if mode.startswith("Brute") else f"{unite_label}/jour (moy.)"

    # Aggregate per product
    df_agg = (
        df_period.groupby("designation")[value_col]
        .sum()
        .reset_index()
        .sort_values(value_col, ascending=False)
        .head(top_n)
    )
    df_agg.columns = ["Produit", y_label]
    df_agg = df_agg.sort_values(y_label, ascending=True)  # ascending for horizontal bars

    st.bar_chart(
        df_agg.set_index("Produit"),
        horizontal=True,
        height=max(300, top_n * 22),
        use_container_width=True,
    )

    st.divider()
    st.subheader(f"Évolution mensuelle — Top {top_n} produits")

    top_products = (
        df_period.groupby("designation")[value_col]
        .sum()
        .nlargest(top_n)
        .index.tolist()
    )

    df_top_evolution = (
        df_period[df_period["designation"].isin(top_products)]
        .groupby(["mois", "designation"])[value_col]
        .sum()
        .reset_index()
        .sort_values("mois")
        .pivot(index="mois", columns="designation", values=value_col)
        .fillna(0)
    )
    df_top_evolution.index = [month_label(ts) for ts in df_top_evolution.index]
    df_top_evolution.index.name = "Mois"

    render_chart(df_top_evolution, chart_type_global, y_title=y_label, height=380)

# ── TAB 2 : Détail produit ────────────────────────────────────────────────────

with tab_detail:
    all_products = sorted(df["designation"].unique().tolist())

    # Initialize the widget's own session state key on first load
    if "multiselect_products" not in st.session_state:
        st.session_state["multiselect_products"] = all_products[:]

    # ── Sélection groupée par mot-clé ─────────────────────────────────────
    search_quick = st.text_input(
        "Sélection groupée par mot-clé",
        placeholder="Ex: melon, citron... — puis Ajouter ou Seulement",
        key="search_quick",
    )
    if search_quick.strip():
        matching = [p for p in all_products if search_quick.strip().lower() in p.lower()]
        mc1, mc2, mc3 = st.columns([2, 2, 8])
        if mc1.button(f"Ajouter ({len(matching)})", disabled=not matching):
            current = list(st.session_state.get("multiselect_products", []))
            st.session_state["multiselect_products"] = list(dict.fromkeys(current + matching))
        if mc2.button(f"Seulement ({len(matching)})", disabled=not matching):
            st.session_state["multiselect_products"] = matching[:]
        if matching:
            mc3.caption(f"Correspond à : {', '.join(matching[:8])}{'...' if len(matching) > 8 else ''}")
        else:
            mc3.caption("Aucun produit correspondant.")

    # ── Tout sélectionner / Tout désélectionner ───────────────────────────
    btn1, btn2, _ = st.columns([1.2, 1.5, 9.3])
    if btn1.button("Tout sélectionner"):
        st.session_state["multiselect_products"] = all_products[:]
    if btn2.button("Tout désélectionner"):
        st.session_state["multiselect_products"] = []

    d1, d2, d3 = st.columns([5, 1, 1])
    selected_products = d1.multiselect(
        "Produit(s)",
        all_products,
        placeholder="Sélectionne un ou plusieurs produits…",
        key="multiselect_products",
    )
    mode_detail = d2.radio(
        "Valeur", ["Brute", "Par jour"], horizontal=True, key="mode_detail"
    )
    chart_type_detail = d3.radio(
        "Vue", ["Barres", "Courbe"], horizontal=True, key="chart_detail"
    )

    if not selected_products:
        st.info("Sélectionne au moins un produit.")
        st.stop()

    value_col_d = "valeur" if mode_detail == "Brute" else "valeur_par_jour"
    y_label_d = unite_label if mode_detail == "Brute" else f"{unite_label}/jour"

    df_sel = df[df["designation"].isin(selected_products)].copy()
    df_sel["mois_label"] = df_sel["mois"].apply(month_label)

    # KPIs uniquement si 1 seul produit sélectionné
    if len(selected_products) == 1:
        prod = selected_products[0]
        df_prod = df_sel.sort_values("mois")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Mois le + actif", df_prod.nlargest(1, "valeur")["mois_label"].values[0])
        k2.metric(f"Pic mensuel ({unite_label})", f"{df_prod['valeur'].max():,.1f}")
        k3.metric(f"Moy/mois ({unite_label})", f"{df_prod['valeur'].mean():,.1f}")
        k4.metric(f"Moy/jour ({unite_label})", f"{df_prod['valeur_par_jour'].mean():,.2f}")

    n = len(selected_products)
    st.caption(f"{n} produit{'s' if n > 1 else ''} sélectionné{'s' if n > 1 else ''}")

    # Graphique principal (barre ou courbe)
    df_pivot = (
        df_sel.groupby(["mois", "designation"])[value_col_d]
        .sum()
        .reset_index()
        .sort_values("mois")
        .pivot(index="mois", columns="designation", values=value_col_d)
        .fillna(0)
    )
    df_pivot.index = [month_label(ts) for ts in df_pivot.index]
    df_pivot.index.name = "Mois"

    render_chart(df_pivot, chart_type_detail, y_title=y_label_d, height=max(400, n * 8))

    # Tableau récapitulatif
    with st.expander("Récapitulatif par produit", expanded=len(selected_products) <= 20):
        recap = (
            df_sel.groupby("designation")
            .agg(
                total=("valeur", "sum"),
                moyenne_mensuelle=("valeur", "mean"),
                moyenne_par_jour=("valeur_par_jour", "mean"),
            )
            .reset_index()
            .sort_values("total", ascending=False)
        )
        recap.columns = ["Produit", f"Total ({unite_label})", f"Moy/mois ({unite_label})", f"Moy/jour ({unite_label})"]
        st.dataframe(recap, hide_index=True, use_container_width=True)
