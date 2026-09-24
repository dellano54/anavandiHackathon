#!/usr/bin/env python3
"""
Vembanad Lake: Sentinel-2 water-quality proxy indices + data-sufficiency diagnostics.

This script is designed to make the quality-control decision visible, especially for
presentation/judging. For EVERY selected window it:
  1. mosaics the downloaded Sentinel-2 bands;
  2. computes the SCL-based invalid mask and exact SCL class distribution;
3. computes diagnostic-only, UNGATED index maps so you can see what the indices
     would look like if the quality gate were ignored;
4. creates a PNG diagnostic figure showing RGB, the SCL validity mask, SCL class
     distribution, and provisional NDTI (turbidity) / NDCI (chlorophyll) /
     NDSSI (suspended sediment) + MNDWI (extra water mask);
  5. applies the data-sufficiency gate;
  6. writes official GeoTIFF indices ONLY for windows that pass the gate.

IMPORTANT:
  The provisional index maps in the diagnostic PNG are for quality-control evidence.
  They are explicitly NOT the official analysis products when a window fails the gate.

Dependencies:
  pip install rasterio numpy matplotlib

Usage:
  python compute_indices.py
  python compute_indices.py --only A
  python compute_indices.py --max-invalid 25
  python compute_indices.py --root /content/project
  python compute_indices.py --chla-breaks 13,14.6,17 --turb-breaks 15,17.2,20 --spm-breaks 19,21.6,25.3

Outputs (official products, written only when the window passes the gate):
  data/indices/<window>_<date>_NDTI.tif    (turbidity index, Lacaux 2007)
  data/indices/<window>_<date>_NDCI.tif    (chlorophyll-a proxy, Mishra 2012)
  data/indices/<window>_<date>_NDSSI.tif   (suspended sediment index, Hossain 2010)
  data/indices/<window>_<date>_MNDWI.tif   (EXTRA water mask, Xu 2006)
  data/indices/<window>_<date>_CHLA.tif    (chlorophyll-a conc., Mishra 2012, ug/L)
  data/indices/<window>_<date>_SPM.tif     (suspended particulate matter, Nechad, mg/L)
  data/indices/<window>_<date>_TURB.tif    (turbidity, Dogliotti blend, FNU)
  data/indices/<window>_<date>_CHLA_CLASS.tif / _TURB_CLASS.tif / _SPM_CLASS.tif
  data/indices/<window>_<date>_WQ_FLAG.tif (overall flag = rounded mean of the 3 classes, uint8)

  data/diagnostics/<window>_<date>_diagnostic.png      (QC: RGB/mask/SCL/indices)
  data/diagnostics/<window>_<date>_concentration.png  (CHLA/SPM/TURB maps)
  data/diagnostics/<window>_<date>_labels.png         (discrete label maps)

  data/diagnostics/<window>_<date>_scl_distribution.json
      -> exact SCL class counts/percentages used for the diagnostic.

  data/indices/report.json
      -> machine-readable pass/fail summary plus diagnostic paths,
         per-window stats summaries and label fractions.

Calibration note: CHLA/SPM/TURB use global literature coefficients
(Mishra 2012 / Nechad 2010-2016 / Dogliotti 2015), NOT locally calibrated
for Vembanad. Values are approximate and intended for relative comparison
across windows A/B/C and hotspot mapping.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import Affine

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


CLOUD_CLASSES = [8, 9, 10]   # medium/high cloud probability + thin cirrus
SHADOW_CLASS = 3
NODATA_CLASS = 0

SCL_LABELS = {
    0: "NoData",
    1: "Saturated/defective",
    2: "Dark features",
    3: "Cloud shadow",
    4: "Vegetation",
    5: "Bare soil",
    6: "Water",
    7: "Unclassified",
    8: "Cloud (medium)",
    9: "Cloud (high)",
    10: "Cirrus",
    11: "Snow/ice",
}

INDEX_SPECS = (
    ("NDTI", "YlOrBr", (-0.5, 0.5)),    # turbidity (Lacaux et al. 2007)
    ("NDCI", "YlGn", (-0.5, 0.5)),      # chlorophyll-a proxy (Mishra & Mishra 2012)
    ("NDSSI", "Oranges", (-1.0, 1.0)),  # suspended sediment (Hossain et al. 2010)
    ("MNDWI", "Blues", (-1.0, 1.0)),    # EXTRA water mask (Xu 2006), not sediment
)

CONC_SPECS = (
    # name, colormap, display range, unit
    ("CHLA", "Greens", (0.0, 50.0), "ug/L"),
    ("SPM", "Oranges", (0.0, 100.0), "mg/L"),
    ("TURB", "YlOrBr", (0.0, 30.0), "FNU"),
)

# Default label breaks, GROUNDED on the premonsoon (window A) water-only
# distribution (quartiles measured 2026-02-11, SCL==6 water pixels):
#   CHLA water p25/p50/p75 = 13.1 / 14.6 / 16.9 ug/L
#   TURB water p25/p50/p75 = 15.2 / 17.2 / 20.1 FNU
#   SPM  water p25/p50/p75 = 19.2 / 21.6 / 25.3 mg/L
# So each parameter shows the full green->red spread on the baseline season,
# and monsoon/postmonsoon shifts read as real movements. The continuous
# GeoTIFFs + stats stay absolute; only the label classes are baseline-relative.
# Tunable via CLI without code edits.
CHLA_BREAKS = (13.0, 14.6, 17.0)   # ug/L -> Low / Moderate / High / Bloom
TURB_BREAKS = (15.0, 17.2, 20.0)   # FNU  -> Clear / Slight / Turbid / Highly turbid
SPM_BREAKS = (19.0, 21.6, 25.3)    # mg/L -> Low / Moderate / High / Very high

# Physical ceilings applied BEFORE classification. The Dogliotti NIR branch can
# blow up near saturation (denominator -> 0); without caps a few percent of
# pixels reach thousands of FNU and force WQ_FLAG=Critical everywhere.
CONC_CAPS = {"CHLA": (0.0, 300.0), "SPM": (0.0, 500.0), "TURB": (0.0, 100.0)}

CHLA_CLASS_NAMES = ("Masked", "Low", "Moderate", "High", "Bloom")
TURB_CLASS_NAMES = ("Masked", "Clear", "Slight", "Turbid", "Highly turbid")
SPM_CLASS_NAMES = ("Masked", "Low", "Moderate", "High", "Very high")
WQ_FLAG_NAMES = ("Masked", "Good", "Moderate", "Poor", "Critical")

# Nechad SPM (single-band Red) coefficients for Sentinel-2 (Nechad et al. 2010/2016).
NECHAD_A_RED = 289.29
NECHAD_C_RED = 0.1686
# Dogliotti 2015 Red saturation switch: use NIR when Red water-leaving reflectance exceeds this.
DOGLIOTTI_RED_SWITCH = 0.07
DOGLIOTTI_A_RED = 228.1
DOGLIOTTI_C_RED = 0.164
DOGLIOTTI_A_NIR = 3078.9
DOGLIOTTI_C_NIR = 0.2112


def log(msg):
    print(msg, flush=True)


def common_grid(tile_infos):
    tb = tile_infos[0]["target_bounds"]
    x0, y0, x1, y1 = tb
    w10 = int(round((x1 - x0) / 10))
    h10 = int(round((y1 - y0) / 10))
    transform10 = Affine(10, 0, x0, 0, -10, y1)
    w20, h20 = w10 // 2, h10 // 2
    transform20 = Affine(20, 0, x0, 0, -20, y1)
    return (transform10, (h10, w10)), (transform20, (h20, w20))


def mosaic_tiles(paths, out_transform, out_shape, dtype, nodata_fill=0):
    """Mosaic AOI-cropped tiles onto the shared target grid using nearest-neighbour."""
    canvas = np.full(out_shape, nodata_fill, dtype=dtype)
    for p in paths:
        with rasterio.open(p) as src:
            src_arr = src.read(1)
            dst = np.full(out_shape, nodata_fill, dtype=dtype)
            reproject(
                source=src_arr,
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=out_transform,
                dst_crs=src.crs,
                resampling=Resampling.nearest,
                src_nodata=nodata_fill,
                dst_nodata=nodata_fill,
            )
            valid = dst != nodata_fill
            canvas[valid] = dst[valid]
    return canvas


def upsample_20m_to_10m(arr20, shape10):
    """Exact 2x nearest upsample for the 20 m -> 10 m aligned grids."""
    h10, w10 = shape10
    out = np.repeat(np.repeat(arr20, 2, axis=0), 2, axis=1)
    return out[:h10, :w10]


def stretch(band, lo=2, hi=98):
    valid = band[band > 0].astype(np.float32)
    if valid.size == 0:
        return np.zeros_like(band, dtype=np.float32)
    p_lo, p_hi = np.percentile(valid, [lo, hi])
    out = np.clip(
        (band.astype(np.float32) - p_lo) / max(p_hi - p_lo, 1e-6), 0, 1
    )
    out[band == 0] = 0
    return out


def to_reflectance(dn):
    """DN -> reflectance using the project's documented Sentinel-2 baseline formula."""
    return np.where(
        dn == 0,
        np.nan,
        (dn.astype(np.float32) - 1000.0) / 10000.0,
    )


def safe_ratio(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / (a + b)
    out[~np.isfinite(out)] = np.nan
    return out


def compute_indices(b02, b03, b04, b05, b08, b11):
    """Compute provisional indices without applying the SCL quality mask.

    Turbidity (NDTI, Lacaux et al. 2007): (Red - Green) / (Red + Green).
    Chlorophyll-a proxy (NDCI, Mishra & Mishra 2012): (RedEdge - Red) / (RedEdge + Red).
    Suspended sediment (NDSSI, Hossain et al. 2010): (Blue - NIR) / (Blue + NIR),
        where -1 = highest SSC and +1 = lowest SSC.
    Extra water mask (MNDWI, Xu 2006): (Green - SWIR1) / (Green + SWIR1).
    """
    r_blue = to_reflectance(b02)
    r_green = to_reflectance(b03)
    r_red = to_reflectance(b04)
    r_rededge = to_reflectance(b05)
    r_nir = to_reflectance(b08)
    r_swir1 = to_reflectance(b11)
    reflectances = {
        "blue": r_blue, "green": r_green, "red": r_red,
        "rededge": r_rededge, "nir": r_nir, "swir1": r_swir1,
    }
    return {
        "NDTI": safe_ratio(r_red, r_green),
        "NDCI": safe_ratio(r_rededge, r_red),
        "NDSSI": safe_ratio(r_blue, r_nir),
        "MNDWI": safe_ratio(r_green, r_swir1),
    }, reflectances


def compute_concentrations(provisional, reflectances):
    """Derive physical concentration maps from indices/reflectances.

    CHLA (Mishra & Mishra 2012, global coastal calibration):
        CHLA = 14.039 + 86.11 * NDCI + 194.325 * NDCI^2  [ug/L], capped to [0, 300].
    SPM (Nechad et al. 2010/2016 single-band Red for Sentinel-2):
        SPM = A * Rw / (1 - Rw / C)  [mg/L] with Rw = R_red, A = 289.29, C = 0.1686.
        Pixels with Rw >= C (saturated) or non-finite input become NaN; capped to [0, 500].
    TURB (Dogliotti et al. 2015 Red-NIR blending concept, simplified):
        T_red = A_red * Rw_red / (1 - Rw_red / C_red),
        T_nir = A_nir * Rw_nir / (1 - Rw_nir / C_nir),
        TURB = T_red where Rw_red <= switch else T_nir  [FNU], capped to [0, 100].
        The cap matters: near saturation the NIR denominator -> 0 and raw values
        reach thousands of FNU, which would force WQ_FLAG=Critical everywhere.
    All outputs are NaN where inputs are non-finite; caller applies the SCL gate.
    """
    ndci = provisional["NDCI"]
    r_red = reflectances["red"]
    r_nir = reflectances["nir"]

    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        chla = 14.039 + 86.11 * ndci + 194.325 * ndci * ndci
        chla[~np.isfinite(ndci)] = np.nan
        chla = np.clip(chla, *CONC_CAPS["CHLA"])

        denom_red = 1.0 - r_red / NECHAD_C_RED
        spm = NECHAD_A_RED * r_red / denom_red
        spm[~np.isfinite(r_red) | (denom_red <= 0) | (r_red < 0)] = np.nan
        spm = np.clip(spm, *CONC_CAPS["SPM"])

        t_red = DOGLIOTTI_A_RED * r_red / (1.0 - r_red / DOGLIOTTI_C_RED)
        t_nir = DOGLIOTTI_A_NIR * r_nir / (1.0 - r_nir / DOGLIOTTI_C_NIR)
        use_nir = np.isfinite(r_red) & (r_red > DOGLIOTTI_RED_SWITCH)
        turb = np.where(use_nir, t_nir, t_red)
        turb[~np.isfinite(turb)] = np.nan
        # Guard saturated denominators explicitly.
        turb[~np.isfinite(r_red) & ~np.isfinite(r_nir)] = np.nan
        turb = np.clip(turb, *CONC_CAPS["TURB"])

    return {"CHLA": chla.astype(np.float32),
            "SPM": spm.astype(np.float32),
            "TURB": turb.astype(np.float32)}


def classify(arr, breaks):
    """Map a continuous concentration array to uint8 classes 1..len(breaks)+1.

    NaN -> 0 (masked). breaks must be ascending, e.g. (5, 15, 40).
    """
    out = np.zeros(arr.shape, dtype=np.uint8)
    valid = np.isfinite(arr)
    # np.digitize returns 0..len(breaks); shift valid pixels to 1..len+1.
    out[valid] = np.digitize(arr[valid], list(breaks), right=False).astype(np.uint8) + 1
    out[~valid] = 0
    return out


def summarize_array(arr):
    """NaN-aware summary over valid (finite) pixels only. JSON-serializable."""
    valid = arr[np.isfinite(arr)]
    n_total = int(arr.size)
    n_valid = int(valid.size)
    if n_valid == 0:
        return {"n_valid": 0, "n_total": n_total, "mean": None, "median": None,
                "std": None, "min": None, "max": None, "p5": None, "p95": None}
    return {
        "n_valid": n_valid,
        "n_total": n_total,
        "mean": round(float(np.mean(valid)), 4),
        "median": round(float(np.median(valid)), 4),
        "std": round(float(np.std(valid)), 4),
        "min": round(float(np.min(valid)), 4),
        "max": round(float(np.max(valid)), 4),
        "p5": round(float(np.percentile(valid, 5)), 4),
        "p95": round(float(np.percentile(valid, 95)), 4),
    }


def label_fractions(cls_arr, names):
    """Fraction (%) of each class over valid (class > 0) pixels + dominant label."""
    valid = cls_arr[cls_arr > 0]
    n_valid = int(valid.size)
    fractions = {}
    for code, name in enumerate(names):
        if code == 0:
            continue
        cnt = int((cls_arr == code).sum())
        fractions[name] = round(100.0 * cnt / n_valid, 2) if n_valid else 0.0
    dominant = max(fractions, key=fractions.get) if fractions and n_valid else None
    return {"n_valid": n_valid, "fractions_pct": fractions, "dominant": dominant}


def build_scl_stats(scl):
    class_ids, class_counts = np.unique(scl, return_counts=True)
    total = int(scl.size)
    invalid_classes = set(CLOUD_CLASSES + [SHADOW_CLASS, NODATA_CLASS])
    rows = []
    for cls, count in zip(class_ids.tolist(), class_counts.tolist()):
        pct = 100.0 * count / total if total else 0.0
        rows.append({
            "class": int(cls),
            "meaning": SCL_LABELS.get(int(cls), "Unknown"),
            "pixels": int(count),
            "percent": round(pct, 4),
            "masked_by_current_gate": int(cls) in invalid_classes,
        })
    return rows


def save_scl_distribution(path, rows, invalid_pct, cloud_pct, shadow_pct, nodata_pct,
                          max_invalid, status):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "max_invalid_pct_threshold": max_invalid,
        "invalid_pct": invalid_pct,
        "cloud_pct": cloud_pct,
        "shadow_pct": shadow_pct,
        "nodata_pct": nodata_pct,
        "current_gate_classes": {
            "cloud": CLOUD_CLASSES,
            "shadow": [SHADOW_CLASS],
            "nodata": [NODATA_CLASS],
        },
        "classes": rows,
    }
    path.write_text(json.dumps(payload, indent=2))


def make_diagnostic_figure(path, label, date, rgb, mask_rgb, scl_rows,
                           invalid_pct, cloud_pct, shadow_pct, nodata_pct,
                           max_invalid, status, provisional):
    """Create the judge-facing QC figure. This is diagnostic evidence, not an official map."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # 8 panels: RGB, SCL mask, SCL distribution, 4 indices, and an explanation panel.
    fig, axes = plt.subplots(1, 8, figsize=(32, 5.5))
    axes = list(axes)

    axes[0].imshow(rgb)
    axes[0].set_title(f"Window {label} — {date}\nRGB (B04/B03/B02)")
    axes[0].axis("off")

    axes[1].imshow(mask_rgb)
    axes[1].set_title(
        f"SCL validity mask\ninvalid={invalid_pct:.1f}%"
        f" (gate={max_invalid:.1f}%)"
    )
    axes[1].axis("off")

    hist_ids = [r["class"] for r in scl_rows]
    hist_counts = [r["pixels"] for r in scl_rows]
    labels = [SCL_LABELS.get(i, str(i)) for i in hist_ids]
    bars = axes[2].bar(range(len(labels)), hist_counts)
    axes[2].set_title("SCL class distribution")
    axes[2].set_ylabel("Pixel count")
    axes[2].set_xticks(range(len(labels)))
    axes[2].set_xticklabels(labels, rotation=65, ha="right", fontsize=7)
    axes[2].grid(axis="y", alpha=0.2)
    for bar, row in zip(bars, scl_rows):
        axes[2].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{row['percent']:.1f}%",
            ha="center",
            va="bottom",
            fontsize=6,
        )

    INDEX_TITLES = {
        "NDTI": "NDTI\nTurbidity",
        "NDCI": "NDCI\nChlorophyll",
        "NDSSI": "NDSSI\nSusp. sediment",
        "MNDWI": "MNDWI\nWater mask (extra)",
    }
    for ax, (name, cmap, vrange) in zip(axes[3:7], INDEX_SPECS):
        arr = provisional[name]
        im = ax.imshow(arr, cmap=cmap, vmin=vrange[0], vmax=vrange[1])
        # Overlay invalid pixels in translucent white so the audience can see where
        # the "would-be" index is contaminated by the quality-control mask.
        invalid_overlay = np.zeros((*arr.shape, 4), dtype=np.float32)
        invalid_overlay[..., 0:3] = 1.0
        invalid_overlay[..., 3] = 0.0
        invalid_overlay[..., 3][~np.isfinite(arr)] = 0.0
        # This overlay is intentionally omitted here because invalid is already baked
        # into the SCL panel; the diagnostic index is the ungated result by design.
        ax.set_title(f"{INDEX_TITLES.get(name, name)}\nDIAGNOSTIC ONLY (ungated)", fontsize=9)
        ax.axis("off")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    axes[7].axis("off")
    verdict = "PASS — official index GeoTIFFs written" if status == "OK" else "INSUFFICIENT DATA — official index GeoTIFFs NOT written"
    body = (
        f"{verdict}\n\n"
        f"Current SCL gate:\n"
        f"  invalid = cloud + shadow + nodata\n"
        f"  threshold = {max_invalid:.1f}%\n\n"
        f"Observed:\n"
        f"  cloud = {cloud_pct:.1f}%\n"
        f"  shadow = {shadow_pct:.1f}%\n"
        f"  nodata = {nodata_pct:.1f}%\n"
        f"  total invalid = {invalid_pct:.1f}%\n\n"
        f"The four index maps are intentionally\n"
        f"UN-GATED diagnostic maps. They show\n"
        f"what the indices would look like if the\n"
        f"quality gate were ignored."
    )
    axes[7].text(
        0.03, 0.97, body, va="top", ha="left", fontsize=10,
        transform=axes[7].transAxes,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="white", alpha=0.9, edgecolor="black"),
    )

    fig.suptitle(
        f"Sentinel-2 data-quality diagnostic — Window {label} ({date})",
        fontsize=15,
        fontweight="bold",
        y=1.02,
    )
    fig.text(
        0.5, 0.005,
        "Judge-facing QC evidence: diagnostic index maps are not official analysis products unless the gate passes.",
        ha="center",
        fontsize=9,
    )
    plt.tight_layout(rect=[0, 0.03, 1, 0.98])
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def make_concentration_figure(path, label, date, concentrations, status):
    """4-panel concentration figure: CHLA / SPM / TURB + note. Diagnostic (ungated)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 4, figsize=(20, 5.0))
    axes = list(axes)
    titles = {"CHLA": "CHLA\nChlorophyll-a (ug/L)",
              "SPM": "SPM\nSediment (mg/L)",
              "TURB": "TURB\nTurbidity (FNU)"}
    for ax, (name, cmap, vrange, _unit) in zip(axes[:3], CONC_SPECS):
        arr = concentrations[name]
        disp = np.where(np.isfinite(arr), arr, np.nan)
        im = ax.imshow(disp, cmap=cmap, vmin=vrange[0], vmax=vrange[1])
        ax.set_title(f"{titles.get(name, name)}\nDIAGNOSTIC ONLY (ungated)", fontsize=9)
        ax.axis("off")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    axes[3].axis("off")
    verdict = "PASS" if status == "OK" else "INSUFFICIENT DATA"
    axes[3].text(
        0.03, 0.97,
        f"{verdict}\n\nGlobal calibration:\n"
        f"  CHLA: Mishra 2012\n  SPM: Nechad Red\n  TURB: Dogliotti blend\n\n"
        f"NOT locally validated\nfor Vembanad.\nUse for relative\nA/B/C comparison.",
        va="top", ha="left", fontsize=10, transform=axes[3].transAxes,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="white", alpha=0.9, edgecolor="black"),
    )
    fig.suptitle(f"Concentration proxies — Window {label} ({date})",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout(rect=[0, 0.03, 1, 0.98])
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def make_label_figure(path, label, date, classes, fractions_all, status):
    """4-panel discrete label figure: CHLA_CLASS / TURB_CLASS / SPM_CLASS / WQ_FLAG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    from matplotlib.colors import ListedColormap, BoundaryNorm
    fig, axes = plt.subplots(1, 4, figsize=(20, 5.0))
    axes = list(axes)
    panels = (
        ("CHLA_CLASS", CHLA_CLASS_NAMES, "Greens"),
        ("TURB_CLASS", TURB_CLASS_NAMES, "YlOrBr"),
        ("SPM_CLASS", SPM_CLASS_NAMES, "Oranges"),
        ("WQ_FLAG", WQ_FLAG_NAMES, "RdYlGn_r"),
    )
    for ax, (key, names, _cmap) in zip(axes, panels):
        arr = classes[key]
        cmap = ListedColormap([plt.get_cmap("Greys")(0.15),
                               plt.get_cmap("Greens")(0.35),
                               plt.get_cmap("YlOrBr")(0.45),
                               plt.get_cmap("Oranges")(0.65),
                               plt.get_cmap("Reds")(0.8)])
        norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5], cmap.N)
        im = ax.imshow(arr, cmap=cmap, norm=norm)
        frac = fractions_all.get(key, {}).get("fractions_pct", {})
        dom = fractions_all.get(key, {}).get("dominant")
        extra = "; ".join(f"{k} {v:.1f}%" for k, v in frac.items()) if frac else "no valid pixels"
        ax.set_title(f"{key}\ndom: {dom or 'n/a'}\n{extra}", fontsize=7)
        ax.axis("off")
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, ticks=[0, 1, 2, 3, 4])
        cbar.ax.set_yticklabels(names, fontsize=7)
    fig.suptitle(f"Water-quality labels — Window {label} ({date}) [{status}]",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout(rect=[0, 0.03, 1, 0.98])
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_class_indices(out_dir, label, date, classes, shape10, t10, crs):
    """Write uint8 label GeoTIFFs (0 = masked/invalid, 1..4 = classes)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, arr in classes.items():
        out_path = out_dir / f"{label}_{date}_{name}.tif"
        prof = dict(
            driver="GTiff", dtype="uint8", count=1,
            width=shape10[1], height=shape10[0],
            crs=crs or "EPSG:32643", transform=t10, nodata=0,
            compress="deflate", tiled=True, blockxsize=512, blockysize=512,
        )
        with rasterio.open(out_path, "w", **prof) as dst:
            dst.write(arr.astype(np.uint8), 1)
        written[name] = str(out_path)
    return written


def write_official_indices(out_dir, label, date, arrays, invalid, shape10, t10, crs):
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, arr in arrays.items():
        official = arr.copy()
        official[invalid] = np.nan
        out_path = out_dir / f"{label}_{date}_{name}.tif"
        prof = dict(
            driver="GTiff",
            dtype="float32",
            count=1,
            width=shape10[1],
            height=shape10[0],
            crs=crs or "EPSG:32643",
            transform=t10,
            nodata=np.nan,
            compress="deflate",
            predictor=3,
            tiled=True,
            blockxsize=512,
            blockysize=512,
        )
        with rasterio.open(out_path, "w", **prof) as dst:
            dst.write(official.astype(np.float32), 1)
        written[name] = str(out_path)
    return written


def parse_breaks(text, default, name):
    try:
        parts = [float(x.strip()) for x in text.split(",")]
        if len(parts) != 3 or not (parts[0] < parts[1] < parts[2]):
            raise ValueError
        return tuple(parts)
    except Exception:
        sys.exit(f"bad --{name} '{text}' (expected e.g. 5,15,40 with ascending values)")
    return default


def process_window(label, sel, raw_dir, out_dir, diagnostics_dir, max_invalid,
                   chla_breaks=CHLA_BREAKS, turb_breaks=TURB_BREAKS, spm_breaks=SPM_BREAKS):
    tiles = sel["tiles"]
    item_ids = {t: raw_dir / d["item_id"] for t, d in tiles.items()}
    date = sel["date"]

    tile_infos = []
    for tile, folder in item_ids.items():
        info_path = folder / "download_info.json"
        if not info_path.exists():
            return {
                "window": label,
                "date": date,
                "status": "INSUFFICIENT",
                "reason": "missing downloaded files",
                "invalid_pct": None,
                "diagnostic_figure": None,
            }
        tile_infos.append(json.load(open(info_path)))

    (t10, shape10), (t20, shape20) = common_grid(tile_infos)

    def paths_for(band):
        return [item_ids[tile] / f"{band}.tif" for tile in item_ids]

    required = ("B02", "B03", "B04", "B05", "B08", "B11", "SCL")
    for band in required:
        for p in paths_for(band):
            if not p.exists():
                return {
                    "window": label,
                    "date": date,
                    "status": "INSUFFICIENT",
                    "reason": f"missing band file {p}",
                    "invalid_pct": None,
                    "diagnostic_figure": None,
                }

    # --- Mosaic source data (10 m bands stay native; 20 m bands upsampled x2) ---
    b02 = mosaic_tiles(paths_for("B02"), t10, shape10, np.uint16, 0)
    b03 = mosaic_tiles(paths_for("B03"), t10, shape10, np.uint16, 0)
    b04 = mosaic_tiles(paths_for("B04"), t10, shape10, np.uint16, 0)
    b08 = mosaic_tiles(paths_for("B08"), t10, shape10, np.uint16, 0)
    b05_20 = mosaic_tiles(paths_for("B05"), t20, shape20, np.uint16, 0)
    b11_20 = mosaic_tiles(paths_for("B11"), t20, shape20, np.uint16, 0)
    scl20 = mosaic_tiles(paths_for("SCL"), t20, shape20, np.uint8, 0)

    b05 = upsample_20m_to_10m(b05_20, shape10)
    b11 = upsample_20m_to_10m(b11_20, shape10)
    scl = upsample_20m_to_10m(scl20, shape10)

    # --- SCL quality-control mask ---
    nodata_mask = (b03 == 0) | (b04 == 0) | (scl == NODATA_CLASS)
    cloud_mask = np.isin(scl, CLOUD_CLASSES)
    shadow_mask = scl == SHADOW_CLASS
    invalid = nodata_mask | cloud_mask | shadow_mask

    invalid_pct = round(100.0 * float(invalid.mean()), 1)
    cloud_pct = round(100.0 * float(cloud_mask.mean()), 1)
    shadow_pct = round(100.0 * float(shadow_mask.mean()), 1)
    nodata_pct = round(100.0 * float(nodata_mask.mean()), 1)

    # --- Exact SCL distribution for evidence ---
    scl_rows = build_scl_stats(scl)

    # --- Diagnostic RGB and binary validity mask ---
    rgb = np.dstack([stretch(b04), stretch(b03), stretch(b02)])
    mask_rgb = np.empty((*shape10, 3), dtype=np.float32)
    mask_rgb[:] = [0.85, 0.85, 0.85]       # valid = light grey
    mask_rgb[cloud_mask] = [1.0, 1.0, 1.0] # cloud = white
    mask_rgb[shadow_mask] = [0.2, 0.2, 0.2]# shadow = dark grey
    mask_rgb[nodata_mask] = [1.0, 0.0, 1.0]# nodata = magenta

    # --- Provisional diagnostic indices + concentrations are ALWAYS computed ---
    # These are intentionally ungated. They never become official GeoTIFF products
    # for an insufficient window.
    provisional, reflectances = compute_indices(b02, b03, b04, b05, b08, b11)
    concentrations = compute_concentrations(provisional, reflectances)

    # --- Labels (per-pixel classes 0..4) on the ungated arrays ---
    # WQ_FLAG is the rounded MEAN of the three classes (not the max): one spiky
    # parameter alone must not condemn a pixel, and the mean keeps the full
    # green->red spread instead of flooding red.
    chla_class = classify(concentrations["CHLA"], chla_breaks)
    turb_class = classify(concentrations["TURB"], turb_breaks)
    spm_class = classify(concentrations["SPM"], spm_breaks)
    stacked = np.stack([chla_class, turb_class, spm_class]).astype(np.float32)
    n_valid = (stacked > 0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        wq_mean = np.where(n_valid > 0, stacked.sum(axis=0) / np.maximum(n_valid, 1), 0.0)
    wq_flag = np.clip(np.floor(wq_mean + 0.5), 1, 4).astype(np.uint8)
    wq_flag[n_valid == 0] = 0
    del stacked, n_valid, wq_mean
    # SCL-invalid pixels are never valid labels, even in diagnostics.
    chla_class[invalid] = 0
    turb_class[invalid] = 0
    spm_class[invalid] = 0
    wq_flag[invalid] = 0
    classes = {"CHLA_CLASS": chla_class, "TURB_CLASS": turb_class,
               "SPM_CLASS": spm_class, "WQ_FLAG": wq_flag}

    # --- Summaries + label fractions (valid pixels only) ---
    summaries = {k: summarize_array(v) for k, v in {**provisional, **concentrations}.items()}
    fractions_all = {
        "CHLA_CLASS": {**label_fractions(chla_class, CHLA_CLASS_NAMES), "breaks": list(chla_breaks)},
        "TURB_CLASS": {**label_fractions(turb_class, TURB_CLASS_NAMES), "breaks": list(turb_breaks)},
        "SPM_CLASS": {**label_fractions(spm_class, SPM_CLASS_NAMES), "breaks": list(spm_breaks)},
        "WQ_FLAG": label_fractions(wq_flag, WQ_FLAG_NAMES),
    }

    status = "OK" if invalid_pct <= max_invalid else "INSUFFICIENT"

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_path = diagnostics_dir / f"{label}_{date}_diagnostic.png"
    concentration_path = diagnostics_dir / f"{label}_{date}_concentration.png"
    labels_path = diagnostics_dir / f"{label}_{date}_labels.png"
    scl_json_path = diagnostics_dir / f"{label}_{date}_scl_distribution.json"

    save_scl_distribution(
        scl_json_path,
        scl_rows,
        invalid_pct,
        cloud_pct,
        shadow_pct,
        nodata_pct,
        max_invalid,
        status,
    )
    make_diagnostic_figure(
        diagnostic_path,
        label,
        date,
        rgb,
        mask_rgb,
        scl_rows,
        invalid_pct,
        cloud_pct,
        shadow_pct,
        nodata_pct,
        max_invalid,
        status,
        provisional,
    )
    make_concentration_figure(concentration_path, label, date, concentrations, status)
    make_label_figure(labels_path, label, date, classes, fractions_all, status)

    log(
        f"  [{label}] {date} | invalid={invalid_pct:.1f}% "
        f"(cloud={cloud_pct:.1f}% shadow={shadow_pct:.1f}% nodata={nodata_pct:.1f}%) "
        f"| status={status}"
    )
    log(f"  [{label}] diagnostic: {diagnostic_path}")
    log(f"  [{label}] concentration: {concentration_path}")
    log(f"  [{label}] labels: {labels_path}")
    log(f"  [{label}] SCL distribution: {scl_json_path}")
    for key in ("NDTI", "NDCI", "NDSSI", "MNDWI", "CHLA", "SPM", "TURB"):
        s = summaries.get(key, {})
        log(f"    {key:<5} n_valid={s.get('n_valid')} mean={s.get('mean')} "
            f"median={s.get('median')} p5={s.get('p5')} p95={s.get('p95')}")
    for key in ("CHLA_CLASS", "TURB_CLASS", "SPM_CLASS", "WQ_FLAG"):
        f = fractions_all.get(key, {})
        log(f"    {key:<10} dominant={f.get('dominant')} fractions={f.get('fractions_pct')}")

    if status == "INSUFFICIENT":
        log(
            f"  [{label}] INSUFFICIENT DATA: {invalid_pct:.1f}% invalid "
            f"> {max_invalid:.1f}% threshold. Diagnostic maps were generated, "
            f"but official GeoTIFFs are NOT written."
        )
        return {
            "window": label,
            "date": date,
            "status": status,
            "reason": (
                f"{invalid_pct}% cloud+shadow+nodata exceeds "
                f"{max_invalid}% threshold"
            ),
            "invalid_pct": invalid_pct,
            "cloud_pct": cloud_pct,
            "shadow_pct": shadow_pct,
            "nodata_pct": nodata_pct,
            "diagnostic_figure": str(diagnostic_path),
            "concentration_figure": str(concentration_path),
            "labels_figure": str(labels_path),
            "scl_distribution": str(scl_json_path),
            "summaries": summaries,
            "label_fractions": fractions_all,
            "official_outputs": {},
        }

    written = write_official_indices(
        out_dir,
        label,
        date,
        {**provisional, **concentrations},
        invalid,
        shape10,
        t10,
        tile_infos[0].get("crs", "EPSG:32643"),
    )
    written_classes = write_class_indices(
        out_dir, label, date, classes, shape10, t10,
        tile_infos[0].get("crs", "EPSG:32643"),
    )
    written.update(written_classes)
    log(f"  [{label}] official products written: {len(written)} files")

    return {
        "window": label,
        "date": date,
        "status": status,
        "invalid_pct": invalid_pct,
        "cloud_pct": cloud_pct,
        "shadow_pct": shadow_pct,
        "nodata_pct": nodata_pct,
        "diagnostic_figure": str(diagnostic_path),
        "concentration_figure": str(concentration_path),
        "labels_figure": str(labels_path),
        "scl_distribution": str(scl_json_path),
        "summaries": summaries,
        "label_fractions": fractions_all,
        "official_outputs": written,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--root",
        default=".",
        help="project root containing data/ (default: cwd)",
    )
    ap.add_argument(
        "--windows-file",
        default=None,
        help="path to selected_scenes.json (default: data/selected_scenes.json)",
    )
    ap.add_argument(
        "--only",
        default=None,
        help="windows to process, e.g. A or AC (default: all)",
    )
    ap.add_argument(
        "--max-invalid",
        type=float,
        default=30.0,
        help="max %% cloud+shadow+nodata allowed before a window is flagged "
             "INSUFFICIENT and official indices are skipped (default: 30)",
    )
    ap.add_argument(
        "--chla-breaks", default=",".join(map(str, CHLA_BREAKS)),
        help="CHLA class breaks in ug/L, ascending (default: 13,14.6,17)",
    )
    ap.add_argument(
        "--turb-breaks", default=",".join(map(str, TURB_BREAKS)),
        help="TURB class breaks in FNU, ascending (default: 15,17.2,20)",
    )
    ap.add_argument(
        "--spm-breaks", default=",".join(map(str, SPM_BREAKS)),
        help="SPM class breaks in mg/L, ascending (default: 19,21.6,25.3)",
    )
    args = ap.parse_args()
    chla_breaks = parse_breaks(args.chla_breaks, CHLA_BREAKS, "chla-breaks")
    turb_breaks = parse_breaks(args.turb_breaks, TURB_BREAKS, "turb-breaks")
    spm_breaks = parse_breaks(args.spm_breaks, SPM_BREAKS, "spm-breaks")

    root = Path(args.root).resolve()
    data = root / "data"
    raw = data / "raw"
    out_dir = data / "indices"
    diagnostics_dir = data / "diagnostics"
    sel_path = Path(args.windows_file) if args.windows_file else data / "selected_scenes.json"

    if not sel_path.exists():
        sys.exit(f"{sel_path} not found. Run download.py first.")

    sel_doc = json.load(open(sel_path))
    selection = sel_doc.get("windows", {})
    labels = [l for l in selection if args.only is None or l in args.only.upper()]
    if not labels:
        sys.exit("No matching windows in selection file.")

    log(
        f"Windows to evaluate: {labels} | max-invalid gate: {args.max_invalid}%\n"
        "Every window will also receive a judge-facing diagnostic PNG."
    )

    results = []
    for label in sorted(labels):
        results.append(
            process_window(
                label,
                selection[label],
                raw,
                out_dir,
                diagnostics_dir,
                args.max_invalid,
                chla_breaks,
                turb_breaks,
                spm_breaks,
            )
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "max_invalid_pct_threshold": args.max_invalid,
        "label_breaks": {"CHLA_ugL": list(chla_breaks),
                         "TURB_FNU": list(turb_breaks),
                         "SPM_mgL": list(spm_breaks)},
        "concentration_caps": {k: list(v) for k, v in CONC_CAPS.items()},
        "calibration": ("CHLA: Mishra & Mishra 2012 global; SPM: Nechad Red; "
                        "TURB: Dogliotti Red-NIR blend (capped at 100 FNU against "
                        "NIR saturation blowup). Label breaks = premonsoon (A) "
                        "water-only quartiles; WQ_FLAG = rounded mean of the 3 "
                        "classes. NOT locally validated "
                        "for Vembanad; use for relative A/B/C comparison."),
        "diagnostics_always_generated": True,
        "diagnostic_note": (
            "Diagnostic maps (indices, concentrations, labels) are ungated and are "
            "for data-quality illustration. Only windows with status OK receive "
            "official GeoTIFFs (indices + concentrations + label classes)."
        ),
        "windows": results,
    }
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2))

    log("\n=== SUMMARY ===")
    log(f"{'win':<4}{'date':<12}{'status':<16}{'invalid%':>10}{'cloud%':>9}{'shadow%':>9}")
    for r in results:
        inv = "n/a" if r["invalid_pct"] is None else f"{r['invalid_pct']:.1f}"
        cl = "n/a" if r.get("cloud_pct") is None else f"{r['cloud_pct']:.1f}"
        sh = "n/a" if r.get("shadow_pct") is None else f"{r['shadow_pct']:.1f}"
        log(
            f"{r['window']:<4}{r['date']:<12}{r['status']:<16}"
            f"{inv:>10}{cl:>9}{sh:>9}"
        )

    n_ok = sum(r["status"] == "OK" for r in results)
    n_bad = sum(r["status"] == "INSUFFICIENT" for r in results)
    log(
        f"\n{n_ok} window(s) OK (official indices written), "
        f"{n_bad} window(s) INSUFFICIENT DATA (diagnostics written, official indices withheld)."
    )
    log(f"Report: {report_path}")

    # Preserve the old useful CI/automation behavior: non-zero if every selected
    # window failed, but do not fail when at least one window is usable.
    sys.exit(1 if n_bad and not n_ok else 0)


if __name__ == "__main__":
    main()
