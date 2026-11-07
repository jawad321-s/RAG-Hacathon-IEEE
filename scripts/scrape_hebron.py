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


def get(url, binary=False, want_response=False):
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
            if want_response:
                return r
            return r.content if binary else r.content.decode("utf-8", "replace")
        if r.status_code == 404 or (r.status_code >= 500 and attempt >= 1):
            print(f"  ! HTTP {r.status_code} for {url}; skipping", file=sys.stderr)
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


LINK_RE = re.compile(r"\]\((/[^)\s]*(?:\.pdf|download=[^)\s]*))\)", re.I)
RESUME = os.environ.get("RESUME", "1") == "1"


def filename_from(resp, url, label):
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    if m:
        name = unquote(m.group(1))
    elif urlparse(url).path.lower().endswith(".pdf"):
        name = unquote(os.path.basename(urlparse(url).path))
    else:
        name = (label or urlparse(url).query.split(":")[-1]) + ".pdf"
    name = re.sub(r"[^\w.\-]+", "_", name).strip("_")
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def download_pdfs(items, pdir, seen_hash):
    import hashlib
    os.makedirs(pdir, exist_ok=True)
    for p in items:
        path = urlparse(p["url"]).path
        if path.lower().endswith(".pdf"):
            existing = os.path.join(pdir, re.sub(r"[^\w.\-]+", "_", unquote(os.path.basename(path))).strip("_"))
            if os.path.exists(existing):
                h = hashlib.sha1(open(existing, "rb").read()).hexdigest()
                p["file"] = seen_hash.setdefault(h, os.path.relpath(existing, ROOT))
                continue
        resp = get(requests.utils.requote_uri(p["url"]), binary=True, want_response=True)
        if resp is None or resp.content[:5] != b"%PDF-":
            print(f"   ! not a pdf: {p['url']}")
            continue
        h = hashlib.sha1(resp.content).hexdigest()
        if h in seen_hash:
            p["file"] = seen_hash[h]
            continue
        fname = filename_from(resp, p["url"], p.get("label"))
        dest = os.path.join(pdir, fname)
        k = 2
        while os.path.exists(dest) and hashlib.sha1(open(dest, "rb").read()).hexdigest() != h:
            dest = os.path.join(pdir, f"{fname[:-4]}_{k}.pdf"); k += 1
        with open(dest, "wb") as f:
            f.write(resp.content)
        p["file"] = seen_hash[h] = os.path.relpath(dest, ROOT)
        print(f"   pdf  {p['file']}")


def pdf_links_from_md(md_text, page_url):
    out = {}
    for m in re.finditer(r"\[([^\]]*)\]\((/[^)\s]*?(?:\.pdf|download=[^)\s]*))\)|\[([^\]]*)\]\((/[^)]*?\.pdf)\)", md_text, re.I):
        label = (m.group(1) or m.group(3) or "").strip("* ")
        href = m.group(2) or m.group(4)
        if "HU-Fund-Flyer" in href:
            continue
        full = urljoin(page_url, href)
        if label.lower() in ("download", "preview", "") and full in out:
            continue
        out[full] = label if label.lower() not in ("download", "preview") else out.get(full, "")
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
        if "hebron.edu" not in p.netloc or not name:
            continue
        if not any(k in name for k in ("بكالوريوس", "تخصص", "تكنولوجيا")):
            continue
        majors.append({"major": name, "url": href})
    print(f"{len(majors)} majors")

    depts = {}
    for m in majors:
        path = urlparse(m["url"]).path
        pre = dept_prefix(path)
        if pre == "/index.php/":  # e.g. /index.php/med-col.html (college landing page)
            pre = None
            slug = os.path.basename(path)[:-5]
        else:
            slug = slug_of(pre)
        d = depts.setdefault(slug, {"slug": slug, "prefix": pre, "seed": m["url"], "majors": [], "pages": {}, "pdfs": []})
        d["majors"].append(m["major"])
        m["department"] = slug

    seen_hash = {}
    for d in depts.values():
        pre = d["prefix"]
        print(f"== {d['slug']}  ({', '.join(d['majors'])[:80]})")
        outdir = os.path.join(ROOT, "pages", d["slug"])
        cached = RESUME and os.path.isdir(outdir) and os.listdir(outdir)
        pdf_links = {}
        if cached:
            for fn in sorted(os.listdir(outdir)):
                txt = open(os.path.join(outdir, fn), encoding="utf-8").read()
                url = re.search(r"^source: (\S+)", txt, re.M).group(1)
                name = fn[:-3]
                d["pages"][name] = {"url": url, "file": f"pages/{d['slug']}/{fn}"}
                for k, v in pdf_links_from_md(txt, url).items():
                    pdf_links.setdefault(k, (v, name))
        else:
            html = get(d["seed"])
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            scope = soup if pre else content_el(soup)
            subpages = {d["seed"]}
            for a in scope.select("a[href]"):
                full = urljoin(d["seed"], a["href"]).split("#")[0]
                pp = urlparse(full)
                if not (pp.netloc.endswith("hebron.edu") and pp.path.endswith(".html") and not pp.query):
                    continue
                if pre and pp.path.startswith(pre):
                    subpages.add(full)
                elif not pre and pp.path.startswith("/index.php/med-"):
                    subpages.add(full)
            os.makedirs(outdir, exist_ok=True)
            for url in sorted(subpages):
                h = html if url == d["seed"] else get(url)
                if not h:
                    continue
                text, _, el = page_markdown(h, url)
                name = os.path.basename(urlparse(url).path)[:-5]
                with open(os.path.join(outdir, name + ".md"), "w", encoding="utf-8") as f:
                    f.write(text)
                d["pages"][name] = {"url": url, "file": f"pages/{d['slug']}/{name}.md"}
                print(f"   page {name}")
                for k, v in pdf_links_from_md(text, url).items():
                    pdf_links.setdefault(k, (v, name))
        d["pdfs"] = [{"url": u, "label": l, "found_on": n} for u, (l, n) in pdf_links.items()]
        download_pdfs(d["pdfs"], os.path.join(ROOT, "pdfs", d["slug"]), seen_hash)

    gdir = os.path.join(ROOT, "general")
    os.makedirs(gdir, exist_ok=True)
    general = {"pages": {}, "pdfs": []}
    for name, path in GENERAL_PAGES.items():
        url = BASE + path
        fpath = os.path.join(gdir, name + ".md")
        if RESUME and os.path.exists(fpath):
            text = open(fpath, encoding="utf-8").read()
        else:
            h = get(url)
            if not h:
                continue
            text, _, _ = page_markdown(h, url)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(text)
        general["pages"][name] = {"url": url, "file": f"general/{name}.md"}
        for k, v in pdf_links_from_md(text, url).items():
            general["pdfs"].append({"url": k, "label": v, "found_on": name})
        print(f"general {name}")
    download_pdfs(general["pdfs"], os.path.join(gdir, "pdfs"), seen_hash)

    with open(os.path.join(ROOT, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump({"source": START, "scraped_at": time.strftime("%Y-%m-%d"),
                   "majors": majors, "departments": list(depts.values()), "general": general},
                  f, ensure_ascii=False, indent=2)
    print("done")


if __name__ == "__main__":
    main()
