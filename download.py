#!/usr/bin/env python3
"""
Vembanad Lake: self-contained Sentinel-2 L2A AOI-only fetcher (Planetary Computer).

One file, no project imports. Dependencies: rasterio, numpy, requests
    pip install rasterio numpy requests

What it does
  1. Reads the AOI bbox from data/aoi/vembanad_aoi.geojson (falls back to the built-in bbox).
  2. For each hydrological window (A/B/C) searches the STAC API, then for the best
     candidate dates measures, cheaply (decimated overview reads):
        - swath coverage of the AOI (union of all tiles)
        - estimated AOI cloud / shadow fraction from SCL
     and picks the least-cloudy date whose swath fully covers the AOI.
3. Downloads ONLY the AOI pixels of B02 B03 B04 B05 B08 B11 SCL (raw DN, untouched)
      into data/raw/<item_id>/<BAND>.tif. Full tiles are never downloaded.
      Band -> index mapping (computed later in indexGen.py):
        B04+B03 -> NDTI turbidity, B05+B04 -> NDCI chlorophyll,
        B02+B08 -> NDSSI suspended sediment, B03+B11 -> MNDWI water mask (extra),
        B04/B03/B02 -> RGB, SCL -> validity mask.
      Derived in indexGen.py (no extra download needed):
        NDCI -> CHLA ug/L (Mishra 2012), B04 -> SPM mg/L (Nechad),
        B04+B08 -> TURB FNU (Dogliotti), then CHLA/TURB/SPM -> label classes.
  4. Writes data/selected_scenes.json and data/raw/<item_id>/download_info.json.

Usage (from the project root)
  python 02_download_bands.py --select-only          # pick scenes, print table, no download
  python 02_download_bands.py                         # pick + download everything
  python 02_download_bands.py --only A                # one window
  python 02_download_bands.py --pick A=2026-03-10     # force a date for a window
  python 02_download_bands.py --window B=2026-07-01:2026-09-15   # change a window's dates
  python 02_download_bands.py --reselect              # ignore saved selection and search again

Safe to re-run: finished files are verified and skipped, writes are atomic (.tmp + rename).
No DN -> reflectance conversion happens here; that belongs in the processing step:
    reflectance = (DN - 1000) / 10000  (baseline >= 04.00), DN == 0 is nodata.
"""
import os

# Must be set before rasterio opens anything. setdefault lets you override from the shell.
for _k, _v in {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MERGE_CONSECUTIVE_REQUESTS": "YES",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_INGESTED_BYTES_AT_OPEN": "32768",
    "GDAL_HTTP_TIMEOUT": "90",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
    "GDAL_CACHEMAX": "512",
}.items():
    os.environ.setdefault(_k, _v)

import argparse
import json
import math
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

# ----------------------------------------------------------------------------- config
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
COLLECTION = "sentinel-2-l2a"
CRS = "EPSG:32643"                       # UTM 43N
DEFAULT_BBOX = (76.22, 9.45, 76.55, 10.05)   # lon_min, lat_min, lon_max, lat_max

# Hydrological windows (edit here or use --window). These match the plan.
WINDOWS = {
    "A": ("2026-01-15", "2026-03-15"),   # pre-monsoon / dry, saline intrusion high
    "B": ("2025-07-01", "2025-09-15"),   # monsoon, peak sediment influx
    "C": ("2025-10-15", "2025-12-15"),   # post-monsoon settling
}

# 10 m bands first (slowest), then 20 m
BANDS = ["B02", "B03", "B04", "B08", "B05", "B11", "SCL"]
DTYPES = {"B02": "uint16", "B03": "uint16", "B04": "uint16", "B05": "uint16",
          "B08": "uint16", "B11": "uint16", "SCL": "uint8"}
CLOUD_CLASSES = [8, 9, 10]   # SCL: cloud medium/high, thin cirrus
SHADOW_CLASS = 3
WATER_CLASS = 6
PROBE_CELL = 100             # metres, cell size for the cheap coverage/cloud probe

TRANSIENT = (RasterioIOError, OSError, TimeoutError, requests.RequestException)
_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


# ----------------------------------------------------------------------------- geometry
def bbox_from_geojson(path):
    gj = json.load(open(path))
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for s in c:
                walk(s)

    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    for f in feats:
        walk(f.get("geometry", f)["coordinates"])
    return (min(xs), min(ys), max(xs), max(ys))


def snapped_bounds(bbox):
    """AOI bbox -> UTM 43N bounds snapped OUTWARD to multiples of 20 m,
    so 10 m and 20 m pixels align exactly for every band and every tile."""
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", CRS, *bbox, densify_pts=21)
    lo = lambda v: int(math.floor(v / 20.0) * 20)
    hi = lambda v: int(math.ceil(v / 20.0) * 20)
    return (lo(x0), lo(y0), hi(x1), hi(y1))


def intersect(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return (x0, y0, x1, y1) if (x1 > x0 and y1 > y0) else None


def int_window(src, bounds):
    """Window for `bounds`; must land exactly on pixel edges (no silent rounding)."""
    w = from_bounds(*bounds, transform=src.transform)
    vals = (w.col_off, w.row_off, w.width, w.height)
    if any(abs(v - round(v)) > 1e-6 for v in vals):
        raise ValueError(f"window not pixel-aligned: {vals} for bounds {bounds}")
    return Window(*[int(round(v)) for v in vals])


def same_transform(a, b):
    return all(abs(x - y) < 1e-6 for x, y in zip(tuple(a)[:6], tuple(b)[:6]))


# ----------------------------------------------------------------------------- signing
class Signer:
    """Planetary Computer SAS token (replaces the `planetary_computer` package).
    Anonymous tokens work but are rate limited; that is fine for a handful of files."""

    def __init__(self):
        self.lock = threading.Lock()
        self.token = None
        self.expiry = 0.0

    def invalidate(self):
        with self.lock:
            self.token = None

    def _refresh(self):
        r = requests.get(SAS_URL, timeout=30)
        r.raise_for_status()
        j = r.json()
        self.token = j["token"]
        try:
            self.expiry = datetime.fromisoformat(
                j["msft:expiry"].replace("Z", "+00:00")).timestamp()
        except Exception:
            self.expiry = time.time() + 1800

    def sign(self, href):
        if not href.startswith("http") or ("?" in href and "sig=" in href):
            return href                      # local path (tests) or already signed
        with self.lock:
            if self.token is None or time.time() > self.expiry - 300:
                self._refresh()
            return f"{href}?{self.token}"


def retry(fn, retries, label, signer=None):
    """Retry only transient network/IO errors. Logic errors propagate immediately."""
    for k in range(1, retries + 1):
        try:
            return fn()
        except TRANSIENT as e:
            log(f"  {label} retry {k}/{retries}: {type(e).__name__}: {e}")
            if signer:
                signer.invalidate()          # force a fresh token on the next attempt
            if k == retries:
                raise
            time.sleep(2 ** k)


# ----------------------------------------------------------------------------- STAC
def stac_search(bbox, start, end, max_cloud):
    body = {"collections": [COLLECTION], "bbox": list(bbox),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": max_cloud}}, "limit": 500}

    def go():
        r = requests.post(STAC_URL, json=body, timeout=120)
        r.raise_for_status()
        return r.json().get("features", [])

    feats = retry(go, 3, "STAC search")
    if len(feats) >= 500:
        log("  WARNING: 500 results returned; narrow the window or lower --max-cloud")
    items = []
    for f in feats:
        a = f["assets"]
        if not all(b in a for b in BANDS):
            continue
        m = re.search(r"_T(\d{2}[A-Z]{3})_", f["id"])
        tile = f["properties"].get("s2:mgrs_tile") or (m.group(1) if m else None)
        if tile is None:
            continue
        items.append({"id": f["id"], "date": f["properties"]["datetime"][:10],
                      "tile": tile, "cloud": f["properties"].get("eo:cloud_cover"),
                      "assets": {b: a[b]["href"] for b in BANDS}})
    return items


def required_tiles(items, target, signer, retries):
    """Tiles that actually intersect the target extent (one cheap header read per tile)."""
    first = {}
    for it in items:
        first.setdefault(it["tile"], it)
    req = []
    for tile, it in sorted(first.items()):
        def go():
            with rasterio.open(signer.sign(it["assets"]["B04"])) as s:
                return intersect(target, tuple(s.bounds))
        if retry(go, retries, f"overlap {tile}", signer):
            req.append(tile)
    return req


# ----------------------------------------------------------------------------- probe
def probe(tiles, target, signer, cell=PROBE_CELL):
    """Decimated reads (use the COG overviews, a few MB total) to estimate, over the
    whole AOI: swath coverage and cloud/shadow/water fractions. `tiles` = {tile: item}."""
    xmin, ymin, xmax, ymax = target
    gh = int(math.ceil((ymax - ymin) / cell))
    gw = int(math.ceil((xmax - xmin) / cell))
    covered = np.zeros((gh, gw), bool)
    scl_grid = np.zeros((gh, gw), np.uint8)

    for tile, it in tiles.items():
        with rasterio.open(signer.sign(it["assets"]["B04"])) as s4, \
                rasterio.open(signer.sign(it["assets"]["SCL"])) as ss:
            inter = intersect(target, tuple(s4.bounds))
            if inter is None:
                continue
            nh = max(1, int(round((inter[3] - inter[1]) / cell)))
            nw = max(1, int(round((inter[2] - inter[0]) / cell)))
            a = s4.read(1, window=from_bounds(*inter, transform=s4.transform),
                        out_shape=(nh, nw))
            s = ss.read(1, window=from_bounds(*inter, transform=ss.transform),
                        out_shape=(nh, nw))
        r0 = int(round((ymax - inter[3]) / cell))
        c0 = int(round((inter[0] - xmin) / cell))
        r1, c1 = min(gh, r0 + nh), min(gw, c0 + nw)
        rr, cc = r1 - r0, c1 - c0
        if rr <= 0 or cc <= 0:
            continue
        valid = a[:rr, :cc] != 0
        covered[r0:r1, c0:c1] |= valid
        sub = scl_grid[r0:r1, c0:c1]          # view
        sub[valid] = s[:rr, :cc][valid]

    n = max(int(covered.sum()), 1)
    vals = scl_grid[covered]
    return {"coverage_pct": round(100 * float(covered.mean()), 1),
            "cloud_pct": round(100 * float(np.isin(vals, CLOUD_CLASSES).sum()) / n, 1),
            "shadow_pct": round(100 * float((vals == SHADOW_CLASS).sum()) / n, 1),
            "water_pct": round(100 * float((vals == WATER_CLASS).sum()) / n, 1)}


def select_window(label, start, end, args, bbox, target, signer):
    log(f"\n=== Window {label}: {start} .. {end} ===")
    items = stac_search(bbox, start, end, args.max_cloud)
    if not items:
        log("  no scenes found (try a higher --max-cloud or different dates)")
        return None
    req = required_tiles(items, target, signer, args.retries)
    by = {}
    for it in items:
        d = by.setdefault(it["date"], {})
        if it["tile"] in req and (it["tile"] not in d or
                                  (it["cloud"] or 100) < (d[it["tile"]]["cloud"] or 100)):
            d[it["tile"]] = it
    dates = {d: t for d, t in by.items() if all(x in t for x in req)}
    log(f"  tiles needed: {req} | dates with all tiles: {len(dates)}")
    if not dates:
        return None

    def tile_cloud(d):
        return sum(t["cloud"] or 100 for t in dates[d].values()) / len(req)

    ranked = sorted(dates, key=tile_cloud)
    if args.pick.get(label):
        if args.pick[label] not in dates:
            sys.exit(f"--pick {label}={args.pick[label]}: date not in candidates: {sorted(dates)}")
        cand = [args.pick[label]]
    else:
        cand = ranked[:args.candidates]

    def run(d):
        return d, retry(lambda: probe(dates[d], target, signer), args.retries,
                        f"probe {d}", signer)

    res = {}
    with ThreadPoolExecutor(max_workers=min(4, len(cand))) as ex:
        for f in as_completed([ex.submit(run, d) for d in cand]):
            d, p = f.result()
            res[d] = p

    log(f"  {'date':<11}{'tile-cloud%':>12}{'AOI-cloud%':>12}{'shadow%':>9}"
        f"{'water%':>8}{'coverage%':>11}  status")
    ok = []
    for d in sorted(res):
        p = res[d]
        good = p["coverage_pct"] >= args.min_coverage
        if good:
            ok.append(d)
        log(f"  {d:<11}{tile_cloud(d):>12.1f}{p['cloud_pct']:>12.1f}{p['shadow_pct']:>9.1f}"
            f"{p['water_pct']:>8.1f}{p['coverage_pct']:>11.1f}  "
            f"{'ok' if good else 'PARTIAL SWATH'}")

    if ok:
        best = min(ok, key=lambda d: (res[d]["cloud_pct"] + res[d]["shadow_pct"],
                                      -res[d]["coverage_pct"]))
    elif args.allow_partial:
        best = max(res, key=lambda d: res[d]["coverage_pct"])
        log(f"  WARNING: no full-coverage date; using best partial: {best}")
    else:
        log(f"  no date reaches {args.min_coverage}% coverage in the top {len(cand)} "
            f"candidates. Raise --candidates, widen the window, or use --allow-partial.")
        return None
    log(f"  -> picked {best}  (AOI cloud est. {res[best]['cloud_pct']}%, "
        f"coverage {res[best]['coverage_pct']}%)")
    return {"window": label, "date_range": [start, end], "date": best,
            "probe": res[best],
            "tiles": {t: {"item_id": it["id"], "tile_cloud_pct": it["cloud"],
                          "assets": it["assets"]} for t, it in dates[best].items()}}


# ----------------------------------------------------------------------------- download
def already_ok(path, dtype, transform, w, h):
    if not path.exists():
        return False
    try:
        with rasterio.open(path) as s:
            return (s.dtypes[0] == dtype and s.width == w and s.height == h
                    and same_transform(s.transform, transform))
    except Exception:
        return False


def fetch_once(t, target, raw, signer):
    out = raw / t["item_id"] / f"{t['band']}.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with rasterio.open(signer.sign(t["href"])) as src:
        inter = intersect(target, tuple(src.bounds))
        if inter is None:
            return {**t, "status": "NO_OVERLAP", "secs": 0.0}
        win = int_window(src, inter)
        tf = src.window_transform(win)
        dtype = DTYPES[t["band"]]
        if src.dtypes[0] != dtype:
            raise ValueError(f"{t['band']}: source dtype {src.dtypes[0]}, expected {dtype}")
        if already_ok(out, dtype, tf, win.width, win.height):
            status = "SKIP"
        else:
            data = src.read(1, window=win)
            prof = dict(driver="GTiff", dtype=dtype, count=1, width=win.width,
                        height=win.height, crs=src.crs, transform=tf, nodata=0,
                        compress="deflate", predictor=2, tiled=True,
                        blockxsize=512, blockysize=512)
            tmp = out.with_name(out.name + ".tmp")
            with rasterio.open(tmp, "w", **prof) as dst:
                dst.write(data, 1)
            os.replace(tmp, out)
            status = "OK"
    nz = None
    if t["band"] == "B04":
        with rasterio.open(out) as s:
            nz = float((s.read(1) != 0).mean())
    return {**t, "status": status, "secs": round(time.time() - t0, 1),
            "shape": [win.height, win.width], "mb": round(out.stat().st_size / 1e6, 1),
            "transform": list(tuple(tf)[:6]), "read_bounds": list(inter),
            "nonzero_frac": nz}


def fetch(t, target, raw, signer, retries):
    tag = f"[{t['win']} {t['tile']}] {t['band']:<4}"
    try:
        r = retry(lambda: fetch_once(t, target, raw, signer), retries, tag, signer)
    except TRANSIENT as e:
        log(f"{tag} FAILED after {retries} tries: {type(e).__name__}: {e}")
        return {**t, "status": "FAIL", "secs": 0.0}
    except Exception as e:                       # logic bug: never retried
        log(f"{tag} FAIL (no retry): {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return {**t, "status": "FAIL", "secs": 0.0}
    sh = r.get("shape", ["-", "-"])
    log(f"{tag} {sh[1]}x{sh[0]}  {r.get('mb', 0)}MB  {r['secs']}s  {r['status']}")
    return r


# ----------------------------------------------------------------------------- main
def parse_kv(values, what):
    out = {}
    for v in values or []:
        if "=" not in v:
            sys.exit(f"bad {what} '{v}' (expected KEY=VALUE)")
        k, val = v.split("=", 1)
        out[k.strip().upper()] = val.strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root containing data/ (default: cwd)")
    ap.add_argument("--aoi", default=None, help="AOI geojson (default: data/aoi/vembanad_aoi.geojson)")
    ap.add_argument("--only", default="ABC", help="windows to process, e.g. A or AC")
    ap.add_argument("--window", action="append", help="override dates: B=2026-07-01:2026-09-15")
    ap.add_argument("--pick", action="append", help="force a date: A=2026-03-10")
    ap.add_argument("--max-cloud", type=float, default=50, help="tile-level cloud%% prefilter")
    ap.add_argument("--min-coverage", type=float, default=98.0, help="required AOI swath coverage %%")
    ap.add_argument("--candidates", type=int, default=12, help="dates to probe per window")
    ap.add_argument("--allow-partial", action="store_true", help="accept best partial-swath date")
    ap.add_argument("--workers", type=int, default=8, help="parallel reads (network-bound)")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--select-only", action="store_true", help="choose scenes, do not download")
    ap.add_argument("--reselect", action="store_true", help="ignore saved selection")
    args = ap.parse_args()
    args.pick = parse_kv(args.pick, "--pick")

    root = Path(args.root).resolve()
    data, raw = root / "data", root / "data" / "raw"
    aoi = Path(args.aoi) if args.aoi else data / "aoi" / "vembanad_aoi.geojson"
    if aoi.exists():
        bbox = bbox_from_geojson(aoi)
        log(f"AOI bbox from {aoi}: {bbox}")
    else:
        bbox = DEFAULT_BBOX
        log(f"AOI file not found; using built-in bbox {bbox}")

    target = snapped_bounds(bbox)
    w10, h10 = (target[2] - target[0]) // 10, (target[3] - target[1]) // 10
    log(f"Snapped target bounds ({CRS}): {target}")
    log(f"10 m grid {w10}x{h10} px | 20 m grid {w10 // 2}x{h10 // 2} px")

    wins = dict(WINDOWS)
    for k, v in parse_kv(args.window, "--window").items():
        s, e = v.split(":")
        wins[k] = (s, e)
    labels = [c for c in args.only.upper() if c in wins]

    signer = Signer()
    sel_path = data / "selected_scenes.json"
    selection = {}
    if sel_path.exists() and not args.reselect:
        selection = json.load(open(sel_path)).get("windows", {})
        log(f"\nUsing saved selection {sel_path} (use --reselect to search again)")
    todo = [l for l in labels if l not in selection]
    for l in todo:
        r = select_window(l, wins[l][0], wins[l][1], args, bbox, target, signer)
        if r:
            selection[l] = r
    missing = [l for l in labels if l not in selection]
    if selection:
        data.mkdir(parents=True, exist_ok=True)
        json.dump({"source": "planetary-computer", "collection": COLLECTION,
                   "stac": STAC_URL, "crs": CRS, "target_bounds": list(target),
                   "aoi_bbox_lonlat": list(bbox),
                   "selected_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "windows": selection}, open(sel_path, "w"), indent=2)
        log(f"\nSaved {sel_path}")
    if missing:
        log(f"\nUnresolved windows: {missing}. Fix the dates or options above and re-run.")
        sys.exit(2)
    if args.select_only:
        return

    tasks = []
    for l in labels:
        for tile, td in selection[l]["tiles"].items():
            for band in BANDS:
                tasks.append(dict(win=l, tile=tile, band=band, item_id=td["item_id"],
                                  href=td["assets"][band]))
    log(f"\nPlanned reads: {len(tasks)} | workers={args.workers}")
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for f in as_completed([ex.submit(fetch, t, target, raw, signer, args.retries)
                               for t in tasks]):
            results.append(f.result())

    by_item = {}
    for r in results:
        by_item.setdefault(r["item_id"], []).append(r)
    for item_id, rs in by_item.items():
        l = rs[0]["win"]
        info = {"item_id": item_id, "window": l, "tile": rs[0]["tile"],
                "date": selection[l]["date"], "source": "planetary-computer",
                "collection": COLLECTION, "target_bounds": list(target), "crs": CRS,
                "aoi_probe": selection[l]["probe"],
                "files": {r["band"]: {k: r.get(k) for k in
                                      ("status", "shape", "mb", "secs", "transform",
                                       "read_bounds", "nonzero_frac")} for r in rs}}
        (raw / item_id).mkdir(parents=True, exist_ok=True)
        json.dump(info, open(raw / item_id / "download_info.json", "w"), indent=2)

    log("\n=== SUMMARY ===")
    for l in labels:
        p = selection[l]["probe"]
        log(f"Window {l}  {selection[l]['date']}  AOI coverage {p['coverage_pct']}%  "
            f"cloud~{p['cloud_pct']}%  shadow~{p['shadow_pct']}%  water~{p['water_pct']}%")
        for r in sorted((x for x in results if x["win"] == l and x["band"] == "B04"),
                        key=lambda x: x["tile"]):
            nz = r.get("nonzero_frac")
            log(f"    {r['tile']}: B04 nonzero over read window = "
                f"{'n/a' if nz is None else f'{nz:.3f}'}")
    n = lambda s: sum(r["status"] == s for r in results)
    m, s = divmod(int(time.time() - t0), 60)
    log(f"\nTotal {m}m{s}s | ok={n('OK')} skipped={n('SKIP')} "
        f"no_overlap={n('NO_OVERLAP')} failed={n('FAIL')}")
    sys.exit(1 if n("FAIL") else 0)


if __name__ == "__main__":
    main()