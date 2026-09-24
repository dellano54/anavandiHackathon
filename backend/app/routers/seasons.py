from fastapi import APIRouter, HTTPException

from ..services import catalog

router = APIRouter()


@router.get("/seasons")
def seasons():
    """Seasonal story: per-season dominant/fractions + overlay URLs."""
    try:
        stats = catalog.seasons_stats()
    except FileNotFoundError as e:
        raise HTTPException(503, f"seasons products not found: {e}")
    out = []
    for s in stats.get("seasons", []):
        wid = s.get("window")
        out.append({**s, "overlays": {
            "WQ_FLAG": f"/api/windows/{wid}/overlay/WQ_FLAG",
            "CHLA": f"/api/windows/{wid}/overlay/CHLA",
            "RGB": f"/api/windows/{wid}/overlay/RGB",
        }})
    return {"metric": stats.get("metric"), "season_mode": stats.get("season_mode"),
            "label_breaks": stats.get("label_breaks"),
            "calibration_note": stats.get("calibration_note"),
            "seasons": out}
