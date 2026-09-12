"""Phase A0: fetch every raw input and record what was fetched.

Writes data/raw/MANIFEST.json with URL, size, SHA-256 and retrieval time for
each file. The manifest is how the writeup can say exactly which vintage of
each dataset produced the headline number; the sources are all republished
over time (Price Paid monthly, ONSPD quarterly, GIAS daily).

Usage:  python -m pipeline.p01_download [--only prices|onspd|ofsted|gias|stations]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from line54 import config

PRICE_PAID_URL = "https://price-paid-data.publicdata.landregistry.gov.uk/pp-{year}.csv"

# ONSPD August 2026, ArcGIS item on the ONS Open Geography Portal.
ONSPD_URL = "https://www.arcgis.com/sharing/rest/content/items/9e5a92a3cfb14dc7ad43d6ea7a7b8c7f/data"

_OFSTED = "https://assets.publishing.service.gov.uk/media/"
# Inspection-level files, Sept 2015 onward. Each row carries the previous
# inspection's grade and the URN at that time, which covers pre-2015 grades and
# academy conversions. The Dec 2019 snapshot supplies the grade in force for
# schools not inspected at all between 2015 and 2019 (Outstanding schools were
# exempt from routine inspection until 2021).
OFSTED_FILES = {
    "ofsted_all_2015_2019.csv": "5f6b4b76d3bf7f72337b6ef7/Management_information_-_state-funded_schools_1_September_2015_to_31_August_2019.csv",
    "ofsted_all_ytd_2020.csv": "5f5891b18fa8f51061921e7c/Management_information_-_state-funded_schools_-_all_inspections_-_year_to_date_published_by_31_August_2020.csv",
    "ofsted_all_ytd_2021.csv": "6141a83c8fa8f503ba3dc8e1/Management_information_-_state-funded_schools_-_all_inspections_-_year_to_date_published_by_31_Aug_2021.csv",
    "ofsted_all_ytd_2022.csv": "63219b51e90e072ce47b76ba/Management_information_-_state-funded_schools_-_all_inspections_-_year_to_date_published_by_31_Aug_2022.csv",
    "ofsted_all_ytd_2023.csv": "64ff268957278000142518d2/Management_information_-_state-funded_schools_-_all_inspections_-_year_to_date_published_by_31_Aug_2023.csv",
    "ofsted_all_ytd_2024.csv": "66e1478ddb528c56bc8e830b/Management_information_-_state-funded_schools_-_all_inspections_-_year_to_date_published_by_31_Aug_2024.csv",
    "ofsted_all_ytd_2025.csv": "68bfd548223d92d088f01dd8/Management_information_-_state-funded_schools_-_all_inspections_-_year_to_date_published_by_31_Aug_2025.csv",
    "ofsted_all_ytd_2026.csv": "6aa0175292e72b8ac437ef36/Management_information_-_state-funded_schools_-_all_inspections_-_year_to_date_published_by_31_August_2026.csv",
    "ofsted_latest_2019-12-31.csv": "5e188f9f40f0b65dc536c1b6/Management_information_-_state-funded_schools_-_latest_inspections_at_31_Dec_2019.csv",
    "ofsted_latest_2026-08-31.csv": "6aa0175392e72b8ac437ef37/Management_information_-_state-funded_schools_-_latest_inspections_as_at_31_August_2026.csv",
}

GIAS_BASE = "https://get-information-schools.service.gov.uk"
# Collate-form tags for "All establishment data": fields CSV and links CSV.
GIAS_TAGS = ("all.edubase.data", "all.edubase.data.links")

MANIFEST = config.RAW / "MANIFEST.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def _key(path: Path) -> str:
    return path.relative_to(config.RAW).as_posix()


def _record(manifest: dict, path: Path, url: str) -> None:
    manifest[_key(path)] = {
        "url": url,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def fetch(session: requests.Session, url: str, dest: Path, manifest: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    head = session.head(url, allow_redirects=True, timeout=60)
    expected = int(head.headers.get("Content-Length", 0)) or None
    # Skip only on an exact size match, so a half-finished download is redone.
    if dest.exists() and expected and dest.stat().st_size == expected:
        print(f"  have {dest.name}")
        if _key(dest) not in manifest:
            _record(manifest, dest, url)
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  get  {dest.name} ({(expected or 0) / 1e6:,.0f} MB)", flush=True)
    with session.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    if expected and tmp.stat().st_size != expected:
        raise IOError(f"{dest.name}: got {tmp.stat().st_size} bytes, expected {expected}")
    tmp.replace(dest)
    _record(manifest, dest, url)


def fetch_prices(s: requests.Session, m: dict) -> None:
    # One year either side of the window is not needed: transfer date is the
    # filter, and each yearly file holds exactly that calendar year.
    for year in range(config.SALES_START.year, config.SALES_END.year + 1):
        fetch(s, PRICE_PAID_URL.format(year=year), config.RAW / "price_paid" / f"pp-{year}.csv", m)


def fetch_onspd(s: requests.Session, m: dict) -> None:
    dest = config.RAW / "onspd" / "ONSPD_AUG_2026.zip"
    fetch(s, ONSPD_URL, dest, m)
    # The zip holds per-area CSVs plus a single UK file; only the UK file is used.
    with zipfile.ZipFile(dest) as z:
        uk = [n for n in z.namelist() if re.search(r"Data/ONSPD_[A-Z]{3}_\d{4}_UK\.csv$", n)]
        if not uk:
            raise FileNotFoundError("no single UK CSV inside the ONSPD zip: " + ", ".join(z.namelist()[:10]))
        out = dest.parent / Path(uk[0]).name
        if not out.exists():
            print(f"  unzip {out.name}", flush=True)
            with z.open(uk[0]) as src, out.open("wb") as f:
                while chunk := src.read(1 << 20):
                    f.write(chunk)


def fetch_ofsted(s: requests.Session, m: dict) -> None:
    for name, path in OFSTED_FILES.items():
        fetch(s, _OFSTED + path, config.RAW / "ofsted" / name, m)


def fetch_gias(s: requests.Session, m: dict) -> None:
    """GIAS moved from dated direct links to a collate-then-poll form."""
    dest_dir = config.RAW / "gias"
    dest_dir.mkdir(parents=True, exist_ok=True)
    html = s.get(GIAS_BASE + "/Downloads", timeout=60).text
    start = html.find('action="/Downloads/Collate"')
    form = html[start : html.find("</form>", start)]
    data, selected = [], set()
    for tag in re.findall(r"<input[^>]*>", form):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        data.append([name.group(1), value.group(1) if value else ""])
    tags = {re.search(r"\[(\d+)\]", n).group(1): v for n, v in data if n.endswith(".Tag")}
    for pair in data:
        if pair[0].endswith(".Selected"):
            idx = re.search(r"\[(\d+)\]", pair[0]).group(1)
            pair[1] = "true" if tags.get(idx) in GIAS_TAGS else "false"
            if pair[1] == "true":
                selected.add(tags[idx])
    if selected != set(GIAS_TAGS):
        raise RuntimeError(f"GIAS form changed; could not select {set(GIAS_TAGS) - selected}")

    r = s.post(GIAS_BASE + "/Downloads/Collate", data=data, timeout=120)
    generated = r.url
    for _ in range(120):
        if "generation-completed-heading" in r.text:
            break
        time.sleep(5)
        r = s.get(generated, timeout=60)
    else:
        raise TimeoutError(f"GIAS file never finished generating: {generated}")

    # The finished page offers the zip through a second POST form.
    start = r.text.find('action="/Downloads/Download/Extract"')
    form = r.text[start : r.text.find("</form>", start)]
    extract = dict(re.findall(r'name="([^"]+)"[^>]*?value="([^"]*)"', form))
    stamp = datetime.now().strftime("%Y%m%d")
    zpath = dest_dir / f"gias_{stamp}.zip"
    url = f"{generated} (extract id {extract.get('id')})"
    print(f"  get  {zpath.name}", flush=True)
    with s.post(GIAS_BASE + "/Downloads/Download/Extract", data=extract, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with zpath.open("wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    _record(m, zpath, url)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest_dir)
        print("  unzip " + ", ".join(z.namelist()))


def fetch_stations(s: requests.Session, m: dict) -> None:
    """NaPTAN access nodes for the R2 distance-to-station balance check.

    Area 910 is National Rail (including Overground and Elizabeth line
    stations); 940 is Underground, DLR and tram. About 1.2 MB together.
    """
    for area in ("910", "940"):
        url = f"https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv&atcoAreaCodes={area}"
        dest = config.RAW / "naptan" / f"naptan_{area}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        # The API sends no Content-Length, so the size check in fetch() cannot apply.
        with s.get(url, timeout=180) as r:
            r.raise_for_status()
            dest.write_bytes(r.content)
        print(f"  get  {dest.name} ({len(r.content) / 1e6:.2f} MB)")
        _record(m, dest, url)


STEPS = {"prices": fetch_prices, "onspd": fetch_onspd, "ofsted": fetch_ofsted, "gias": fetch_gias, "stations": fetch_stations}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", choices=sorted(STEPS), action="append")
    args = p.parse_args(argv)
    session = requests.Session()
    session.headers["User-Agent"] = "the-54000-line research download (+OGL v3.0 data)"
    manifest = _load_manifest()
    for name in args.only or ["ofsted", "gias", "onspd", "stations", "prices"]:
        print(f"[{name}]", flush=True)
        STEPS[name](session, manifest)
    print(f"manifest: {MANIFEST}")


if __name__ == "__main__":
    sys.exit(main())
