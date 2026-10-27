import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from app.common import set_page_config, get_detection_service

set_page_config(title="U-SHADE", icon="◆")

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:#0A0A0A;border-radius:16px;padding:56px 48px;margin-bottom:40px;">
  <div style="font-size:11px;font-weight:700;letter-spacing:3px;color:#444444;margin:0 0 16px 0;">BARCELONA · 2026</div>
  <div style="font-size:64px;font-weight:800;color:#FFFFFF;letter-spacing:-2px;margin:0 0 16px 0;line-height:1;">U-SHADE</div>
  <div style="font-size:18px;color:#2B7A5E;margin:0 0 10px 0;font-weight:500;">Urban Shade Infrastructure from Reclaimed Materials</div>
  <div style="font-size:14px;color:#666666;font-style:italic;margin:0;">The city already has everything it needs.</div>
</div>
""", unsafe_allow_html=True)

# ── Three question cards ──────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("""
    <div style="background:#FFFFFF;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.06);height:180px;">
      <div style="font-size:48px;font-weight:800;color:#2B7A5E;margin:0 0 16px 0;line-height:1;">01</div>
      <div style="font-size:16px;font-weight:600;color:#0A0A0A;margin:0 0 12px 0;">What materials exist today?</div>
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;">MATERIAL DETECTION</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown("""
    <div style="background:#FFFFFF;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.06);height:180px;">
      <div style="font-size:48px;font-weight:800;color:#DFA22E;margin:0 0 16px 0;line-height:1;">02</div>
      <div style="font-size:16px;font-weight:600;color:#0A0A0A;margin:0 0 12px 0;">What becomes available in 90 days?</div>
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;">PREDICTIVE ENGINE</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown("""
    <div style="background:#FFFFFF;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.06);height:180px;">
      <div style="font-size:48px;font-weight:800;color:#0E8C8C;margin:0 0 16px 0;line-height:1;">03</div>
      <div style="font-size:16px;font-weight:600;color:#0A0A0A;margin:0 0 12px 0;">Who owns them and who needs them?</div>
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;">MARKETPLACE</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)

# ── Five metrics ──────────────────────────────────────────────────────────────
svc = get_detection_service()
summary = svc.get_summary()

mc1, mc2, mc3, mc4, mc5 = st.columns(5)
mc1.metric("Detection Sources", summary["total_sources"])
mc2.metric("M² Available",      f"{summary['total_m2']:,.0f}")
mc3.metric("CO₂ Avoided",       f"{summary['total_carbon_avoided_tonnes']:.1f} t")
mc4.metric("Material Types",    len(summary["materials_detected"]))
mc5.metric("Events · 30 Days",  4)

st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)

# ── Statement ─────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;font-size:18px;color:#6B6B6B;font-style:italic;max-width:720px;margin:0 auto;line-height:1.7;">
  2.3M tonnes of construction waste. 12,000 m² of billboard vinyl. Every summer festival.<br>
  U-SHADE harvests this before it becomes landfill.
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)
st.markdown("<hr style='border:none;border-top:1px solid #EFEFEF;margin:0;'>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align:center;font-size:11px;color:#A0A0A0;letter-spacing:2px;padding:24px 0;'>U-SHADE · URBAN SHADE INFRASTRUCTURE FROM RECLAIMED MATERIALS · BARCELONA 2026</div>",
    unsafe_allow_html=True,
)
