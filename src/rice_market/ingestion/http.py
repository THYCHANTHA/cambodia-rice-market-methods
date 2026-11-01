"""Download helper: every byte that enters data/raw is recorded in the download manifest."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from rice_market import config

DEFAULT_USER_AGENT = "rice-market-methods/0.1 (research toolkit; set RICE_MARKET_USER_AGENT to identify yourself)"
USER_AGENT = os.environ.get("RICE_MARKET_USER_AGENT") or DEFAULT_USER_AGENT


class QuotaExceeded(RuntimeError):
    """HTTP 403 "quota exceeded": the provider refused the call; retrying immediately will not help."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _display_path(path: Path) -> str:
    """Project-relative path when possible (keeps manifests free of machine-specific absolute paths)."""
    try:
        return path.resolve().relative_to(config.ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def record_download(source: str, url: str, path: Path, content: bytes, note: str = "") -> dict:
    """Append one provenance line. The URL is stored without query-string credentials."""
    entry = {
        "source": source,
        "url": url.split("subscription-key")[0].rstrip("?&"),
        "retrieved_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": sha256_bytes(content),
        "bytes": len(content),
        "path": _display_path(path),
        "note": note,
    }
    config.MANIFESTS.mkdir(parents=True, exist_ok=True)
    with config.DOWNLOAD_MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def get_with_retry(
    url: str, params: dict | None = None, headers: dict | None = None, tries: int = 6, timeout: int = 90
) -> requests.Response:
    """GET with back-off on 429/5xx. TLS verification is always on; failures are raised, never bypassed."""
    hdr = {"User-Agent": USER_AGENT, **(headers or {})}
    last: Exception | None = None
    for attempt in range(tries):
        try:
            resp = requests.get(url, params=params, headers=hdr, timeout=timeout)
        except requests.RequestException as exc:  # includes SSLError: do not downgrade verification
            last = exc
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(4 * (attempt + 1))
            last = RuntimeError(f"HTTP {resp.status_code}")
            continue
        if resp.status_code == 403 and "quota" in resp.text.lower():
            raise QuotaExceeded(
                f"{resp.text.strip()[:120]} for {url.split('?')[0]}. The free API quota is used up; "
                "cached files are kept, so re-run later (or set COMTRADE_API_KEY) and the download resumes."
            )
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"giving up on {url}: {last}")
