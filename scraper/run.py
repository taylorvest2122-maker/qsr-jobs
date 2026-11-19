"""
Daily job: fetch every brand in brands.yaml, keep corporate roles, write site/data/*.json

    python -m scraper.run                 # all brands
    python -m scraper.run --only "Wendy's"  # one brand (handy for testing)
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import traceback
from pathlib import Path

import yaml

from .classify import categorize, is_corporate, seniority
from .sources import FETCHERS, Http

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"


def load_previous():
    p = DATA / "jobs.json"
    if p.exists():
        try:
            return json.loads(p.read_text())["jobs"]
        except Exception:
            pass
    return []


def normalize_date(raw, today):
    """Accepts ISO dates or Workday-style 'Posted 3 Days Ago'. Returns YYYY-MM-DD or ''."""
    if not raw:
        return ""
    raw = str(raw)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    low = raw.lower()
    if "today" in low:
        return today.isoformat()
    if "yesterday" in low:
        return (today - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*days?", low)
    if m:
        return (today - dt.timedelta(days=int(m.group(1)))).isoformat()
    return ""


def job_id(brand, url):
    return hashlib.sha1(f"{brand}|{url}".encode()).hexdigest()[:12]


def run(only=None, http=None, config_path=None, today=None):
    today = today or dt.date.today()
    http = http or Http()
    cfg = yaml.safe_load(Path(config_path or ROOT / "brands.yaml").read_text())
    previous = load_previous()
    prev_by_id = {j["id"]: j for j in previous}

    all_jobs, status = [], []
    for brand in cfg["brands"]:
        name = brand["name"]
        if only and name.lower() != only.lower():
            continue
        if not brand.get("enabled", True):
            status.append({"brand": name, "ok": None, "count": 0, "message": "Turned off in brands.yaml"})
            continue
        fetch = FETCHERS.get(brand["source"])
        if not fetch:
            status.append({"brand": name, "ok": False, "count": 0, "message": f"Unknown source '{brand['source']}'"})
            continue
        try:
            kwargs = {}
            if brand["source"] == "sitemap":
                kwargs["cache"] = {j["url"]: j for j in previous if j["brand"] == name}
            raw = fetch(brand, http, **kwargs)
            kept = 0
            for j in raw:
                if not j.get("title") or not j.get("url"):
                    continue
                if not is_corporate(j, brand):
                    continue
                jid = job_id(name, j["url"])
                prev = prev_by_id.get(jid, {})
                posted = normalize_date(j.get("posted"), today) or prev.get("posted", "")
                all_jobs.append({
                    "id": jid,
                    "brand": name,
                    "parent": brand.get("parent", ""),
                    "title": j["title"],
                    "url": j["url"],
                    "location": j.get("location", ""),
                    "remote": bool(j.get("remote")),
                    "department": j.get("department", ""),
                    "category": categorize(j),
                    "level": seniority(j["title"]),
                    "posted": posted,
                    "first_seen": prev.get("first_seen", today.isoformat()),
                })
                kept += 1
            status.append({"brand": name, "ok": True, "count": kept, "scanned": len(raw),
                           "message": "OK" if raw else "Connected, but found 0 postings — check the settings"})
        except Exception as e:
            traceback.print_exc()
            status.append({"brand": name, "ok": False, "count": 0, "message": f"{type(e).__name__}: {e}"[:300]})
            # Keep yesterday's postings for this brand rather than wiping them out
            for j in previous:
                if j["brand"] == name:
                    all_jobs.append(j)

    if only:  # merge with other brands' existing data
        all_jobs += [j for j in previous if j["brand"].lower() != only.lower()]

    # de-duplicate
    seen, unique = set(), []
    for j in all_jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)
    unique.sort(key=lambda j: (j.get("posted") or j.get("first_seen") or ""), reverse=True)

    DATA.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (DATA / "jobs.json").write_text(json.dumps({"updated": stamp, "count": len(unique), "jobs": unique}, indent=1))
    (DATA / "status.json").write_text(json.dumps({"updated": stamp, "sources": status}, indent=1))

    print(f"\n{'Brand':28} {'Status':8} Jobs")
    for s in status:
        flag = "OK" if s["ok"] else ("OFF" if s["ok"] is None else "FAILED")
        print(f"{s['brand']:28} {flag:8} {s['count']:>4}   {'' if s['ok'] else s['message']}")
    print(f"\nTotal corporate postings: {len(unique)}")
    return unique, status


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Run a single brand by name")
    args = ap.parse_args()
    run(only=args.only)
    sys.exit(0)
