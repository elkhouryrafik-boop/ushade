import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import datetime
import streamlit as st
import pandas as pd

from app.common import set_page_config, render_header
from config.settings import COLORS, MATERIAL_CODES
from src.marketplace import MarketplaceService

set_page_config(title="Stakeholder Marketplace")
render_header(title="Stakeholder Marketplace")

mkt  = MarketplaceService()
feed = mkt.get_transaction_feed()

# ── Metrics ───────────────────────────────────────────────────────────────────
total_tx  = len(feed)
completed = sum(1 for tx in feed if tx.get("status") == "completed")
total_m2  = sum(float(tx.get("quantity_m2", 0))  for tx in feed)
total_eur = sum(float(tx.get("brokerage_eur", 0)) for tx in feed)

mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Transactions", total_tx)
mc2.metric("Completed",    completed)
mc3.metric("M² Transacted", f"{total_m2:,.0f}")
mc4.metric("EUR Brokered",  f"€{total_eur:,.0f}")

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Transaction feed ───────────────────────────────────────────────────────────
st.markdown(
    "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 12px 0;'>RECENT TRANSACTIONS</div>",
    unsafe_allow_html=True,
)

STATUS_COLORS = {"completed": "#2B7A5E", "pending": "#DFA22E", "negotiating": "#0E8C8C"}

for tx in feed:
    color = STATUS_COLORS.get(tx.get("status", ""), "#A0A0A0")
    badge = tx.get("status", "unknown")
    mat_pill = (
        f'<span style="background:#F0F0F0;border-radius:4px;padding:2px 8px;'
        f'font-size:11px;color:#6B6B6B;">{tx.get("material","")}</span>'
    )
    st.markdown(
        f"""<div style="background:#FFFFFF;border-radius:12px;padding:18px 24px;
        box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:8px;">
          <div style="overflow:hidden;margin-bottom:8px;">
            <span style="float:right;background:{color};color:white;border-radius:4px;
            padding:2px 8px;font-size:10px;font-weight:700;">{badge}</span>
            <div style="font-size:13px;color:#0A0A0A;font-weight:500;">{tx.get("description","")}</div>
          </div>
          <div>{mat_pill}
            <span style="font-size:12px;color:#A0A0A0;margin-left:8px;">
              {tx.get("quantity_m2","")} m² · EUR {tx.get("brokerage_eur",0):,.0f} · {tx.get("date","")}
            </span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Stakeholder directory ──────────────────────────────────────────────────────
st.markdown(
    "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 12px 0;'>STAKEHOLDER DIRECTORY</div>",
    unsafe_allow_html=True,
)

tab_owner, tab_collector, tab_designer, tab_organizer = st.tabs(
    ["Owners", "Collectors", "Designers", "Organizers"]
)


def _render_cards(role: str):
    df_s = mkt.get_stakeholders(role)
    if df_s.empty:
        st.info("No stakeholders found.")
        return

    grid = st.columns(3)
    for i, (_, row) in enumerate(df_s.head(6).iterrows()):
        name      = str(row.get("name", "—"))
        role_desc = str(row.get("role", row.get("type", role))).strip()
        dist      = row.get("distance_to_forum_km", "")
        active    = str(row.get("status", "active")).lower() in ("active", "true", "1")
        dot_color = "#2B7A5E" if active else "#A0A0A0"

        mats_raw  = str(row.get("materials_offered", row.get("materials_needed", "")))
        mats      = [m.strip() for m in mats_raw.split(";") if m.strip() and mats_raw != "nan"]
        pill_html = "".join(
            f'<span style="background:#F0F0F0;border-radius:4px;padding:2px 8px;'
            f'font-size:11px;color:#6B6B6B;margin-right:4px;display:inline-block;'
            f'margin-bottom:4px;">{m}</span>'
            for m in mats
        )
        dist_str = f"{dist} km" if dist and str(dist) not in ("", "nan", "varies") else ""

        with grid[i % 3]:
            st.markdown(
                f"""<div style="background:#FFFFFF;border-radius:12px;padding:20px;
                box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:12px;">
                  <div style="font-size:14px;font-weight:700;color:#0A0A0A;margin:0 0 4px 0;">
                    <span style="color:{dot_color};">●</span> {name}
                  </div>
                  <div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;
                  margin:0 0 10px 0;">{role_desc[:60].upper()}</div>
                  <div style="margin-bottom:10px;">{pill_html if pill_html else '<span style="color:#A0A0A0;font-size:11px;">—</span>'}</div>
                  {f'<div style="font-size:12px;color:#A0A0A0;">{dist_str}</div>' if dist_str else ''}
                </div>""",
                unsafe_allow_html=True,
            )


with tab_owner:     _render_cards("owner")
with tab_collector: _render_cards("collector")
with tab_designer:  _render_cards("designer")
with tab_organizer: _render_cards("organizer")

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Matching engine ────────────────────────────────────────────────────────────
st.markdown(
    "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 12px 0;'>FIND MATERIALS FOR YOUR EVENT</div>",
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns(4)
with col1:
    mat_code  = st.selectbox("Material needed", list(MATERIAL_CODES.keys()),
                              format_func=lambda c: f"{c} — {MATERIAL_CODES[c]}")
with col2:
    qty_needed = st.number_input("Quantity (m²)", min_value=10.0, max_value=5000.0,
                                  value=200.0, step=10.0)
with col3:
    event_date = st.date_input("Event date",
                                value=datetime.date.today() + datetime.timedelta(days=30))
with col4:
    max_dist = st.slider("Max distance (km)", 5, 50, 30)

match_btn = st.button("Find Matches", type="primary", use_container_width=True)

if match_btn:
    results = mkt.match(mat_code, qty_needed, str(event_date), max_distance_km=max_dist)
    if results.empty:
        st.warning("No matches found. Try a wider date range or distance.")
    else:
        st.success(f"{len(results)} match(es) found")
        res_cols = st.columns(3)
        for i, (_, row) in enumerate(results.iterrows()):
            score = float(row.get("composite_score", 0))
            score_color = "#2B7A5E" if score >= 4 else ("#DFA22E" if score >= 2.5 else "#C0392B")
            with res_cols[i % 3]:
                st.markdown(
                    f"""<div style="background:#FFFFFF;border-radius:12px;padding:24px;
                    box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:12px;">
                      <div style="font-size:14px;font-weight:700;color:#0A0A0A;margin:0 0 8px 0;">{row["source_name"]}</div>
                      <div style="font-size:36px;font-weight:800;color:{score_color};margin:0 0 8px 0;line-height:1;">
                        {score:.1f}<span style="font-size:14px;color:#A0A0A0;">/5</span>
                      </div>
                      <div style="font-size:12px;color:#A0A0A0;margin:0 0 4px 0;">
                        {row["material_codes"]} · {row["quantity_m2"]} m² · {row["distance_to_forum_km"]} km
                      </div>
                      <div style="font-size:12px;color:#A0A0A0;">
                        {row["availability_start"]} → {row["availability_end"]}
                      </div>
                    </div>""",
                    unsafe_allow_html=True,
                )

# ── Post a request ─────────────────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
with st.expander("+ Post a material request"):
    rf1, rf2, rf3, rf4 = st.columns(4)
    with rf1:
        st.selectbox("Material needed", list(MATERIAL_CODES.keys()),
                     format_func=lambda c: f"{c} — {MATERIAL_CODES[c]}", key="req_mat")
    with rf2:
        st.number_input("Quantity (m²)", min_value=10.0, value=100.0, step=10.0, key="req_qty")
    with rf3:
        st.date_input("Date needed", key="req_date")
    with rf4:
        st.text_input("Contact email", key="req_contact")
    if st.button("Submit Request", key="req_submit"):
        st.success("Request submitted. Matching partners will be notified.")
