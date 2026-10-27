import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import datetime
import streamlit as st
import plotly.express as px
import pandas as pd

from app.common import set_page_config, render_header
from config.settings import COLORS
from src.predictions import PredictionEngine

set_page_config(title="Predictive Availability Engine")
render_header(title="Predictive Availability Engine")

months = st.slider("Months ahead", 3, 12, 6)
engine = PredictionEngine()
df = engine.all_predictions(months_ahead=months)

if not df.empty:
    df["midpoint"]    = (df["quantity_m2_min"] + df["quantity_m2_max"]) / 2
    df["date_dt"]     = pd.to_datetime(df["date"], errors="coerce")
    df["date_parsed"] = df["date_dt"].dt.date

# ── Metrics ───────────────────────────────────────────────────────────────────
total_events    = len(df)
high_conf_count = int((df["confidence"] >= 0.85).sum()) if not df.empty else 0
total_m2        = int(df["midpoint"].sum())              if not df.empty else 0

mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Events Predicted", total_events)
mc2.metric("High Confidence",  high_conf_count)
mc3.metric("M² Forecast",      f"{total_m2:,}")
mc4.metric("Months Ahead",     months)

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Urgency alerts ────────────────────────────────────────────────────────────
if not df.empty:
    today      = datetime.date.today()
    week_ahead = today + datetime.timedelta(days=7)
    this_week  = df[df["date_parsed"].between(today, week_ahead)]
    for _, row in this_week.iterrows():
        st.error(f"⚠  {row.get('source','—')} — {row.get('material_codes','—')} — collect by {row.get('date','—')}")

# ── Upcoming event cards ──────────────────────────────────────────────────────
if not df.empty:
    upcoming = df.sort_values("date_dt").head(3)
    st.markdown(
        "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 12px 0;'>UPCOMING EVENTS</div>",
        unsafe_allow_html=True,
    )
    ev_cols = st.columns(3)

    def _conf_color(c: float) -> str:
        if c >= 0.85: return "#2B7A5E"
        if c >= 0.65: return "#DFA22E"
        return "#C0392B"

    def _conf_label(c: float) -> str:
        if c >= 0.85: return "HIGH"
        if c >= 0.65: return "MEDIUM"
        return "LOW"

    def _mat_pills(codes_str: str) -> str:
        codes = [c.strip() for c in str(codes_str).split(",") if c.strip()]
        return "".join(
            f'<span style="background:#F0F0F0;border-radius:4px;padding:2px 8px;font-size:11px;color:#6B6B6B;margin-right:4px;display:inline-block;">{c}</span>'
            for c in codes
        )

    for i, (_, row) in enumerate(upcoming.iterrows()):
        conf  = float(row.get("confidence", 0))
        color = _conf_color(conf)
        label = _conf_label(conf)
        qty   = f"{row.get('quantity_m2_min','—')}–{row.get('quantity_m2_max','—')} m²"
        with ev_cols[i]:
            st.markdown(
                f"""<div style="background:#FFFFFF;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
                <div style="font-size:24px;font-weight:700;color:{color};margin:0 0 10px 0;">{row.get('date','—')}</div>
                <div style="font-size:14px;font-weight:600;color:#0A0A0A;margin:0 0 10px 0;">{row.get('source','—')}</div>
                <div style="margin-bottom:10px;">{_mat_pills(row.get('material_codes',''))}</div>
                <div style="font-size:12px;color:#A0A0A0;margin:0 0 8px 0;">{qty}</div>
                <div style="font-size:11px;font-weight:700;color:{color};">{label}</div>
                </div>""",
                unsafe_allow_html=True,
            )

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Forward Availability Calendar ─────────────────────────────────────────────
st.markdown(
    "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 12px 0;'>FORWARD AVAILABILITY CALENDAR</div>",
    unsafe_allow_html=True,
)
if not df.empty:
    source_colors = {
        "advertising": "#DFA22E",
        "festival":    "#2B7A5E",
        "construction":"#4746D8",
        "port":        "#0E8C8C",
    }
    fig = px.scatter(
        df, x="date_dt", y="source_type", size="midpoint", color="source_type",
        color_discrete_map=source_colors,
        hover_data=["event", "material_codes", "quantity_m2_min", "quantity_m2_max", "confidence"],
        labels={"date_dt": "Date", "source_type": "Source Type", "midpoint": "m²"},
    )
    fig.update_layout(
        height=340, plot_bgcolor="#FFFFFF", paper_bgcolor="#F8F7F4",
        font=dict(color="#6B6B6B", size=11), showlegend=True,
        margin=dict(l=0, r=0, t=20, b=20),
    )
    fig.update_xaxes(gridcolor="#F0F0F0", showgrid=True, title=None)
    fig.update_yaxes(showgrid=False, title=None)
    st.plotly_chart(fig, use_container_width=True)

# ── Confidence distribution ───────────────────────────────────────────────────
st.markdown(
    "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 12px 0;'>CONFIDENCE DISTRIBUTION</div>",
    unsafe_allow_html=True,
)
if not df.empty:
    def _conf_band(c: float) -> str:
        if c >= 0.85: return "High (≥85%)"
        if c >= 0.65: return "Medium (65–84%)"
        return "Low (<65%)"

    df["conf_band"] = df["confidence"].apply(_conf_band)
    band_counts     = df.groupby("conf_band").size().reset_index(name="count")
    band_color      = {"High (≥85%)": "#2B7A5E", "Medium (65–84%)": "#DFA22E", "Low (<65%)": "#A0A0A0"}
    fig2 = px.bar(band_counts, x="conf_band", y="count", color="conf_band",
                  color_discrete_map=band_color)
    fig2.update_layout(
        showlegend=False, plot_bgcolor="#FFFFFF", paper_bgcolor="#F8F7F4",
        font=dict(color="#6B6B6B", size=11),
        margin=dict(l=0, r=0, t=20, b=0), height=240,
    )
    fig2.update_xaxes(title=None, showgrid=False)
    fig2.update_yaxes(gridcolor="#F0F0F0", title=None)
    st.plotly_chart(fig2, use_container_width=True)

# ── Monthly forecast table ────────────────────────────────────────────────────
st.markdown(
    "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 12px 0;'>MONTHLY FORECAST</div>",
    unsafe_allow_html=True,
)
monthly = engine.monthly_forecast(months_ahead=months)
if not monthly.empty:
    st.dataframe(monthly.set_index("month"), use_container_width=True, height=200, hide_index=False)

gaps = engine.gap_analysis(monthly)
if gaps:
    st.caption("Supply gaps detected: " + " · ".join(gaps))
