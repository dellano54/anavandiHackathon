"""Catalog service: single access point over the pipeline's JSON products.

Reads (all mtime-cached, see core.cache):
  data/selected_scenes.json  -> windows, dates, tiles
  data/indices/report.json   -> gate status, summaries, label fractions, breaks
  data/indices/seasons_*_stats.json / change_*_stats.json -> cross-window stats
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import config
from ..core.cache import load_json_cached

CONT_PRODUCTS = ("NDTI", "NDCI", "NDSSI", "MNDWI", "CHLA", "SPM", "TURB")
CLASS_PRODUCTS = ("CHLA_CLASS", "TURB_CLASS", "SPM_CLASS", "WQ_FLAG")


def _read(path: Path, default: Any = None) -> Any:
    try:
        return load_json_cached(path)
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def selection() -> dict:
    return _read(config.SELECTED_SCENES)


def report() -> dict:
    return _read(config.REPORT_JSON)


def windows() -> list[dict]:
    """Ordered window descriptors: id, season, date, status, water/invalid %, products."""
    sel = selection().get("windows", {})
    rep_windows = {w["window"]: w for w in report().get("windows", [])}
    out = []
    for wid in sorted(sel):
        s = sel[wid]
        r = rep_windows.get(wid, {})
        summaries = r.get("summaries", {})
        out.append(
            {
                "id": wid,
                "season": config.SEASON_NAMES.get(wid, wid),
                "date": s.get("date"),
                "status": r.get("status"),
                "invalid_pct": r.get("invalid_pct"),
                "cloud_pct": r.get("cloud_pct"),
                "shadow_pct": r.get("shadow_pct"),
                "nodata_pct": r.get("nodata_pct"),
                "summaries": summaries,
                "label_fractions": r.get("label_fractions", {}),
                "products": [p for p in list(CONT_PRODUCTS) + list(CLASS_PRODUCTS)],
            }
        )
    return out


def window_detail(wid: str) -> dict:
    wid = wid.upper()
    for w in windows():
        if w["id"] == wid:
            rep = report()
            detail = dict(w)
            detail["label_breaks"] = rep.get("label_breaks", {})
            detail["calibration"] = rep.get("calibration")
            detail["overlays"] = {
                layer: f"/api/windows/{wid}/overlay/{layer}"
                for layer in config.OVERLAY_LAYERS
            }
            return detail
    raise KeyError(wid)


def seasons_stats() -> dict:
    cands = sorted(config.INDICES_DIR.glob("seasons_*_stats.json"))
    if not cands:
        raise FileNotFoundError("no seasons stats JSON in data/indices")
    return _read(cands[0])


def change_pairs() -> list[str]:
    return sorted(
        p.stem[len("change_"): -len("_stats")]
        for p in config.INDICES_DIR.glob("change_*_stats.json")
    )


def change_stats(pair: str) -> dict:
    path = config.INDICES_DIR / f"change_{pair.upper()}_stats.json"
    return _read(path)


def overlay_path(wid: str, layer: str) -> Path:
    return config.CACHE_DIR / f"{wid.upper()}_{layer.upper()}.png"


def overlay_meta_path(wid: str, layer: str) -> Path:
    return config.CACHE_DIR / f"{wid.upper()}_{layer.upper()}.meta.json"
