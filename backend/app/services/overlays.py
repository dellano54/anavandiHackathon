"""Overlay builder: pre-renders small browser-ready PNGs from the GeoTIFF products.

One build pass (`--build-all`) renders every window x layer into
data/cache/overlays/ so the API serves static files (never renders per request).

Rendering matches visualize.py: RGB basemap at full brightness, heat only on
water (SCL==6, cloud/shadow/nodata excluded), same breaks/colormaps.
Mosaic + stretch helpers are imported from the pipeline script for parity.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine as _Affine
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, transform_bounds
from PIL import Image

from ..core import config

sys.path.insert(0, str(config.PROJECT_ROOT))
import visualize as viz  # noqa: E402  (pipeline helpers: mosaic/common_grid/stretch)

# Discrete class ramp (all class layers): green -> yellow -> orange -> red
CLASS_PALETTE = {
    1: (34, 197, 94, 255),
    2: (234, 179, 8, 255),
    3: (249, 115, 22, 255),
    4: (239, 68, 68, 255),
}

# Continuous layers: (vmin, vmax, lo_rgb, hi_rgb)
CONT_SPECS = {
    "NDTI": (-0.5, 0.5, (255, 247, 237), (234, 88, 12)),
    "NDCI": (-0.5, 0.5, (240, 253, 244), (21, 128, 61)),
    "NDSSI": (-1.0, 1.0, (255, 247, 237), (234, 88, 12)),
    "MNDWI": (-1.0, 1.0, (239, 246, 255), (29, 78, 216)),
    "CHLA": (0.0, 50.0, (240, 253, 244), (21, 128, 61)),
    "SPM": (0.0, 100.0, (255, 247, 237), (234, 88, 12)),
    "TURB": (0.0, 30.0, (255, 247, 237), (234, 88, 12)),
}

CLASS_LABELS = {
    "WQ_FLAG": ["Masked", "Good", "Moderate", "Poor", "Critical"],
    "CHLA_CLASS": ["Masked", "Low", "Moderate", "High", "Bloom"],
    "TURB_CLASS": ["Masked", "Clear", "Slight", "Turbid", "Highly turbid"],
    "SPM_CLASS": ["Masked", "Low", "Moderate", "High", "Very high"],
}
CLASS_UNITS = {"WQ_FLAG": "flag", "CHLA_CLASS": "class", "TURB_CLASS": "class",
               "SPM_CLASS": "class"}
CONT_UNITS = {"NDTI": "index", "NDCI": "index", "NDSSI": "index", "MNDWI": "index",
              "CHLA": "ug/L", "SPM": "mg/L", "TURB": "FNU"}


def _lerp_lut(lo: tuple, hi: tuple, n: int = 256) -> np.ndarray:
    lo_a, hi_a = np.array(lo, np.float32), np.array(hi, np.float32)
    t = np.linspace(0, 1, n, dtype=np.float32)[:, None]
    return (lo_a[None, :] * (1 - t) + hi_a[None, :] * t).astype(np.uint8)


def _read_capped(path: Path, max_dim: int, nearest: bool = False) -> tuple[np.ndarray, dict]:
    rs = Resampling.nearest if nearest else Resampling.bilinear
    with rasterio.open(path) as src:
        h, w = src.height, src.width
        m = max(h, w)
        if m <= max_dim:
            arr = src.read(1)
        else:
            s = int(np.ceil(m / max_dim))
            arr = src.read(1, out_shape=(int(np.ceil(h / s)), int(np.ceil(w / s))),
                           resampling=rs)
        prof = {"crs": str(src.crs), "transform": [src.transform.a, src.transform.b,
                src.transform.c, src.transform.d, src.transform.e, src.transform.f],
                "width": src.width, "height": src.height}
    return arr, prof


def _window_raw(wid: str, date: str, ref_shape: tuple[int, int],
                disp_shape: tuple[int, int]):
    """Mosaic raw bands once; return RGB at disp_shape and SCL water at ref_shape.

    Water = SCL water class minus cloud/shadow/nodata (exact product grid via
    nearest-index sampling, so it aligns pixel-perfect with the products).
    RGB uses cloud-excluded stretch so land keeps satellite brightness.
    """
    from ..services import catalog as _cat  # local import to avoid cycle at module load

    sel = _cat.selection()["windows"][wid]
    item_dirs = {t: config.RAW_DIR / d["item_id"] for t, d in sel["tiles"].items()}
    tile_infos = [json.loads((f / "download_info.json").read_text()) for f in item_dirs.values()]
    (t10, shape10), (t20, shape20) = viz.common_grid(tile_infos)

    def _paths(band):
        return [item_dirs[t] / f"{band}.tif" for t in item_dirs]

    scl20 = viz.mosaic_tiles(_paths("SCL"), t20, shape20, np.uint8)
    scl = viz.upsample_20m_to_10m(scl20, shape10)
    del scl20
    b02 = viz.mosaic_tiles(_paths("B02"), t10, shape10, np.uint16)
    b03 = viz.mosaic_tiles(_paths("B03"), t10, shape10, np.uint16)
    b04 = viz.mosaic_tiles(_paths("B04"), t10, shape10, np.uint16)
    water_full = ((scl == viz.WATER_CLASS)
                  & ~(np.isin(scl, viz.CLOUD_CLASSES) | (scl == viz.SHADOW_CLASS)
                      | (b04 == 0) | (scl == viz.NODATA_CLASS)))
    H, W = shape10
    # Exact product-grid sampling (nearest index) for the water mask
    rh, rw = ref_shape
    ih = np.linspace(0, H - 1, rh).astype(int)
    iw = np.linspace(0, W - 1, rw).astype(int)
    water = water_full[ih][:, iw].copy()
    # Display-size RGB
    oh, ow = disp_shape
    jh = np.linspace(0, H - 1, oh).astype(int)
    jw = np.linspace(0, W - 1, ow).astype(int)
    scld = scl[jh][:, jw]
    excl = (np.isin(scld, viz.CLOUD_CLASSES) | (scld == viz.SHADOW_CLASS)
            | (b04[jh][:, jw] == 0) | (scld == viz.NODATA_CLASS))
    rgb = np.dstack([viz.stretch(b04[jh][:, jw], exclude=excl),
                     viz.stretch(b03[jh][:, jw], exclude=excl),
                     viz.stretch(b02[jh][:, jw], exclude=excl)])
    rgb_u8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    del scl, scld, b02, b03, b04, water_full, rgb, excl
    gc.collect()
    return rgb_u8, water


def _product_path(wid: str, date: str, layer: str) -> Path:
    return config.INDICES_DIR / f"{wid}_{date}_{layer}.tif"


def _paint_class(arr: np.ndarray, water: np.ndarray) -> np.ndarray:
    """RGBA overlay for a discrete class layer (0/masked or non-water -> transparent)."""
    h, w = arr.shape
    out = np.zeros((h, w, 4), np.uint8)
    valid = (arr > 0) & water
    for code, color in CLASS_PALETTE.items():
        m = valid & (arr == code)
        out[m] = color
    return out


def _paint_cont(arr: np.ndarray, water: np.ndarray, layer: str) -> np.ndarray:
    vmin, vmax, lo, hi = CONT_SPECS[layer]
    lut = _lerp_lut(lo, hi)
    h, w = arr.shape
    out = np.zeros((h, w, 4), np.uint8)
    valid = np.isfinite(arr) & water
    t = np.clip((arr[valid].astype(np.float32) - vmin) / max(vmax - vmin, 1e-9), 0, 1)
    out[valid, :3] = lut[(t * 255).astype(np.uint8)]
    out[valid, 3] = 255
    return out


def _composite(rgb_u8: np.ndarray, heat: np.ndarray) -> np.ndarray:
    """RGB land (opaque) + heat on water; heat alpha respected."""
    base = np.dstack([rgb_u8, np.full(rgb_u8.shape[:2], 255, np.uint8)])
    alpha = heat[..., 3:4].astype(np.float32) / 255.0
    comp = (heat[..., :3].astype(np.float32) * alpha
            + base[..., :3].astype(np.float32) * (1 - alpha)).astype(np.uint8)
    return np.dstack([comp, np.full(rgb_u8.shape[:2], 255, np.uint8)])


def build_window(wid: str, max_dim: int | None = None) -> list[str]:
    """Build all overlay PNGs + meta JSONs for one window. Returns built layer names."""
    from ..services import catalog as _cat

    wid = wid.upper()
    max_dim = max_dim or config.OVERLAY_MAX_DIM
    sel = _cat.selection()["windows"][wid]
    date = sel["date"]
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Native product grid first (all official TIFFs share the snapped grid);
    # display shape = native, capped to max_dim by stride.
    with rasterio.open(_product_path(wid, date, "WQ_FLAG")) as src:
        ref_shape = (src.height, src.width)
    s = max(1, int(np.ceil(max(ref_shape) / max_dim)))
    disp_shape = (int(np.ceil(ref_shape[0] / s)), int(np.ceil(ref_shape[1] / s)))

    rgb_u8, water_scl = _window_raw(wid, date, ref_shape, disp_shape)
    # True water = official valid pixels (WQ>0) AND SCL water class, both on the
    # exact product grid. WQ>0 alone includes land (products classify land too).
    wq_path = _product_path(wid, date, "WQ_FLAG")
    if wq_path.exists():
        wq_native, _ = _read_capped(wq_path, 10 ** 9, nearest=True)
        water_native = (wq_native > 0) & water_scl
        del wq_native, water_scl
    else:
        water_native = water_scl
        del water_scl
    gc.collect()
    water = water_native if s == 1 else water_native[::s, ::s].copy()
    del water_native
    gc.collect()
    # Product profile (shared snapped grid) for bounds metadata
    prof: dict | None = None
    for probe in ("NDTI", "WQ_FLAG"):
        p = _product_path(wid, date, probe)
        if p.exists():
            _, prof = _read_capped(p, max_dim)
            break
    built = []
    for layer, kind in config.OVERLAY_LAYERS.items():
        if layer == "RGB":
            rgba = np.dstack([rgb_u8, np.full(rgb_u8.shape[:2], 255, np.uint8)])
            meta_extra: dict = {"kind": "rgb", "unit": "reflectance-stretch"}
        else:
            p = _product_path(wid, date, layer)
            if not p.exists():
                continue
            # Native read + same stride as the water mask => pixel-aligned heat.
            arr_full, _ = _read_capped(p, 10 ** 9, nearest=(kind == "class"))
            arr = arr_full if s == 1 else arr_full[::s, ::s].copy()
            del arr_full
            # Reconcile any residual off-by-one shapes
            mh = min(arr.shape[0], water.shape[0], rgb_u8.shape[0])
            mw = min(arr.shape[1], water.shape[1], rgb_u8.shape[1])
            arr, w = arr[:mh, :mw], water[:mh, :mw]
            rgb_c = rgb_u8[:mh, :mw]
            if kind == "class":
                heat = _paint_class(arr.astype(np.int16), w)
                rep = {}
                try:
                    rep = _cat.report().get("label_breaks", {})
                except FileNotFoundError:
                    pass
                bkey = {"CHLA_CLASS": "CHLA_ugL", "TURB_CLASS": "TURB_FNU",
                        "SPM_CLASS": "SPM_mgL"}.get(layer)
                meta_extra = {"kind": "class", "unit": CLASS_UNITS.get(layer, "class"),
                              "labels": CLASS_LABELS.get(layer, []),
                              "breaks": rep.get(bkey, []) if bkey else rep}
            else:
                vmin, vmax, _lo, _hi = CONT_SPECS[layer]
                heat = _paint_cont(arr.astype(np.float32), w, layer)
                meta_extra = {"kind": "continuous", "unit": CONT_UNITS.get(layer, ""),
                              "vrange": [vmin, vmax]}
            rgba = _composite(rgb_c, heat)
            del arr, heat
        # RGB-only layer uses full-size rgb (no crop needed beyond decimation already applied)
        out = config.CACHE_DIR / f"{wid}_{layer}.png"
        Image.fromarray(rgba).save(out)
        meta = {"window": wid, "date": date, "layer": layer,
                "width": int(rgba.shape[1]), "height": int(rgba.shape[0]),
                **meta_extra}
        if prof is not None:
            t = _Affine(*prof["transform"])
            left, bottom, right, top = array_bounds(prof["height"], prof["width"], t)
            meta["bounds_utm"] = [left, bottom, right, top]
            meta["bounds_lonlat"] = list(transform_bounds(
                prof["crs"], "EPSG:4326", left, bottom, right, top))
        (config.CACHE_DIR / f"{wid}_{layer}.meta.json").write_text(json.dumps(meta, indent=2))
        built.append(layer)
        gc.collect()
    del rgb_u8, water
    gc.collect()
    return built


def build_change(pair: str, max_dim: int | None = None) -> list[str]:
    """Build hotspot overlay for a change pair (e.g. 'AB' -> B-A) if the TIFF exists."""
    max_dim = max_dim or config.OVERLAY_MAX_DIM
    built = []
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for suffix, kind in (("HOTSPOT", "hotspot"), ("WQ_JUMP", "jump")):
        src = None
        for a, b in [(pair[0], pair[1])]:
            cand = config.INDICES_DIR / f"change_{b}-{a}_{suffix}.tif"
            if cand.exists():
                src = cand
        if src is None:
            continue
        arr, _ = _read_capped(src, max_dim, nearest=True)
        h, w = arr.shape
        rgba = np.zeros((h, w, 4), np.uint8)
        if kind == "hotspot":
            m = arr > 0
            rgba[m] = (239, 68, 68, 255)
            meta_extra = {"kind": "hotspot", "unit": "mask"}
        else:
            for v, color in ((-3, (21, 128, 61, 255)), (-2, (74, 222, 128, 255)),
                             (-1, (190, 242, 100, 255)), (0, (254, 240, 138, 200)),
                             (1, (251, 146, 60, 255)), (2, (249, 115, 22, 255)),
                             (3, (239, 68, 68, 255))):
                rgba[arr == v] = color
            meta_extra = {"kind": "class-jump", "unit": "delta-class", "vrange": [-3, 3]}
        out = config.CACHE_DIR / f"change_{pair.upper()}_{suffix}.png"
        Image.fromarray(rgba).save(out)
        (config.CACHE_DIR / f"change_{pair.upper()}_{suffix}.meta.json").write_text(
            json.dumps({"pair": pair.upper(), "layer": suffix,
                        "width": w, "height": h, **meta_extra}, indent=2))
        built.append(suffix)
    return built


def build_all(max_dim: int | None = None) -> dict:
    from ..services import catalog as _cat

    result: dict = {"windows": {}, "changes": {}}
    for wid in sorted(_cat.selection().get("windows", {})):
        try:
            result["windows"][wid] = build_window(wid, max_dim)
        except Exception as e:
            result["windows"][wid] = {"error": str(e)}
    for pair in _cat.change_pairs():
        try:
            result["changes"][pair] = build_change(pair, max_dim)
        except Exception as e:
            result["changes"][pair] = {"error": str(e)}
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-all", action="store_true")
    ap.add_argument("--window", default=None)
    ap.add_argument("--max-dim", type=int, default=None)
    a = ap.parse_args()
    if a.window:
        print(build_window(a.window, a.max_dim))
    else:
        print(json.dumps(build_all(a.max_dim), indent=2))
