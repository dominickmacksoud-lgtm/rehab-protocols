"""Generate sitemap.xml from what actually exists on disk.

Replaces the hand-maintained file, whose lastmod dates had drifted two months
stale and which listed /privacy/ and /terms-of-use/ despite both being noindex —
a Search Console warning and wasted crawl budget.

Deliberately omits <changefreq> and <priority>: Google ignores both, so they are
stale noise. Sitemap index is unnecessary at this scale — ~965 URLs is about 2%
of the 50,000-URL limit. Revisit past ~40,000.
"""

import json
import re
import subprocess
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from rp_data import ROOT, write_text

SITE = 'https://rehabprotocols.com'
SITEMAP_PATH = ROOT / 'sitemap.xml'
LASTMOD_CACHE = ROOT / '.page-lastmod.json'

# Hand-maintained pages. Anything noindex is intentionally absent.
STATIC_PAGES = [
    '/', '/guidelines/', '/protocols/', '/pricing/', '/hep/', '/treatment-planner/',
    '/about/', '/contact/', '/requests/',
    '/shoulder/', '/knee/', '/hip/', '/spine/', '/ankle-foot/', '/elbow/', '/wrist-hand/',
]

NOINDEX_RE = re.compile(r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*noindex',
                        re.IGNORECASE)


def path_to_file(url_path):
    rel = url_path.strip('/')
    return (ROOT / rel / 'index.html') if rel else (ROOT / 'index.html')


def is_noindex(file_path):
    try:
        return bool(NOINDEX_RE.search(file_path.read_text(encoding='utf-8')))
    except OSError:
        return True


def git_lastmod(rel_path, cache):
    """Last commit date for a file.

    Not file mtime: a fresh clone resets mtime, which would make every URL claim
    to have changed today.
    """
    key = str(rel_path)
    if key in cache:
        return cache[key]
    try:
        out = subprocess.run(
            ['git', 'log', '-1', '--format=%cs', '--', key],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        stamp = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        stamp = ''
    stamp = stamp or date.today().isoformat()
    cache[key] = stamp
    return stamp


def generate(ledger=None):
    cache = {}
    if LASTMOD_CACHE.exists():
        try:
            cache = json.loads(LASTMOD_CACHE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            cache = {}

    urls = []
    seen = set()

    def add(url_path, lastmod):
        if url_path in seen:
            return
        f = path_to_file(url_path)
        if not f.exists() or is_noindex(f):
            return
        seen.add(url_path)
        urls.append((url_path, lastmod))

    for p in STATIC_PAGES:
        f = path_to_file(p)
        if f.exists():
            add(p, git_lastmod(f.relative_to(ROOT).as_posix(), cache))

    # Generated pages: lastmod comes from the ledger's content_sha tracking, so a
    # protocol only claims to have changed when its rendered content really did.
    if ledger:
        for entry in ledger.values():
            if entry.get('status') == 'retired':
                continue
            topic, slug = entry['topic_slug'], entry['slug']
            stamp = entry.get('last_changed') or date.today().isoformat()
            add(f'/protocols/{topic}/{slug}/', stamp)

    # Hub pages: newest change among their members.
    hub_dates = {}
    if ledger:
        for entry in ledger.values():
            if entry.get('status') == 'retired':
                continue
            t = entry['topic_slug']
            stamp = entry.get('last_changed') or date.today().isoformat()
            hub_dates[t] = max(hub_dates.get(t, ''), stamp)
    for topic, stamp in sorted(hub_dates.items()):
        add(f'/protocols/{topic}/', stamp)

    urls.sort(key=lambda u: u[0])
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url_path, lastmod in urls:
        lines.append('  <url>')
        lines.append(f'    <loc>{xml_escape(SITE + url_path)}</loc>')
        lines.append(f'    <lastmod>{xml_escape(lastmod)}</lastmod>')
        lines.append('  </url>')
    lines.append('</urlset>')

    write_text(SITEMAP_PATH, '\n'.join(lines) + '\n')
    write_text(LASTMOD_CACHE, json.dumps(cache, indent=0, sort_keys=True))
    print(f'  Generated sitemap.xml — {len(urls)} URLs')
    return len(urls)
