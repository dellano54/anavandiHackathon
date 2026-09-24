from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..core import config
from ..core.cache import file_etag
from ..services import catalog

router = APIRouter()


@router.get("/compare")
def compare_pairs():
    return {"pairs": catalog.change_pairs()}


@router.get("/compare/{pair}")
def compare_pair(pair: str):
    try:
        stats = catalog.change_stats(pair)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown change pair {pair.upper()}")
    pair = pair.upper()
    hot = config.CACHE_DIR / f"change_{pair}_HOTSPOT.png"
    payload = dict(stats)
    payload["hotspot_overlay"] = (
        f"/api/compare/{pair}/hotspot" if hot.exists() else None)
    return payload


@router.get("/compare/{pair}/hotspot")
def compare_hotspot(pair: str):
    path = config.CACHE_DIR / f"change_{pair.upper()}_HOTSPOT.png"
    if not path.exists():
        raise HTTPException(404, "hotspot overlay not built")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": config.IMMUTABLE_CACHE,
                                 "ETag": file_etag(path)})
