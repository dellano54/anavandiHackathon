from fastapi import APIRouter, HTTPException

from ..services import catalog

router = APIRouter()


@router.get("/windows")
def list_windows():
    try:
        return {"windows": catalog.windows()}
    except FileNotFoundError as e:
        raise HTTPException(503, f"pipeline products not found: {e}")


@router.get("/windows/{wid}")
def window_detail(wid: str):
    try:
        return catalog.window_detail(wid)
    except KeyError:
        raise HTTPException(404, f"unknown window {wid.upper()}")
    except FileNotFoundError as e:
        raise HTTPException(503, f"pipeline products not found: {e}")


@router.get("/windows/{wid}/stats")
def window_stats(wid: str):
    """Per-window summaries + label fractions (served from report.json)."""
    try:
        d = catalog.window_detail(wid)
    except KeyError:
        raise HTTPException(404, f"unknown window {wid.upper()}")
    except FileNotFoundError as e:
        raise HTTPException(503, f"pipeline products not found: {e}")
    return {"window": d["id"], "season": d["season"], "date": d["date"],
            "status": d["status"], "invalid_pct": d["invalid_pct"],
            "cloud_pct": d["cloud_pct"], "shadow_pct": d["shadow_pct"],
            "nodata_pct": d["nodata_pct"], "summaries": d["summaries"],
            "label_fractions": d["label_fractions"],
            "label_breaks": d["label_breaks"]}
