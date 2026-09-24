"""Legend single-source-of-truth (replaces hardcoded frontend legends)."""
from fastapi import APIRouter, HTTPException

from ..services.overlays import CLASS_LABELS, CLASS_PALETTE, CONT_SPECS, CONT_UNITS

router = APIRouter()

_CLASS_BREAKS_FALLBACK = {"CHLA_CLASS": [13.0, 14.6, 17.0],
                          "TURB_CLASS": [15.0, 17.2, 20.0],
                          "SPM_CLASS": [19.0, 21.6, 25.3]}


def _rgba(t):
    return f"rgba({t[0]},{t[1]},{t[2]},{t[3] / 255:.2f})"


@router.get("/legend/{layer}")
def legend(layer: str):
    layer = layer.upper()
    if layer in CLASS_LABELS:
        from ..services import catalog

        try:
            breaks = catalog.report().get("label_breaks", {})
        except FileNotFoundError:
            breaks = {}
        key = {"CHLA_CLASS": "CHLA_ugL", "TURB_CLASS": "TURB_FNU",
               "SPM_CLASS": "SPM_mgL"}.get(layer)
        classes = [{"value": i, "label": name,
                    "color": _rgba(CLASS_PALETTE[i]) if i else "transparent"}
                   for i, name in enumerate(CLASS_LABELS[layer])]
        return {"layer": layer, "kind": "class",
                "breaks": breaks if layer == "WQ_FLAG" else
                          breaks.get(key, _CLASS_BREAKS_FALLBACK.get(layer, [])),
                "classes": classes}
    if layer in CONT_SPECS:
        vmin, vmax, lo, hi = CONT_SPECS[layer]
        return {"layer": layer, "kind": "continuous", "unit": CONT_UNITS[layer],
                "vrange": [vmin, vmax],
                "gradient": [_rgba((*lo, 255)), _rgba((*hi, 255))]}
    if layer == "RGB":
        return {"layer": "RGB", "kind": "rgb",
                "note": "Sentinel-2 true color (B04/B03/B02), cloud-excluded stretch"}
    raise HTTPException(404, f"unknown layer {layer}")
