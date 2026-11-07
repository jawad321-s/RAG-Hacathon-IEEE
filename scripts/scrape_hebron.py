#!/usr/bin/env python3
"""
Scrape Hebron University undergraduate programs into a local knowledge base
for an academic-advisor RAG system.

Source: https://www.hebron.edu/index.php/academic/aca01/undergraduate.html

Output (under data/):
  catalog.json                      - every major -> department, pages, PDFs
  pages/<dept>/<page>.md            - text of each department sub-page
                                      (overview, mission, objectives, jobs,
                                      courses, guide plan, staff, ...)
  pdfs/<dept>/<file>.pdf            - official study plans (الخطط الدراسية)
  general/<name>.md                 - university-wide pages (admissions,
                                      regulations, fees, scholarships ...)

Polite crawling: one request at a time, DELAY seconds between requests,
exponential back-off when the site answers 403/429/5xx.
"""
import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

BASE = "https://www.hebron.edu"
START = BASE + "/index.php/academic/aca01/undergraduate.html"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DELAY = float(os.environ.get("DELAY", "4"))

GENERAL_PAGES = {
    "undergraduate-programs": "/index.php/academic/aca01/undergraduate.html",
    "colleges": "/index.php/academic/aca01/colleges.html",
    "admissions": "/index.php/academic/aca02/admissions.html",
    "admissions-regulations": "/index.php/academic/aca02/admissions-regulations.html",
    "fees": "/index.php/academic/aca02/hu-fees.html",
    "new-students": "/index.php/academic/aca02/newstd.html",
    "scholarships": "/index.php/academic/aca02/scholarships.html",
    "student-affairs": "/index.php/student-life-2/std01/student-affairs.html",
    "excellence-center": "/index.php/academic/aca03/excellence-center.html",
    "language-center": "/index.php/international-students-2/int02/language-center.html",
    "library": "/index.php/facilities-2/fac01/library.html",
    "diploma-programs": "/index.php/academic/aca01/diploma.html",
    "postgraduate-programs": "/index.php/academic/aca01/postgraduate.html",
}

session = requests.Session()
session.headers["User-Agent"] = "RAG-Hackathon-IEEE academic-advisor crawler (educational project)"
_last = [0.0]


def get(url, binary=False):
    for attempt in range(6):
        wait = DELAY - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = session.get(url, timeout=60)
        except requests.RequestException as e:
            print(f"  ! {e}", file=sys.stderr)
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code == 200 and (binary or "403: Access Forbidden" not in r.text[:500]):
            return r.content if binary else r.content.decode("utf-8", "replace")
        if r.status_code == 404:
            return None
        backoff = 60 * (2 ** attempt)
        print(f"  ! HTTP {r.status_code} for {url}; waiting {backoff}s", file=sys.stderr)
        time.sleep(backoff)
    print(f"  !! giving up on {url}", file=sys.stderr)
    return None


def content_el(soup):
    return soup.select_one("#sp-component") or soup.body


def page_markdown(html, url):
    soup = BeautifulSoup(html, "lxml")
    el = content_el(soup)
    for bad in el.select("script, style, .modal, noscript"):
        bad.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    text = md(str(el), heading_style="ATX")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return f"---\nsource: {url}\ntitle: {title}\n---\n\n{text}\n", soup, el


def dept_prefix(path):
    # /index.php/it-dep/it-dep1/it-dep1-plans.html -> /index.php/it-dep/it-dep1/
    return path.rsplit("/", 1)[0] + "/"


def slug_of(prefix):
    parts = [p for p in prefix.strip("/").split("/") if p and p != "index.php"]
    return "__".join(parts)


def collect_pdfs(el, page_url):
    out = {}
    for a in el.select("a[href], iframe[src], embed[src], object[data]"):
        h = a.get("href") or a.get("src") or a.get("data")
        full = urljoin(page_url, h)
        p = urlparse(full)
        if p.netloc and "hebron.edu" not in p.netloc:
            continue
        label = a.get_text(" ", strip=True)
        if p.path.lower().endswith(".pdf") and "HU-Fund-Flyer" not in p.path:
            out.setdefault(full, label)
    # phoca download items without a direct preview link
    for a in el.select("a[href*='download=']"):
        full = urljoin(page_url, a["href"])
        out.setdefault(full, a.get_text(" ", strip=True))
    return out


def main():
    os.makedirs(ROOT, exist_ok=True)
    html = get(START)
    soup = BeautifulSoup(html, "lxml")
    body = content_el(soup)

    majors = []
    for a in body.select("a[href]"):
        name = a.get_text(" ", strip=True)
        href = urljoin(START, a["href"])
        p = urlparse(href)
        if "hebron.edu" not in p.netloc or not name or "بكالوريوس" not in name and "تخصص" not in name and "تكنولوجيا" not in name:
            continue
        majors.append({"major": name, "url": href})
    print(f"{len(majors)} majors")

    depts = {}
    for m in majors:
        path = urlparse(m["url"]).path
        pre = dept_prefix(path)
        d = depts.setdefault(pre, {"slug": slug_of(pre), "seed": m["url"], "majors": [], "pages": {}, "pdfs": []})
        d["majors"].append(m["major"])
        m["department"] = d["slug"]

    seen_pdf = set()
    for pre, d in depts.items():
        print(f"== {d['slug']}  ({', '.join(d['majors'])[:80]})")
        html = get(d["seed"])
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        subpages = {d["seed"]}
        for a in soup.select("a[href]"):
            full = urljoin(d["seed"], a["href"]).split("#")[0]
            pp = urlparse(full)
            if pp.netloc.endswith("hebron.edu") and pp.path.startswith(pre) and pp.path.endswith(".html") and not pp.query:
                subpages.add(full)
        outdir = os.path.join(ROOT, "pages", d["slug"])
        os.makedirs(outdir, exist_ok=True)
        for url in sorted(subpages):
            h = html if url == d["seed"] else get(url)
            if not h:
                continue
            text, s2, el = page_markdown(h, url)
            name = os.path.basename(urlparse(url).path)[:-5]
            with open(os.path.join(outdir, name + ".md"), "w", encoding="utf-8") as f:
                f.write(text)
            d["pages"][name] = {"url": url, "file": os.path.relpath(os.path.join(outdir, name + ".md"), ROOT)}
            print(f"   page {name}")
            for purl, label in collect_pdfs(el, url).items():
                if purl in seen_pdf:
                    continue
                seen_pdf.add(purl)
                d["pdfs"].append({"url": purl, "label": label, "found_on": name})

        # prefer direct .pdf links; download only "?download=" ones when no direct pdf exists
        direct = [p for p in d["pdfs"] if urlparse(p["url"]).path.lower().endswith(".pdf")]
        todo = direct if direct else d["pdfs"]
        pdir = os.path.join(ROOT, "pdfs", d["slug"])
        os.makedirs(pdir, exist_ok=True)
        for p in todo:
            pth = urlparse(p["url"])
            fname = unquote(os.path.basename(pth.path)) if pth.path.lower().endswith(".pdf") else (pth.query.split(":")[-1] + ".pdf")
            fname = re.sub(r"[^\w.\-]+", "_", fname)
            dest = os.path.join(pdir, fname)
            if not os.path.exists(dest):
                data = get(requests.utils.requote_uri(p["url"]), binary=True)
                if not data or not data[:5] == b"%PDF-":
                    print(f"   ! not a pdf: {p['url']}")
                    continue
                with open(dest, "wb") as f:
                    f.write(data)
            p["file"] = os.path.relpath(dest, ROOT)
            print(f"   pdf  {fname}")

    gdir = os.path.join(ROOT, "general")
    os.makedirs(gdir, exist_ok=True)
    general = {}
    for name, path in GENERAL_PAGES.items():
        url = BASE + path
        h = get(url)
        if not h:
            continue
        text, _, el = page_markdown(h, url)
        with open(os.path.join(gdir, name + ".md"), "w", encoding="utf-8") as f:
            f.write(text)
        general[name] = {"url": url, "file": f"general/{name}.md"}
        for purl, label in collect_pdfs(el, url).items():
            if purl.lower().split("?")[0].endswith(".pdf") and purl not in seen_pdf:
                seen_pdf.add(purl)
                fname = re.sub(r"[^\w.\-]+", "_", unquote(os.path.basename(urlparse(purl).path)))
                data = get(requests.utils.requote_uri(purl), binary=True)
                if data and data[:5] == b"%PDF-":
                    with open(os.path.join(gdir, fname), "wb") as f:
                        f.write(data)
                    general.setdefault("_pdfs", []).append({"url": purl, "label": label, "file": f"general/{fname}"})
        print(f"general {name}")

    with open(os.path.join(ROOT, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump({"source": START, "scraped_at": time.strftime("%Y-%m-%d"),
                   "majors": majors, "departments": list(depts.values()), "general": general},
                  f, ensure_ascii=False, indent=2)
    print("done")


if __name__ == "__main__":
    main()
