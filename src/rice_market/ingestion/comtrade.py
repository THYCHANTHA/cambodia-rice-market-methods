"""UN Comtrade monthly rice trade (HS 1006 and its 6-digit children).

Works WITHOUT a key through the free preview endpoint (one period per call, at most 500 records, rate limited).
If COMTRADE_API_KEY is set the keyed endpoint is used instead, which accepts several periods per call.
One JSON file is cached per (flow, reporter-or-partner, period); cached files are never re-requested.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rice_market import config
from rice_market.ingestion.http import get_with_retry, record_download

PAUSE_SECONDS = 3.6  # the preview endpoint answers 429 below roughly one call per 3 seconds


def periods(start: str, end: str) -> list[str]:
    """Inclusive list of YYYYMM strings."""
    y, m = int(start[:4]), int(start[4:])
    ey, em = int(end[:4]), int(end[4:])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y}{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def cache_path(view: str, period: str) -> Path:
    return config.RAW / "comtrade" / view / f"{period}.json"


def fetch_period(view: str, period: str, force: bool = False) -> tuple[Path, bool]:
    """Fetch one month. view = 'exports' (Cambodia as reporter, flow X) or 'mirror' (partners' imports from Cambodia).

    Returns (path, downloaded). Empty months are cached too, so that an absent month is a recorded fact.
    """
    path = cache_path(view, period)
    if path.exists() and not force:
        return path, False
    params = {
        "period": period,
        "cmdCode": ",".join(config.HS_RICE),
        "flowCode": "X" if view == "exports" else "M",
    }
    if view == "exports":
        params["reporterCode"] = config.CAMBODIA_COMTRADE_CODE
    else:
        params["partnerCode"] = config.CAMBODIA_COMTRADE_CODE
    headers = {}
    url = config.COMTRADE_PREVIEW_URL
    key = config.comtrade_key()
    if key:
        url = config.COMTRADE_KEYED_URL
        headers["Ocp-Apim-Subscription-Key"] = key
    resp = get_with_retry(url, params=params, headers=headers)
    payload = resp.content
    body = json.loads(payload)
    if body.get("error"):
        raise RuntimeError(f"Comtrade error for {view} {period}: {body['error']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    record_download(
        f"comtrade_{view}",
        resp.request.url or url,
        path,
        payload,
        note=f"records={body.get('count')}; preview={'no' if key else 'yes'}",
    )
    return path, True


def fetch_range(view: str, start: str, end: str, log=print, max_calls: int | None = None) -> dict:
    """Fetch every month in [start, end] that is not cached yet, one request at a time.

    Fair-use behaviour: strictly sequential, a pause after each download, cached months are never re-requested, and the
    run stops after `max_calls` network calls (a per-run budget; None = unlimited) or at the first quota refusal
    (QuotaExceeded propagates to the caller). Returns counts, with stopped=True when the budget ended the run early.
    """
    stats = {"downloaded": 0, "cached": 0, "empty": 0, "stopped": False}
    for p in periods(start, end):
        if max_calls is not None and stats["downloaded"] >= max_calls and not cache_path(view, p).exists():
            stats["stopped"] = True
            log(f"stopped after {max_calls} network calls (budget); re-run to continue")
            break
        path, did = fetch_period(view, p)
        stats["downloaded" if did else "cached"] += 1
        if json.loads(path.read_text(encoding="utf-8")).get("count", 0) == 0:
            stats["empty"] += 1
        if did:
            log(f"{view} {p} ok")
            time.sleep(PAUSE_SECONDS)
    return stats
