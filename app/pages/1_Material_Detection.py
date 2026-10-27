import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import folium
import plotly.express as px
import pandas as pd
from streamlit_folium import st_folium

from app.common import set_page_config, render_header, get_detection_service
from config.settings import COLORS, MATERIAL_CODES, SITE_LAT, SITE_LON

set_page_config(title="Material Detection Dashboard")
render_header(title="Material Detection Dashboard")

svc = get_detection_service()
summary = svc.get_summary()

# ── Metrics ───────────────────────────────────────────────────────────────────
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Total Sources", summary["total_sources"])
mc2.metric("M² Available",  f"{summary['total_m2']:,.0f}")
mc3.metric("CO₂ Avoided",   f"{summary['total_carbon_avoided_tonnes']:.1f} t")
mc4.metric("Expiring Soon", summary["expiring_count"])

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin-bottom:12px;'>FILTERS</div>",
        unsafe_allow_html=True,
    )
    source_types    = ["advertising", "festival", "construction", "industrial", "port", "municipal"]
    selected_types  = st.multiselect("Source type",   source_types,               default=[])
    selected_codes  = st.multiselect("Material code", list(MATERIAL_CODES.keys()), default=[])
    max_dist        = st.slider("Max distance (km)", 5, 50, 50)
    conditions      = st.multiselect("Condition", ["excellent", "good", "fair", "poor"], default=[])

df_all = svc.filter(
    source_type=selected_types   if selected_types  else None,
    material_code=selected_codes if selected_codes  else None,
    max_distance_km=max_dist,
    condition=conditions         if conditions       else None,
)

# ── Urgency alerts ────────────────────────────────────────────────────────────
expiring = svc.get_expiring(days=7)
if not expiring.empty:
    for _, r in expiring.iterrows():
        st.error(f"⚠  {r['source_name']} — {r['material_codes']} ({r['quantity_m2']} m²) — collect by {r['availability_end']}")

# ── Map ───────────────────────────────────────────────────────────────────────
STATUS_COLOR = {
    "available_now": "green",
    "expiring":      "red",
    "available_30d": "orange",
    "available_90d": "gray",
    "future":        "lightgray",
    "unknown":       "lightgray",
}

m = folium.Map(location=[SITE_LAT, SITE_LON], zoom_start=11, tiles="CartoDB positron")
folium.Marker(
    [SITE_LAT, SITE_LON],
    popup="Parc del Fòrum",
    icon=folium.Icon(color="black", icon="star"),
).add_to(m)

for _, row in df_all.iterrows():
    lat = row.get("location_lat")
    lon = row.get("location_lon")
    if pd.isna(lat) or pd.isna(lon):
        continue
    color = STATUS_COLOR.get(str(row.get("status", "")), "gray")
    popup_html = (
        f"<b>{row['source_name']}</b><br>"
        f"Materials: {row['material_codes']}<br>"
        f"Qty: {row['quantity_m2']} m² / {row['quantity_kg']} kg<br>"
        f"Condition: {row['condition']}<br>"
        f"Carbon avoided: {row['carbon_avoided_kg']} kgCO₂e<br>"
        f"Contact: {row['contact']}"
    )
    folium.CircleMarker(
        location=[lat, lon],
        radius=9,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.75,
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=row["source_name"],
    ).add_to(m)

st_folium(m, height=520, use_container_width=True)

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Table + Bar chart ─────────────────────────────────────────────────────────
col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown(
        "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin-bottom:12px;'>DETECTION RECORDS</div>",
        unsafe_allow_html=True,
    )
    display_df = df_all.rename(columns={
        "material_codes":       "code",
        "source_name":          "name",
        "source_type":          "type",
        "distance_to_forum_km": "distance_km",
    })
    cols_show = [c for c in ["code", "name", "type", "condition", "distance_km", "status"]
                 if c in display_df.columns]
    st.dataframe(display_df[cols_show], use_container_width=True, hide_index=True, height=320)

with col_right:
    st.markdown(
        "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin-bottom:12px;'>M² BY SOURCE TYPE</div>",
        unsafe_allow_html=True,
    )
    if not df_all.empty and "source_type" in df_all.columns:
        type_df = df_all.groupby("source_type")["quantity_m2"].sum().reset_index()
        type_df.columns = ["Source Type", "m²"]
        fig_bar = px.bar(
            type_df, x="m²", y="Source Type", orientation="h",
            color_discrete_sequence=["#2B7A5E"],
        )
        fig_bar.update_layout(
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#F8F7F4",
            font=dict(color="#6B6B6B", size=11),
            showlegend=False,
            margin=dict(l=0, r=0, t=20, b=0),
            height=320,
        )
        fig_bar.update_xaxes(gridcolor="#F0F0F0", showgrid=True, title=None)
        fig_bar.update_yaxes(showgrid=False, title=None)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No data to chart.")
