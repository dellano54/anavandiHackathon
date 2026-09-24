"""Tiny cache helpers: mtime-aware JSON loading + HTTP cache headers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_json_cache: dict[str, tuple[float, int, Any]] = {}


def load_json_cached(path: Path) -> Any:
    """Load JSON, re-reading only when mtime/size changed (process-local cache)."""
    key = str(path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        _json_cache.pop(key, None)
        raise
    sig = (stat.st_mtime, stat.st_size)
    hit = _json_cache.get(key)
    if hit is not None and (hit[0], hit[1]) == sig:
        return hit[2]
    data = json.loads(path.read_text())
    _json_cache[key] = (stat.st_mtime, stat.st_size, data)
    return data


def file_etag(path: Path) -> str:
    """Weak ETag from mtime+size (cheap, no file read)."""
    stat = path.stat()
    raw = f"{stat.st_mtime_ns}-{stat.st_size}".encode()
    return f'W/"{hashlib.md5(raw).hexdigest()}"'
