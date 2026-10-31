import hmac
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pydeck as pdk

st.set_page_config(page_title="COPAG – Tableau de bord logistique", page_icon="🚛", layout="wide")
sns.set_theme(style="whitegrid")

st.markdown(
    """
    <style>
    #MainMenu, footer {visibility: hidden;}
    [data-testid="stMetric"] {background: rgba(128,128,128,.08); border: 1px solid rgba(128,128,128,.2);
                              padding: .8rem 1rem; border-radius: 14px;}
    div[data-testid="stForm"] {border-radius: 16px; padding: 1.5rem;}
    div[data-testid="stForm"] button {width: 100%;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Connexion
# ---------------------------
USERNAME = "Amine"
PASSWORD = "2006"
MAX_TRIES = 5


def check_credentials(user: str, pwd: str) -> bool:
    ok_user = hmac.compare_digest(user.strip().casefold().encode(), USERNAME.casefold().encode())
    ok_pwd = hmac.compare_digest(pwd.encode(), PASSWORD.encode())
    return ok_user and ok_pwd


if not st.session_state.get("auth", False):
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown(
            "<div style='text-align: center; margin-top: 3rem;'>"
            "<div style='font-size: 3.5rem;'>🚛</div>"
            "<h2>COPAG Logistique</h2>"
            "<p style='opacity: .7;'>Connectez-vous pour accéder au tableau de bord</p></div>",
            unsafe_allow_html=True,
        )
        st.info(f"🔑 **Identifiant :** {USERNAME}  \n🔒 **Mot de passe :** {PASSWORD}")
        tries = st.session_state.get("tries", 0)
        if tries >= MAX_TRIES:
            st.error("Trop de tentatives. Rechargez la page pour réessayer.")
        else:
            with st.form("login"):
                user = st.text_input("Identifiant", placeholder="Entrez votre identifiant")
                pwd = st.text_input("Mot de passe", type="password", placeholder="••••")
                submitted = st.form_submit_button("Se connecter")
            if submitted:
                if check_credentials(user, pwd):
                    st.session_state["auth"] = True
                    st.session_state["tries"] = 0
                    st.rerun()
                else:
                    st.session_state["tries"] = tries + 1
                    st.error(f"Identifiant ou mot de passe incorrect ({MAX_TRIES - tries - 1} essai(s) restant(s)).")
    st.stop()

# ---------------------------
# Chargement des données
# ---------------------------
@st.cache_data
def load_data(path: str):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["trajet"] = df["origin_hub"] + " → " + df["destination_city"]
    return df

DATA_PATH = str(Path(__file__).parent / "copag_logistics.csv")
df = load_data(DATA_PATH)

st.markdown("## <div style='text-align: center;'>🚛 Tableau de bord des opérations logistiques COPAG</div>", unsafe_allow_html=True)

st.markdown(
    """
Ce tableau de bord explore les expéditions logistiques de la COPAG (Maroc).
Utilisez la barre latérale pour filtrer par hub d'origine, produit, mode de transport et période.
Les graphiques sont organisés **deux par ligne** pour une meilleure lisibilité.
"""
)

# ---------------------------
# Filtres (barre latérale)
# ---------------------------
st.sidebar.success(f"👤 Connecté : **{USERNAME}**")
if st.sidebar.button("Se déconnecter"):
    st.session_state["auth"] = False
    st.rerun()

st.sidebar.header("Filtres")

hubs = ["Tous"] + sorted(df["origin_hub"].dropna().unique().tolist())
selected_hub = st.sidebar.selectbox("Hub d'origine", hubs, key="hub_sel")

produits = ["Tous"] + sorted(df["product_category"].dropna().unique().tolist())
selected_prod = st.sidebar.selectbox("Catégorie de produit", produits, key="prod_sel")

modes = ["Tous"] + sorted(df["mode"].dropna().unique().tolist())
selected_mode = st.sidebar.selectbox("Mode de transport", modes, key="mode_sel")

# Période
min_date, max_date = df["date"].min().date(), df["date"].max().date()
date_range = st.sidebar.date_input(
    "Période",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
    key="date_range_sel",
)

# Application des filtres
mask = pd.Series(True, index=df.index)
if selected_hub != "Tous":
    mask &= (df["origin_hub"] == selected_hub)
if selected_prod != "Tous":
    mask &= (df["product_category"] == selected_prod)
if selected_mode != "Tous":
    mask &= (df["mode"] == selected_mode)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    mask &= (df["date"].between(start, end))

fdf = df.loc[mask].copy()

st.caption(f"Lignes filtrées : **{len(fdf)}** / {len(df)}")

if fdf.empty:
    st.warning("Aucune expédition ne correspond aux filtres sélectionnés.")
    st.stop()

# ---------------------------
# Indicateurs clés
# ---------------------------
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Expéditions", f"{len(fdf):,}".replace(",", " "))
with col2:
    st.metric("Retard moyen (min)", f"{fdf['delay_min'].mean():.1f}")
with col3:
    st.metric("Ponctualité", f"{fdf['on_time'].mean():.1%}")
with col4:
    st.metric("Coût total (MAD)", f"{fdf['cost_mad'].sum():,.0f}".replace(",", " "))
with col5:
    st.metric("CO₂ total (kg)", f"{fdf['co2_kg'].sum():,.0f}".replace(",", " "))

st.divider()

# ===========================
# LIGNE 1
# Série temporelle || Top trajets
# ===========================
left1, right1 = st.columns(2)

with left1:
    st.subheader("Série temporelle — Retard moyen par jour (Matplotlib)")
    ts = fdf.groupby("date", as_index=False)["delay_min"].mean()

    fig1, ax1 = plt.subplots()
    ax1.plot(ts["date"], ts["delay_min"], color="#1b6ca8", lw=1)
    ax1.axhline(0, color="gray", ls="--", lw=1)
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Retard moyen (min)")
    ax1.set_title("Retard moyen par jour")
    fig1.autofmt_xdate()
    fig1.tight_layout()
    st.pyplot(fig1, clear_figure=True)

with right1:
    st.subheader("Top 10 des trajets par nombre d'expéditions (Seaborn)")
    route_counts = fdf["trajet"].value_counts().head(10).reset_index()
    route_counts.columns = ["trajet", "count"]

    fig2, ax2 = plt.subplots()
    sns.barplot(data=route_counts, x="count", y="trajet", color="#17bebb", ax=ax2)
    ax2.set_xlabel("Expéditions")
    ax2.set_ylabel("Trajet")
    ax2.set_title("Top 10 des trajets")
    fig2.tight_layout()
    st.pyplot(fig2, clear_figure=True)

st.divider()

# ===========================
# LIGNE 2
# Boxplot || Heatmap de corrélation
# ===========================
left2, right2 = st.columns(2)

with left2:
    st.subheader("Distribution des retards par destination (Seaborn — Boxplot)")
    figb, axb = plt.subplots()
    sns.boxplot(data=fdf, x="delay_min", y="destination_city", color="#1b6ca8", ax=axb)
    axb.set_xlabel("Retard (min)")
    axb.set_ylabel("Destination")
    axb.set_title("Boxplot des retards par destination")
    figb.tight_layout()
    st.pyplot(figb, clear_figure=True)

with right2:
    st.subheader("Heatmap de corrélation (Seaborn)")
    num_cols = ["distance_km", "planned_duration_min", "actual_duration_min", "delay_min",
                "capacity_utilization", "fuel_liters", "co2_kg", "cost_mad", "quantity_tons"]
    corr = fdf[num_cols].corr(numeric_only=True)

    figh, axh = plt.subplots()
    sns.heatmap(corr, annot=True, fmt=".2f", annot_kws={"size": 7}, cmap="vlag", center=0, ax=axh)
    axh.set_title("Heatmap de corrélation")
    figh.tight_layout()
    st.pyplot(figh, clear_figure=True)

st.divider()

# ===========================
# LIGNE 3
# Statistiques par produit || Mode de transport
# ===========================
left3, right3 = st.columns(2)

with left3:
    st.subheader("Statistiques par produit (Matplotlib — Barres)")
    avg_delay_prod = (
        fdf.groupby("product_category", as_index=False)["delay_min"]
        .mean()
        .sort_values("delay_min", ascending=False)
    )
    fig5, ax5 = plt.subplots()
    ax5.bar(avg_delay_prod["product_category"], avg_delay_prod["delay_min"], color="#e4572e")
    ax5.set_xlabel("Catégorie de produit")
    ax5.set_ylabel("Retard moyen (min)")
    ax5.set_title("Retard moyen par catégorie de produit")
    plt.setp(ax5.get_xticklabels(), rotation=45, ha="right")
    fig5.tight_layout()
    st.pyplot(fig5, clear_figure=True)

with right3:
    st.subheader("Mode de transport (Matplotlib — Camembert)")
    mode_counts = fdf["mode"].value_counts().reset_index()
    mode_counts.columns = ["mode", "count"]
    fig6, ax6 = plt.subplots()
    ax6.pie(mode_counts["count"], labels=mode_counts["mode"], autopct="%1.1f%%", startangle=90,
            colors=["#1b6ca8", "#17bebb", "#e4572e"])
    ax6.axis("equal")
    ax6.set_title("Part des expéditions par mode de transport")
    st.pyplot(fig6, clear_figure=True)

st.divider()

# ===========================
# LIGNE 4
# Carte — Dernières positions || Flux de trajets
# ===========================
left4, right4 = st.columns(2)

with left4:
    st.subheader("Carte — Dernières positions connues")
    st.caption("Nuage de points rapide avec st.map")
    st.map(fdf[["lat", "lon"]].dropna().rename(columns={"lat": "latitude", "lon": "longitude"}))

with right4:
    st.subheader("Flux de trajets (PyDeck — Arcs)")
    st.caption("Arcs origine → destination agrégés")

    arcs = (
        fdf.groupby(["origin_hub", "destination_city", "o_lat", "o_lon", "d_lat", "d_lon"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    arcs["width"] = arcs["count"] / 4 + 1

    if not arcs.empty:
        arc_layer = pdk.Layer(
            "ArcLayer",
            data=arcs,
            get_source_position=["o_lon", "o_lat"],
            get_target_position=["d_lon", "d_lat"],
            get_width="width",
            get_source_color=[27, 108, 168],   # bleu
            get_target_color=[228, 87, 46],    # orange
            pickable=True,
        )
        center_lat = float(np.mean(arcs[["o_lat", "d_lat"]].to_numpy()))
        center_lon = float(np.mean(arcs[["o_lon", "d_lon"]].to_numpy()))
        view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=4, pitch=0)
        deck = pdk.Deck(layers=[arc_layer], initial_view_state=view_state,
                        tooltip={"text": "{origin_hub} → {destination_city} ({count})"})
        st.pydeck_chart(deck)
    else:
        st.info("Aucun arc à afficher pour les filtres actuels.")

st.divider()

# ---------------------------
# Données brutes (dépliable)
# ---------------------------
with st.expander("Afficher le tableau des données filtrées"):
    n_invalides = int((fdf["actual_duration_min"] <= 0).sum())
    if n_invalides:
        st.caption(f"⚠️ {n_invalides} expédition(s) ont une durée réelle négative ou nulle (anomalie dans les données).")
    st.dataframe(fdf.reset_index(drop=True))
    st.download_button("⬇️ Télécharger (CSV)", fdf.to_csv(index=False).encode("utf-8"),
                       "copag_filtre.csv", "text/csv")
