"""Central configuration: paths, seasons, overlay + cache policy."""
from __future__ import annotations

import os
from pathlib import Path

# backend/app/core/config.py -> parents[3] == project root (D:\jain-kochi-hackathon)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = Path(os.environ.get("JKH_DATA_DIR", PROJECT_ROOT / "data"))
INDICES_DIR = DATA_DIR / "indices"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = Path(os.environ.get("JKH_CACHE_DIR", DATA_DIR / "cache" / "overlays"))

SELECTED_SCENES = DATA_DIR / "selected_scenes.json"
REPORT_JSON = INDICES_DIR / "report.json"

# Window -> human season name (matches visualize.py --season-names usage)
SEASON_NAMES = {"A": "Premonsoon", "B": "Monsoon", "C": "Postmonsoon"}

# Max longest-side (px) for browser overlay PNGs
OVERLAY_MAX_DIM = int(os.environ.get("JKH_OVERLAY_MAX_DIM", "1200"))

# Layers served as overlays: {tif_suffix: kind}
OVERLAY_LAYERS = {
    "RGB": "rgb",
    "WQ_FLAG": "class",
    "CHLA_CLASS": "class",
    "TURB_CLASS": "class",
    "SPM_CLASS": "class",
    "NDTI": "cont",
    "NDCI": "cont",
    "NDSSI": "cont",
    "MNDWI": "cont",
    "CHLA": "cont",
    "SPM": "cont",
    "TURB": "cont",
}

# HTTP cache policy
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
STATS_CACHE = "public, max-age=300"

# CORS origins for local dev (Vite) — "*" is also enabled for the hackathon demo
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
