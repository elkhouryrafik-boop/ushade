import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_NAME = "U-SHADE"
FULL_NAME = "Urban Shade Infrastructure from Reclaimed Materials"
TAGLINE = "The city already has everything it needs."
VERSION = "1.0.0-MVP"

DEPLOYMENT_SITE = "Parc del Forum"
SITE_LAT = 41.4106
SITE_LON = 2.2203

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

EF_TRUCK = 0.0001
EF_INSTALL_M2 = 0.30
EF_EOL_M2 = 0.05
CARBON_PERMANENT_SHADE_LOW = 120
CARBON_PERMANENT_SHADE_HIGH = 180
CARBON_TARGET_M2 = 5.0

COLORS = {
    "black": "#0A0A0A",
    "paper": "#F2F0ED",
    "ink": "#16181D",
    "green": "#2B7A5E",
    "green2": "#3DA67A",
    "amber": "#DFA22E",
    "red": "#C0392B",
    "teal": "#0E8C8C",
    "heat": "#E8462A",
    "indigo": "#4746D8",
    "grey": "#A8AAB6",
    "white": "#FFFFFF",
}

MATERIAL_CODES = {
    "SCF": "Scaffold tube 48.3mm",
    "ALU": "Aluminium event truss",
    "PAL": "Euro pallet (EPAL)",
    "HRS": "Heras fence panel",
    "CHR": "Stadium chair",
    "PVC": "PVC billboard vinyl",
    "NET": "Industrial shade net (HDPE)",
    "TRP": "Recycled PE tarpaulin",
    "SHR": "PE yacht shrink-wrap",
    "CRP": "PP festival carpet",
}

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
EXPORT_DIR = ROOT_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)
