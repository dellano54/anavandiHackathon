from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    from ..core import config
    from ..services import catalog

    try:
        n = len(catalog.windows())
        data_ok = True
    except FileNotFoundError:
        n = 0
        data_ok = False
    return {"status": "ok", "data_ok": data_ok, "windows": n,
            "data_dir": str(config.DATA_DIR)}
