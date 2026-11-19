"""
Point this at any brand's careers page and it tells you what to paste into brands.yaml.

    python -m scraper.discover "Wingstop" https://www.wingstop.com/careers
"""
import re
import sys
from urllib.parse import urlparse

from .sources import Http

PATTERNS = [
    ("workday", re.compile(r"https://[\w\-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[\w\-]+")),
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w\-]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([\w\-]+)")),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([\w\-]+)")),
    ("icims", re.compile(r"([\w\-]+\.icims\.com)")),
]


def detect(html):
    for kind, rx in PATTERNS:
        m = rx.search(html)
        if m:
            return kind, m
    return None, None


def suggest(name, url, http=None):
    http = http or Http(delay=0)
    html = http.get(url).text
    kind, m = detect(html)
    lines = [f"  - name: \"{name}\""]
    if kind == "workday":
        lines += ["    source: workday", f"    url: {m.group(0)}"]
    elif kind == "greenhouse":
        lines += ["    source: greenhouse", f"    board: {m.group(1)}"]
    elif kind == "lever":
        lines += ["    source: lever", f"    company: {m.group(1)}"]
    elif kind == "smartrecruiters":
        lines += ["    source: smartrecruiters", f"    company: {m.group(1)}"]
    elif kind == "icims":
        lines += ["    source: icims", f"    host: {m.group(1)}"]
    else:
        host = urlparse(url).netloc
        lines += ["    source: sitemap", f"    sitemap: https://{host}/sitemap.xml", "    url_pattern: /job"]
        lines.insert(0, "# No known careers system found on that page; trying the site's sitemap instead.")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    print("\nPaste this under 'brands:' in brands.yaml:\n")
    print(suggest(sys.argv[1], sys.argv[2]))
