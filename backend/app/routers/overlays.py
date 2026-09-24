from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..core import config
from ..core.cache import file_etag, load_json_cached
from ..services import catalog

router = APIRouter()


def _overlay_file(wid: str, layer: str):
    wid, layer = wid.upper(), layer.upper()
    if layer not in config.OVERLAY_LAYERS and not (
            layer in ("HOTSPOT", "WQ_JUMP") or layer.startswith("change_")):
        raise HTTPException(404, f"unknown layer {layer}")
    path = catalog.overlay_path(wid, layer)
    if not path.exists():
        raise HTTPException(
            404, f"overlay {wid}/{layer} not built yet "
                 f"(run: python -m app.services.overlays --build-all from backend/)")
    return path


@router.get("/windows/{wid}/overlay/{layer}")
def overlay_png(wid: str, layer: str):
    path = _overlay_file(wid, layer)
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": config.IMMUTABLE_CACHE,
                                 "ETag": file_etag(path)})


@router.get("/windows/{wid}/overlay/{layer}/meta")
def overlay_meta(wid: str, layer: str):
    _overlay_file(wid, layer)  # 404 if missing
    meta_path = catalog.overlay_meta_path(wid.upper(), layer.upper())
    if not meta_path.exists():
        raise HTTPException(404, "meta not found")
    return load_json_cached(meta_path)
