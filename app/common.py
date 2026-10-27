import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from config.settings import PROJECT_NAME, FULL_NAME, TAGLINE, COLORS
from src.detection import DetectionService

_CSS = """<style>
[data-testid="stAppViewContainer"] { background: #F8F7F4; }
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #EFEFEF; }
[data-testid="stSidebar"] * { font-size: 13px; }
h1 { font-size: 32px !important; font-weight: 700 !important; color: #0A0A0A !important; letter-spacing: -0.5px !important; }
h2 { font-size: 20px !important; font-weight: 600 !important; color: #0A0A0A !important; }
h3 { font-size: 16px !important; font-weight: 600 !important; color: #0A0A0A !important; }
p, li { font-size: 13px !important; color: #6B6B6B !important; }
[data-testid="metric-container"] { background: #FFFFFF; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
[data-testid="metric-container"] label { font-size: 11px !important; font-weight: 700 !important; letter-spacing: 2px !important; text-transform: uppercase !important; color: #A0A0A0 !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 700 !important; color: #0A0A0A !important; }
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
.stButton button { background: #0A0A0A; color: #FFFFFF; border: none; border-radius: 8px; padding: 10px 24px; font-size: 13px; font-weight: 600; letter-spacing: 0.3px; }
.stButton button:hover { background: #2B7A5E; }
.stSelectbox, .stMultiSelect, .stSlider { font-size: 13px !important; }
hr { border: none; border-top: 1px solid #EFEFEF; margin: 32px 0; }
</style>"""


def set_page_config(title: str = PROJECT_NAME, icon: str = "◆", layout: str = "wide"):
    st.set_page_config(page_title=title, page_icon=icon, layout=layout)
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header(title: str = PROJECT_NAME, subtitle: str | None = None):
    st.markdown(
        "<div style='font-size:11px;font-weight:700;letter-spacing:2px;color:#A0A0A0;margin:0 0 6px 0;'>U-SHADE · MATERIAL INTELLIGENCE</div>",
        unsafe_allow_html=True,
    )
    margin = "8px" if subtitle else "0"
    st.markdown(
        f"<h1 style='margin:0 0 {margin};'>{title}</h1>",
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f"<div style='font-size:13px;color:#6B6B6B;margin:0;'>{subtitle}</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "<hr style='border:none;border-top:1px solid #EFEFEF;margin:24px 0;'>",
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_detection_service() -> DetectionService:
    return DetectionService()
