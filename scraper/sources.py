"""
One fetcher per careers system ("ATS"). Each returns a list of raw job dicts:
    {title, url, location, posted, remote, department, req_id}
Every fetcher is defensive: a single brand failing never stops the others.
"""
import json
import re
import time
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (compatible; QSRCorporateJobsBot/1.0; "
    "+https://github.com/ - aggregates public job postings)"
)
TIMEOUT = 30


class Http:
    """Small wrapper so tests can swap in fake responses."""

    def __init__(self, delay=0.4):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        self.delay = delay

    def get(self, url, **kw):
        time.sleep(self.delay)
        r = self.s.get(url, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return r

    def post_json(self, url, payload):
        time.sleep(self.delay)
        r = self.s.post(url, json=payload, timeout=TIMEOUT,
                        headers={"Content-Type": "application/json", "Accept": "application/json"})
        r.raise_for_status()
        return r.json()


def _job(title, url, location="", posted="", remote=False, department="", req_id=""):
    return {
        "title": (title or "").strip(),
        "url": url,
        "location": (location or "").strip(),
        "posted": posted or "",
        "remote": bool(remote) or "remote" in (location or "").lower(),
        "department": (department or "").strip(),
        "req_id": str(req_id or ""),
    }


# ---------------------------------------------------------------- Greenhouse
def greenhouse(cfg, http):
    token = cfg["board"]
    data = http.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false").json()
    out = []
    for j in data.get("jobs", []):
        out.append(_job(
            j.get("title"), j.get("absolute_url"),
            (j.get("location") or {}).get("name", ""),
            j.get("first_published") or j.get("updated_at", ""),
            department=", ".join(d.get("name", "") for d in j.get("departments", []) or []),
            req_id=j.get("requisition_id") or j.get("id"),
        ))
    return out


# ---------------------------------------------------------------- Lever
def lever(cfg, http):
    company = cfg["company"]
    data = http.get(f"https://api.lever.co/v0/postings/{company}?mode=json").json()
    out = []
    for j in data:
        cats = j.get("categories") or {}
        created = j.get("createdAt")
        posted = time.strftime("%Y-%m-%d", time.gmtime(created / 1000)) if created else ""
        out.append(_job(j.get("text"), j.get("hostedUrl"), cats.get("location", ""), posted,
                        remote=(j.get("workplaceType") == "remote"),
                        department=cats.get("team", ""), req_id=j.get("id")))
    return out


# ---------------------------------------------------------------- SmartRecruiters
def smartrecruiters(cfg, http):
    company = cfg["company"]
    max_pages = cfg.get("max_pages", 80)
    out, offset = [], 0
    for _ in range(max_pages):
        data = http.get(
            f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset={offset}"
        ).json()
        items = data.get("content", [])
        for j in items:
            loc = j.get("location") or {}
            loc_txt = ", ".join(x for x in [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()] if x)
            out.append(_job(
                j.get("name"), f"https://jobs.smartrecruiters.com/{company}/{j.get('id')}",
                loc_txt, (j.get("releasedDate") or "")[:10], remote=loc.get("remote"),
                department=(j.get("department") or {}).get("label", ""), req_id=j.get("refNumber") or j.get("id"),
            ))
        offset += len(items)
        if not items or offset >= data.get("totalFound", 0):
            break
    return out


# ---------------------------------------------------------------- Workday
def workday(cfg, http):
    """cfg['url'] is the public Workday careers URL, e.g.
    https://acme.wd1.myworkdayjobs.com/en-US/AcmeCareers"""
    u = urlparse(cfg["url"])
    host = u.netloc
    tenant = cfg.get("tenant") or host.split(".")[0]
    parts = [p for p in u.path.split("/") if p and not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", p)]
    site = cfg.get("site") or parts[0]
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    out, offset, total = [], 0, None
    max_jobs = cfg.get("max_jobs", 2000)
    while offset < max_jobs:
        payload = {"appliedFacets": cfg.get("facets", {}), "limit": 20, "offset": offset,
                   "searchText": cfg.get("search", "")}
        data = http.post_json(api, payload)
        if total is None:
            total = data.get("total", 0)
        posts = data.get("jobPostings", [])
        for j in posts:
            out.append(_job(
                j.get("title"), f"https://{host}/{site}{j.get('externalPath', '')}",
                j.get("locationsText", ""), j.get("postedOn", ""),  # e.g. "Posted 3 Days Ago"
                req_id=(j.get("bulletFields") or [""])[0],
            ))
        offset += len(posts)
        if not posts or offset >= total:
            break
    return out


# ---------------------------------------------------------------- iCIMS
ICIMS_JOB = re.compile(r"/jobs/(\d+)/[^/?#]+/job")
ICIMS_LOC = re.compile(r"\b([A-Z]{2}-[A-Z]{2}-[A-Za-z .'\-]+?)(?=\s{2,}|\n|$|[A-Z][a-z]+ ID|\|)")


def icims(cfg, http):
    host = cfg["host"]
    seen, out = set(), []
    for page in range(cfg.get("max_pages", 40)):
        html = http.get(f"https://{host}/jobs/search?pr={page}&schemaId=&o=&in_iframe=1").text
        soup = BeautifulSoup(html, "html.parser")
        new = 0
        for a in soup.find_all("a", href=ICIMS_JOB):
            m = ICIMS_JOB.search(a["href"])
            jid = m.group(1)
            if jid in seen:
                continue
            title = a.get("title") or a.get_text(" ", strip=True)
            title = re.sub(r"^\d+\s*-\s*", "", title)  # iCIMS titles are often "1234 - Title"
            if not title or title.lower() in {"apply", "view job"}:
                continue
            seen.add(jid)
            new += 1
            row = a.find_parent(class_=re.compile(r"(iCIMS_JobsTableRow|row)")) or a.parent
            row_txt = row.get_text("\n", strip=True) if row else ""
            lm = ICIMS_LOC.search(row_txt)
            out.append(_job(title, urljoin(f"https://{host}/", a["href"].split("?")[0]),
                            lm.group(1).strip() if lm else "", req_id=jid))
        if new == 0:
            break
    return out


# ---------------------------------------------------------------- Sitemap + JSON-LD
def _sitemap_urls(url, http, depth=0):
    xml = http.get(url).text
    soup = BeautifulSoup(xml, "html.parser")  # tolerant of namespaces
    locs = [l.get_text(strip=True) for l in soup.find_all("loc")]
    if soup.find("sitemapindex") and depth < 2:
        urls = []
        for child in locs:
            try:
                urls += _sitemap_urls(child, http, depth + 1)
            except Exception:
                pass
        return urls
    return locs


def _find_jobposting(obj):
    if isinstance(obj, list):
        for x in obj:
            r = _find_jobposting(x)
            if r:
                return r
    elif isinstance(obj, dict):
        t = obj.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            return obj
        for k in ("@graph", "mainEntity", "itemListElement"):
            if k in obj:
                r = _find_jobposting(obj[k])
                if r:
                    return r
    return None


def parse_jobposting_html(html, url):
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or s.get_text() or "")
        except Exception:
            continue
        jp = _find_jobposting(data)
        if not jp:
            continue
        locs = jp.get("jobLocation") or []
        if isinstance(locs, dict):
            locs = [locs]
        parts = []
        for l in locs[:3]:
            a = (l or {}).get("address") or {}
            if isinstance(a, str):
                parts.append(a)
                continue
            country = a.get("addressCountry")
            if isinstance(country, dict):
                country = country.get("name")
            parts.append(", ".join(x for x in [a.get("addressLocality"), a.get("addressRegion"), country] if x))
        loc = " | ".join(p for p in parts if p)
        remote = "TELECOMMUTE" in json.dumps(jp.get("jobLocationType", "")).upper()
        if remote and not loc:
            loc = "Remote"
        ident = jp.get("identifier")
        if isinstance(ident, dict):
            ident = ident.get("value")
        dept = jp.get("occupationalCategory") or jp.get("industry") or ""
        if isinstance(dept, list):
            dept = ", ".join(map(str, dept))
        title = BeautifulSoup(jp.get("title", ""), "html.parser").get_text()
        return _job(title, url, loc, (jp.get("datePosted") or "")[:10], remote, str(dept), ident)
    return None


def sitemap_jsonld(cfg, http, cache=None):
    """Works with most branded career sites (Radancy/TalentBrew, Phenom, etc.),
    because Google for Jobs requires schema.org JobPosting data on each job page.
    `cache` = {url: previous job} so we only download pages for new postings."""
    cache = cache or {}
    pattern = re.compile(cfg.get("url_pattern", r"/job"))
    urls = [u for u in _sitemap_urls(cfg["sitemap"], http) if pattern.search(u)]
    urls = list(dict.fromkeys(urls))
    out, fetched = [], 0
    max_new = cfg.get("max_new_per_run", 400)
    for u in urls:
        if u in cache:
            out.append(cache[u])
            continue
        if fetched >= max_new:
            continue  # pick the rest up tomorrow
        fetched += 1
        try:
            j = parse_jobposting_html(http.get(u).text, u)
        except Exception:
            j = None
        if j and j["title"]:
            out.append(j)
    return out


FETCHERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "smartrecruiters": smartrecruiters,
    "workday": workday,
    "icims": icims,
    "sitemap": sitemap_jsonld,
}
