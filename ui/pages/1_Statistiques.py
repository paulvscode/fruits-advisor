"""Page Statistiques — visualisation des ventes historiques par produit."""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.stats.sales import parse_sales_csv
from core.weather.open_meteo import fetch_monthly_weather
from core.calendar.fr_calendar import public_holidays_by_month, school_holidays_by_month


@st.cache_data(ttl=3600)
def _cached_weather(lat: float, lon: float, start: str, end: str):
    return fetch_monthly_weather(lat, lon, start, end)


@st.cache_data(ttl=86400)
def _cached_school_hols(months_tuple: tuple, zone: str):
    return school_holidays_by_month(list(months_tuple), zone)

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
    st.divider()
    st.subheader("Localisation")
    city_name = st.text_input("Ville", value="Le Havre")
    lat_col, lon_col = st.columns(2)
    lat = lat_col.number_input("Latitude", value=49.4938, step=0.01, format="%.4f")
    lon = lon_col.number_input("Longitude", value=0.1077, step=0.01, format="%.4f")
    zone = st.selectbox("Zone scolaire", ["A", "B", "C"], index=1)

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

tab_global, tab_detail, tab_context = st.tabs(["Vue globale", "Détail produit", "Météo & Calendrier"])

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
    if "search_results" not in st.session_state:
        st.session_state["search_results"] = []

    # ── Sélection groupée par mot-clé ─────────────────────────────────────
    # on_change fires when the user presses Enter or blurs the field
    def _run_search():
        term = st.session_state.get("search_quick", "").strip().lower()
        st.session_state["search_results"] = (
            [p for p in all_products if term in p.lower()] if term else []
        )

    sc1, sc2 = st.columns([5, 1])
    sc1.text_input(
        "Sélection groupée par mot-clé",
        placeholder="Ex: melon, citron...",
        key="search_quick",
        on_change=_run_search,
    )
    if sc2.button("Rechercher"):
        _run_search()

    matching = st.session_state["search_results"]
    if matching:
        to_add = st.multiselect(
            f"{len(matching)} résultat(s) — affiner avant d'ajouter :",
            options=matching,
            default=matching,
        )
        mc1, mc2, _ = st.columns([2, 2, 8])
        if mc1.button(f"Ajouter ({len(to_add)})", disabled=not to_add):
            current = list(st.session_state.get("multiselect_products", []))
            st.session_state["multiselect_products"] = list(dict.fromkeys(current + to_add))
        if mc2.button(f"Seulement ({len(to_add)})", disabled=not to_add):
            st.session_state["multiselect_products"] = to_add[:]
    elif st.session_state.get("search_quick", "").strip():
        st.caption("Aucun produit correspondant.")

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

    # ── Highlights : meilleurs mois ───────────────────────────────────────
    st.divider()
    st.subheader("Meilleurs mois")

    df_highlights = (
        df_sel.groupby(["mois", "mois_label"])[value_col_d]
        .sum()
        .reset_index()
        .sort_values(value_col_d, ascending=False)
        .reset_index(drop=True)
    )

    total_val = df_highlights[value_col_d].sum()
    n_show = min(3, len(df_highlights))
    rank_labels = ["Meilleur mois", "2e mois", "3e mois"]

    h_cols = st.columns(n_show)
    for i in range(n_show):
        row = df_highlights.iloc[i]
        pct = row[value_col_d] / total_val * 100 if total_val > 0 else 0
        with h_cols[i]:
            st.metric(
                label=f"{rank_labels[i]} : {row['mois_label']}",
                value=f"{row[value_col_d]:,.1f} {y_label_d}",
                delta=f"{pct:.0f}% du total",
                delta_color="off",
            )
            if len(selected_products) > 1:
                best_prod = (
                    df_sel[df_sel["mois"] == row["mois"]]
                    .groupby("designation")[value_col_d]
                    .sum()
                    .idxmax()
                )
                st.caption(f"Leadeur : {best_prod}")

    st.divider()

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

# ── TAB 3 : Météo & Calendrier ────────────────────────────────────────────────

with tab_context:
    st.subheader(f"Météo & Calendrier — {city_name}")

    start_str = months[0].strftime("%Y-%m-%d")
    end_str = months[-1].strftime("%Y-%m-%d")

    # ── Fetch weather ─────────────────────────────────────────────────────
    with st.spinner("Chargement des données météo…"):
        try:
            df_weather = _cached_weather(lat, lon, start_str, end_str)
            weather_ok = True
        except Exception as exc:
            st.warning(f"Météo indisponible : {exc}")
            df_weather = pd.DataFrame(columns=["mois", "temp_mean", "precip_sum"])
            weather_ok = False

    # ── Fetch calendar ────────────────────────────────────────────────────
    with st.spinner("Chargement du calendrier scolaire…"):
        pub_hols = public_holidays_by_month(months)
        try:
            school_hols = _cached_school_hols(tuple(months), zone)
        except Exception:
            school_hols = {m.replace(day=1): None for m in months}

    # ── Build combined table ──────────────────────────────────────────────
    sales_by_month = (
        df.groupby("mois")["valeur"]
        .sum()
        .reset_index()
        .rename(columns={"valeur": "ventes"})
    )

    rows = []
    for ts in months:
        key = ts.replace(day=1)
        label = month_label(ts)
        ventes = sales_by_month.loc[sales_by_month["mois"] == ts, "ventes"]
        ventes = ventes.values[0] if len(ventes) else 0.0

        w = df_weather[df_weather["mois"] == key] if weather_ok else pd.DataFrame()
        temp = f"{w['temp_mean'].values[0]:.1f} °C" if len(w) else "—"
        precip = f"{w['precip_sum'].values[0]:.0f} mm" if len(w) else "—"

        hols = pub_hols.get(key, [])
        hols_str = ", ".join(hols) if hols else "—"

        school = school_hols.get(key)
        school_str = school if school else "—"

        rows.append({
            "Mois": label,
            f"Ventes ({unite_label})": round(ventes, 1),
            "Temp. moy.": temp,
            "Précip.": precip,
            "Jours fériés": hols_str,
            f"Vacances (Zone {zone})": school_str,
        })

    df_ctx = pd.DataFrame(rows)
    st.dataframe(df_ctx, hide_index=True, use_container_width=True)

    # ── Charts ────────────────────────────────────────────────────────────
    if weather_ok and not df_weather.empty:
        st.divider()

        # Merge sales + weather on the same months
        df_plot = sales_by_month.copy()
        df_plot["mois_label"] = df_plot["mois"].apply(month_label)
        df_weather["mois_label"] = df_weather["mois"].apply(month_label)
        df_merged = df_plot.merge(df_weather[["mois", "temp_mean", "precip_sum"]], on="mois", how="left")
        df_merged["mois_label"] = df_merged["mois"].apply(month_label)
        x_order = df_merged["mois_label"].tolist()

        # ── Ventes + Température (dual axis) ─────────────────────────────
        st.markdown("**Ventes vs Température**")
        base = alt.Chart(df_merged).encode(
            x=alt.X("mois_label:O", sort=x_order, title="Mois",
                     axis=alt.Axis(labelAngle=-45))
        )
        bars = base.mark_bar(opacity=0.6, color="#4C78A8").encode(
            y=alt.Y("ventes:Q", title=f"Ventes ({unite_label})", axis=alt.Axis(titleColor="#4C78A8"))
        )
        line_temp = base.mark_line(point=True, color="#E45756").encode(
            y=alt.Y("temp_mean:Q", title="Température (°C)",
                     scale=alt.Scale(zero=False),
                     axis=alt.Axis(titleColor="#E45756"))
        )
        chart_dual = (
            alt.layer(bars, line_temp)
            .resolve_scale(y="independent")
            .properties(height=300)
        )
        st.altair_chart(chart_dual, use_container_width=True)

        # ── Précipitations ────────────────────────────────────────────────
        st.markdown("**Précipitations mensuelles**")
        chart_precip = (
            alt.Chart(df_merged)
            .mark_bar(color="#76B7B2")
            .encode(
                x=alt.X("mois_label:O", sort=x_order, title="Mois",
                          axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("precip_sum:Q", title="Précipitations (mm)"),
                tooltip=["mois_label:O", "precip_sum:Q"],
            )
            .properties(height=200)
        )
        st.altair_chart(chart_precip, use_container_width=True)
