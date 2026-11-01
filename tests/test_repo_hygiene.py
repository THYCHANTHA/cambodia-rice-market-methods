"""Release gates on TRACKED files: no source data, no results, no screenshots, no secrets, no local paths,
no automated MEF retrieval, attribution and scope statements present.

These read `git ls-files`, so they test what would actually be published, not whatever sits in the working folder.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    files = [f for f in out.splitlines() if f]
    if not files:
        pytest.skip("no tracked files")
    return files


DATA_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".parquet",
    ".duckdb",
    ".db",
    ".sqlite",
    ".npz",
    ".npy",
    ".zip",
    ".dta",
    ".feather",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}


def _read(f: str) -> str:
    return (ROOT / f).read_text(encoding="utf-8", errors="ignore")


def test_no_source_data_results_or_images_tracked():
    bad = []
    for f in _tracked():
        ext = Path(f).suffix.lower()
        if f.startswith(("data/", "reports/")) or ext in DATA_EXTENSIONS or ext in IMAGE_EXTENSIONS:
            bad.append(f)
        if ext == ".json":  # no JSON of any kind is shipped (no cached API responses, no experiment records)
            bad.append(f)
    assert not bad, f"data, results, images or JSON are tracked: {bad}"


def test_no_unchanged_comtrade_records_in_tracked_text():
    pattern = re.compile(r"refPeriodId|\"primaryValue\"|\"netWgt\"|\"cifvalue\"|\"fobvalue\"")
    allowed = ("src/", "tests/")  # parser code and synthetic fixtures name these fields
    hits = [f for f in _tracked() if not f.startswith(allowed) and pattern.search(_read(f))]
    assert not hits, f"raw Comtrade field names found outside code and fixtures: {hits}"


def test_no_local_paths_secrets_or_emails():
    path_re = re.compile(r"[A-Za-z]:[\\/](?:Users|thy|Program)|/c/Users|/d/thy", re.I)
    secret_re = re.compile(r"(api[_-]?key|secret|token|passw(or)?d)\s*[=:]\s*\S{6,}|AIza|ghp_|-----BEGIN", re.I)
    email_re = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
    problems = []
    for f in _tracked():
        if Path(f).suffix.lower() == ".lock" or f == "tests/test_repo_hygiene.py":
            continue
        text = _read(f)
        for name, rx in (("path", path_re), ("secret", secret_re), ("email", email_re)):
            problems += [f"{f}: {name} {m.group(0)[:30]!r}" for m in rx.finditer(text)]
    assert not problems, problems


def test_env_example_has_no_value():
    assert re.search(r"^COMTRADE_API_KEY=\s*$", _read(".env.example"), re.M), ".env.example must be an empty template"


def test_no_large_files():
    big = [f for f in _tracked() if (ROOT / f).stat().st_size > 400_000]
    assert not big, big


def test_no_automated_mef_retrieval_in_tracked_files():
    """The MEF portal's file endpoint, dataset identifiers or any downloader must not appear anywhere."""
    banned = re.compile(r"public-datasets|api/v1/public|pd_[0-9a-f]{20,}|fetch_mef|MEF_FILE_URL|MEF_DATASETS", re.I)
    hits = [f for f in _tracked() if f != "tests/test_repo_hygiene.py" and banned.search(_read(f))]
    assert not hits, hits


def test_readme_states_scope_attribution_and_non_endorsement():
    text = _read("README.md")
    for needle in (
        "methods-and-code release",
        "not a publication of the analytical findings",
        "synthetic",
        "UN Comtrade",
        "World Bank",
        "Data EF",
        "not endorsed",
        "Bloomberg",
        "automated retrieval",
    ):
        assert needle.lower() in text.lower(), f"README is missing {needle!r}"


def test_required_documents_exist():
    for f in (
        "README.md",
        "LICENSE",
        "docs/RELEASE_SCOPE.md",
        "docs/DATA_PROVENANCE.md",
        "docs/DATA_LICENSE_AUDIT.md",
        "docs/METHODOLOGY.md",
        "docs/RELEASE_LIMITATIONS.md",
    ):
        assert f in _tracked(), f"{f} is not tracked"
