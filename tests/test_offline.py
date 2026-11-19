"""Offline tests: fake responses for each careers system. Run: python -m unittest discover tests"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scraper import run as runmod
from scraper.classify import categorize, is_corporate
from scraper.discover import detect
from scraper.sources import (greenhouse, icims, lever, parse_jobposting_html, sitemap_jsonld,
                             smartrecruiters, workday)


class Resp:
    def __init__(self, body):
        self._b = body

    @property
    def text(self):
        return self._b if isinstance(self._b, str) else json.dumps(self._b)

    def json(self):
        return self._b if not isinstance(self._b, str) else json.loads(self._b)


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _match(self, url):
        self.calls.append(url)
        for key, body in self.routes.items():
            if key in url:
                return body(url) if callable(body) else body
        raise RuntimeError(f"404 {url}")

    def get(self, url, **kw):
        return Resp(self._match(url))

    def post_json(self, url, payload):
        self.calls.append(url)
        for key, body in self.routes.items():
            if key in url:
                return body(payload) if callable(body) else body
        raise RuntimeError(f"404 {url}")


JOB_PAGE = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Senior Manager, Brand Marketing",
 "datePosted":"2026-11-10","identifier":{"@type":"PropertyValue","value":"JR-1"},
 "jobLocation":{"@type":"Place","address":{"addressLocality":"Chicago","addressRegion":"IL","addressCountry":"US"}}}
</script></head></html>"""


class Sources(unittest.TestCase):
    def test_greenhouse(self):
        http = FakeHttp({"greenhouse.io": {"jobs": [
            {"title": "Data Engineer", "absolute_url": "https://x/1", "location": {"name": "Los Angeles, CA"},
             "updated_at": "2026-11-01T00:00:00Z", "id": 1}]}})
        jobs = greenhouse({"board": "sweetgreen"}, http)
        self.assertEqual(jobs[0]["title"], "Data Engineer")
        self.assertEqual(jobs[0]["location"], "Los Angeles, CA")

    def test_lever(self):
        http = FakeHttp({"lever.co": [{"text": "Analyst", "hostedUrl": "https://l/1", "createdAt": 1763000000000,
                                        "categories": {"location": "Remote", "team": "Finance"}}]})
        j = lever({"company": "x"}, http)[0]
        self.assertTrue(j["remote"])
        self.assertEqual(j["department"], "Finance")

    def test_smartrecruiters_paginates(self):
        def page(url):
            off = int(url.split("offset=")[1])
            items = [{"id": str(off + i), "name": f"Job {off + i}", "releasedDate": "2026-11-02T00:00:00Z",
                      "location": {"city": "Ann Arbor", "region": "MI", "country": "us"}} for i in range(100 if off < 100 else 50)]
            return {"totalFound": 150, "content": items}
        jobs = smartrecruiters({"company": "Dominos"}, FakeHttp({"smartrecruiters.com": page}))
        self.assertEqual(len(jobs), 150)
        self.assertEqual(jobs[0]["location"], "Ann Arbor, MI, US")

    def test_workday(self):
        def api(payload):
            off = payload["offset"]
            posts = [{"title": f"Engineer {off + i}", "externalPath": f"/job/Seattle/Eng_{off + i}",
                      "locationsText": "Seattle, WA", "postedOn": "Posted 3 Days Ago", "bulletFields": [f"R{off + i}"]}
                     for i in range(20 if off < 20 else 5)]
            return {"total": 25, "jobPostings": posts}
        http = FakeHttp({"/wday/cxs/starbucks/StarbucksExternal/jobs": api})
        jobs = workday({"url": "https://starbucks.wd1.myworkdayjobs.com/en-US/StarbucksExternal"}, http)
        self.assertEqual(len(jobs), 25)
        self.assertEqual(jobs[0]["url"], "https://starbucks.wd1.myworkdayjobs.com/StarbucksExternal/job/Seattle/Eng_0")

    def test_icims(self):
        page0 = """<div class="row"><a href="https://corporatejobs-wendys.icims.com/jobs/45726/manager---vendor/job?in_iframe=1"
                   title="45726 - Manager - Restaurant Technology Vendor Management">x</a>
                   <span>Job Locations</span> US-OH-Dublin\n</div>"""
        http = FakeHttp({"pr=0": page0, "pr=1": "<html></html>"})
        jobs = icims({"host": "corporatejobs-wendys.icims.com"}, http)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Manager - Restaurant Technology Vendor Management")
        self.assertEqual(jobs[0]["location"], "US-OH-Dublin")
        self.assertNotIn("in_iframe", jobs[0]["url"])

    def test_jsonld_and_sitemap_cache(self):
        self.assertEqual(parse_jobposting_html(JOB_PAGE, "u")["location"], "Chicago, IL, US")
        index = "<sitemapindex><sitemap><loc>https://c.com/sm1.xml</loc></sitemap></sitemapindex>"
        sm1 = "<urlset><url><loc>https://c.com/job/1</loc></url><url><loc>https://c.com/job/2</loc></url><url><loc>https://c.com/about</loc></url></urlset>"
        http = FakeHttp({"sitemap.xml": index, "sm1.xml": sm1, "/job/": JOB_PAGE})
        cached = {"https://c.com/job/1": {"title": "Cached", "url": "https://c.com/job/1"}}
        jobs = sitemap_jsonld({"sitemap": "https://c.com/sitemap.xml", "url_pattern": "/job/"}, http, cache=cached)
        self.assertEqual([j["title"] for j in jobs], ["Cached", "Senior Manager, Brand Marketing"])
        self.assertNotIn("https://c.com/job/1", http.calls)  # cache avoided a download


class Filter(unittest.TestCase):
    def test_excludes_crew(self):
        for t in ["Crew Member", "Delivery Driver(01578) - 13214 Tesson Ferry Rd", "Assistant Manager (5424) - Milan, TN",
                  "Shift Supervisor", "barista", "General Manager (Kailua-Kona)", "Customer Service Rep(05763)",
                  "Pizza Maker/Crew Member(06702)", "Yard Driver"]:
            self.assertFalse(is_corporate({"title": t}), t)

    def test_keeps_corporate(self):
        for t in ["Senior Platform Engineer", "Director, Public Relations- Dunkin'", "Lead Product Owner",
                  "Franchise Business Consultant - Dunkin'", "Sr. Analyst, Compensation", "Manager, Culinary Innovation",
                  "Director, Crew Experience Strategy", "General Manager, Digital Platforms"]:
            self.assertTrue(is_corporate({"title": t}), t)

    def test_categories(self):
        self.assertEqual(categorize({"title": "Senior Platform Engineer"}), "Technology")
        self.assertEqual(categorize({"title": "Manager, Culinary Innovation"}), "Culinary & R&D")
        self.assertEqual(categorize({"title": "Sr. Analyst, Compensation"}), "People & HR")
        self.assertEqual(categorize({"title": "Brand Manager"}), "Marketing & Brand")


class Discover(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(detect('<a href="https://acme.wd5.myworkdayjobs.com/en-US/Acme_Careers">')[0], "workday")
        self.assertEqual(detect('src="https://boards.greenhouse.io/embed/job_board?for=cava"')[1].group(1), "cava")
        self.assertEqual(detect("https://careers-x.icims.com/jobs")[0], "icims")


class EndToEnd(unittest.TestCase):
    def test_run_writes_files_and_survives_failures(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = tmp / "brands.yaml"
        cfg.write_text("""brands:
  - {name: GoodCo, source: greenhouse, board: good}
  - {name: BadCo, source: lever, company: bad}
  - {name: OffCo, source: lever, company: off, enabled: false}
""")
        http = FakeHttp({"greenhouse.io": {"jobs": [
            {"title": "Director, Supply Chain", "absolute_url": "https://g/1", "location": {"name": "Atlanta, GA"},
             "updated_at": "2026-11-15T00:00:00Z"},
            {"title": "Team Member", "absolute_url": "https://g/2", "location": {"name": "Atlanta, GA"}}]}})
        with mock.patch.object(runmod, "DATA", tmp / "data"):
            jobs, status = runmod.run(http=http, config_path=cfg, today=dt.date(2026, 11, 19))
        self.assertEqual([j["title"] for j in jobs], ["Director, Supply Chain"])
        self.assertEqual(jobs[0]["category"], "Supply Chain")
        self.assertEqual(jobs[0]["level"], "Director")
        by = {s["brand"]: s for s in status}
        self.assertTrue(by["GoodCo"]["ok"])
        self.assertFalse(by["BadCo"]["ok"])
        self.assertIsNone(by["OffCo"]["ok"])
        self.assertTrue((tmp / "data" / "jobs.json").exists())

    def test_workday_relative_dates(self):
        self.assertEqual(runmod.normalize_date("Posted 3 Days Ago", dt.date(2026, 11, 19)), "2026-11-16")
        self.assertEqual(runmod.normalize_date("Posted 30+ Days Ago", dt.date(2026, 11, 19)), "2026-10-20")
        self.assertEqual(runmod.normalize_date("Posted Today", dt.date(2026, 11, 19)), "2026-11-19")


if __name__ == "__main__":
    unittest.main()
