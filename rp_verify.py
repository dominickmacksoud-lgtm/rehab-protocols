"""Read-only verifier for the generated static pages, ledger, and sitemap.

Runs no network calls and writes nothing. Exit 0 = clean, 1 = failures found.

    python rp_verify.py              # everything that currently exists
    python rp_verify.py --pages      # HTML structural checks only
    python rp_verify.py --links      # internal link resolution only
    python rp_verify.py --ledger     # slug-ledger invariants only
    python rp_verify.py --sitemap    # sitemap checks only

Checks that do not live here because they need to run the generator:
  - idempotency (run twice, `git status --porcelain` must be empty)
Those are documented in CLAUDE.md and run manually before committing.
"""

import sys
import json
import re
import csv
import argparse
from html.parser import HTMLParser
from pathlib import Path
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent
SITE = 'https://rehabprotocols.com'

# Directories that never contain pages we generate or own.
SKIP_DIRS = {'.git', '.github', '__pycache__', 'node_modules', 'templates', '.claude'}

# Title/description length windows. These are soft SEO guidance, not hard rules —
# they catch truncation and empty-string bugs, which is the real point.
TITLE_MIN, TITLE_MAX = 15, 70
DESC_MIN, DESC_MAX = 70, 165


class PageParser(HTMLParser):
    """Collects just enough structure to assert on. Not a full DOM."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.lang = None
        self.h1s = []
        self.meta = {}          # name/property -> content
        self.canonical = None
        self.jsonld_raw = []
        self.hrefs = []
        self._in_title = False
        self._in_h1 = False
        self._in_jsonld = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html':
            self.lang = a.get('lang')
        elif tag == 'title':
            self._in_title = True
            self._buf = []
        elif tag == 'h1':
            self._in_h1 = True
            self._buf = []
        elif tag == 'meta':
            key = a.get('name') or a.get('property')
            if key:
                self.meta[key.lower()] = a.get('content', '')
        elif tag == 'link':
            rels = (a.get('rel') or '').lower().split()
            if 'canonical' in rels:
                self.canonical = a.get('href')
            if a.get('href'):
                self.hrefs.append(a['href'])
        elif tag == 'a':
            if a.get('href'):
                self.hrefs.append(a['href'])
        elif tag == 'script':
            if (a.get('type') or '').lower() == 'application/ld+json':
                self._in_jsonld = True
                self._buf = []
            elif a.get('src'):
                self.hrefs.append(a['src'])
        elif tag == 'img' and a.get('src'):
            self.hrefs.append(a['src'])

    def handle_endtag(self, tag):
        # Only the tag that opened a capture may close it. Clearing the buffer on
        # every endtag would drop text in <h1>Foo <span>bar</span></h1>.
        if tag == 'title' and self._in_title:
            self.title = ''.join(self._buf).strip()
            self._in_title = False
            self._buf = []
        elif tag == 'h1' and self._in_h1:
            self.h1s.append(' '.join(''.join(self._buf).split()))
            self._in_h1 = False
            self._buf = []
        elif tag == 'script' and self._in_jsonld:
            self.jsonld_raw.append(''.join(self._buf).strip())
            self._in_jsonld = False
            self._buf = []

    def handle_data(self, data):
        if self._in_title or self._in_h1 or self._in_jsonld:
            self._buf.append(data)


class Report:
    def __init__(self):
        self.failures = []
        self.warnings = []
        self.checked = 0

    def fail(self, where, msg):
        self.failures.append(f'{where}: {msg}')

    def warn(self, where, msg):
        self.warnings.append(f'{where}: {msg}')

    def summary(self, label):
        print(f'\n  {label}')
        if self.warnings:
            print(f'    {len(self.warnings)} warning(s):')
            for w in self.warnings[:40]:
                print(f'      {w}')
            if len(self.warnings) > 40:
                print(f'      ... and {len(self.warnings) - 40} more')
        if self.failures:
            print(f'    {len(self.failures)} FAILURE(s):')
            for f in self.failures[:40]:
                print(f'      {f}')
            if len(self.failures) > 40:
                print(f'      ... and {len(self.failures) - 40} more')
        else:
            print(f'    OK — {self.checked} checked, 0 failures')
        return not self.failures


def iter_html():
    """Every .html file we own, as (path, rel_posix)."""
    for p in sorted(ROOT.rglob('*.html')):
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        yield p, p.relative_to(ROOT).as_posix()


def parse(path):
    parser = PageParser()
    parser.feed(path.read_text(encoding='utf-8'))
    return parser


def expected_canonical(rel):
    """/foo/index.html -> https://rehabprotocols.com/foo/"""
    if rel == 'index.html':
        return SITE + '/'
    if rel.endswith('/index.html'):
        return f'{SITE}/{rel[:-len("index.html")]}'
    return f'{SITE}/{rel}'


# ── Page structure ────────────────────────────────────────────────────────────

def check_pages(rep):
    for path, rel in iter_html():
        rep.checked += 1
        try:
            page = parse(path)
        except Exception as e:
            rep.fail(rel, f'HTML failed to parse: {e}')
            continue

        if page.lang != 'en':
            rep.fail(rel, f'<html lang> is {page.lang!r}, expected "en"')

        # Exactly one h1 — the whole point of the double-H1 fix.
        if len(page.h1s) == 0:
            rep.fail(rel, 'no <h1>')
        elif len(page.h1s) > 1:
            rep.fail(rel, f'{len(page.h1s)} <h1> tags (expected 1): {page.h1s[:3]}')

        if not page.title:
            rep.fail(rel, 'missing <title>')
        elif not (TITLE_MIN <= len(page.title) <= TITLE_MAX):
            rep.warn(rel, f'title {len(page.title)} chars (want {TITLE_MIN}-{TITLE_MAX}): {page.title[:70]!r}')

        desc = page.meta.get('description')
        if desc is None:
            rep.fail(rel, 'missing meta description')
        elif not (DESC_MIN <= len(desc) <= DESC_MAX):
            rep.warn(rel, f'description {len(desc)} chars (want {DESC_MIN}-{DESC_MAX})')

        # Canonical must exist and point at this page's own URL.
        if not page.canonical:
            rep.fail(rel, 'missing rel=canonical')
        else:
            want = expected_canonical(rel)
            if page.canonical.rstrip('/') != want.rstrip('/'):
                rep.fail(rel, f'canonical is {page.canonical!r}, expected {want!r}')

        # A page in the sitemap must not be noindex; checked in check_sitemap.
        robots = page.meta.get('robots', '')
        if 'noindex' in robots and 'nofollow' in robots:
            rep.warn(rel, 'noindex,nofollow — link equity dead-ends here')


# ── Internal links ────────────────────────────────────────────────────────────

def resolve(href):
    """Map a root-relative href to a path on disk, or None if not resolvable."""
    clean = href.split('#')[0].split('?')[0]
    if not clean or not clean.startswith('/'):
        return None
    target = ROOT / clean.lstrip('/')
    if clean.endswith('/'):
        return target / 'index.html'
    if target.suffix:
        return target
    return target / 'index.html'


def check_links(rep):
    for path, rel in iter_html():
        page = parse(path)
        for href in page.hrefs:
            if not href.startswith('/'):
                continue                      # external, relative, mailto:, #anchor
            resolved = resolve(href)
            if resolved is None:
                continue
            rep.checked += 1
            if not resolved.exists():
                # A bare extensionless path may legitimately be a file.
                alt = ROOT / href.split('#')[0].split('?')[0].lstrip('/')
                if not alt.exists():
                    rep.fail(rel, f'dead internal link {href!r}')


# ── JSON-LD ───────────────────────────────────────────────────────────────────

DATE_PROPS = ('datePublished', 'dateModified', 'dateCreated', 'guidelineDate')
ISO_DATE_RE = re.compile(r'\d{4}(-\d{2}(-\d{2})?)?$')

# A named entity whose name is CSV bookkeeping — one Person was published as
# "Not listed". Absence must be an omitted key, never a placeholder value.
PLACEHOLDER_NAME_RE = re.compile(
    r'^(not listed|not specified|not stated|not provided|unknown|none|n/?a)'
    r'(\s*\([^)]*\))?$',
    re.IGNORECASE)
NAMED_TYPES = ('Person', 'Organization')


def walk_nodes(obj):
    """Yield every dict that has an @type, at any nesting depth."""
    if isinstance(obj, dict):
        if '@type' in obj:
            yield obj
        for v in obj.values():
            yield from walk_nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_nodes(v)


def check_jsonld(rep):
    for path, rel in iter_html():
        page = parse(path)
        for i, raw in enumerate(page.jsonld_raw):
            rep.checked += 1
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                rep.fail(rel, f'ld+json block {i} is invalid JSON: {e}')
                continue

            for node in walk_nodes(data):
                types = node['@type']
                types = types if isinstance(types, list) else [types]

                # Every schema.org Date-valued property must be ISO-8601.
                # Raw CSV text used to flow into datePublished, shipping 443
                # invalid values ("Not listed", "August 2024", "09/2024").
                # Reduced precision (2024, 2024-08) is valid and intended.
                for key in DATE_PROPS:
                    val = node.get(key)
                    if val is not None and not ISO_DATE_RE.match(str(val)):
                        rep.fail(rel, f'{key} is not an ISO-8601 date: {str(val)[:40]!r}')

                if any(t in types for t in NAMED_TYPES):
                    name = str(node.get('name', ''))
                    if PLACEHOLDER_NAME_RE.match(name.strip()):
                        rep.fail(rel, f'{types[0]}.name is a placeholder: {name!r}')

                if 'MedicalWebPage' in types:
                    url = node.get('url', '')
                    if url and not url.startswith(SITE):
                        rep.fail(rel, f'MedicalWebPage.url points off-site: {url[:80]}')

                if 'BreadcrumbList' in types:
                    items = node.get('itemListElement', [])
                    positions = [it.get('position') for it in items if isinstance(it, dict)]
                    if positions != list(range(1, len(positions) + 1)):
                        rep.fail(rel, f'BreadcrumbList positions not contiguous from 1: {positions}')

                if 'ItemList' in types:
                    declared = node.get('numberOfItems')
                    actual = len(node.get('itemListElement', []))
                    if declared is not None and actual and declared != actual:
                        rep.fail(rel, f'ItemList numberOfItems={declared} but lists {actual}')


# ── Ledger ────────────────────────────────────────────────────────────────────

def check_ledger(rep):
    ledger_path = ROOT / 'protocol-slugs.csv'
    if not ledger_path.exists():
        rep.warn('protocol-slugs.csv', 'not present yet — skipping ledger checks')
        return

    with ledger_path.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    seen_pid = {}
    by_topic = defaultdict(set)
    retired = set()

    for i, r in enumerate(rows, start=2):
        rep.checked += 1
        pid = r.get('pid', '')
        topic = r.get('topic_slug', '')
        slug = r.get('slug', '')
        status = r.get('status', '')

        if not pid:
            rep.fail(f'ledger row {i}', 'empty pid')
            continue
        if pid in seen_pid:
            rep.fail(f'ledger row {i}', f'duplicate pid {pid} (first at row {seen_pid[pid]})')
        seen_pid[pid] = i

        key = f'{topic}/{slug}'
        if status == 'retired':
            retired.add(key)
        else:
            if slug in by_topic[topic]:
                rep.fail(f'ledger row {i}', f'duplicate slug within topic: {key}')
            by_topic[topic].add(slug)

    # An active slug must never reuse a retired one — that resurrects a dead URL
    # with different content.
    for topic, slugs in by_topic.items():
        for slug in slugs:
            if f'{topic}/{slug}' in retired:
                rep.fail('ledger', f'active slug collides with retired slug: {topic}/{slug}')

    # Ledger <-> CSV bijection, modulo retired.
    csv_path = ROOT / 'protocols-import.csv'
    if csv_path.exists():
        try:
            from rp_slugs import pid as make_pid
        except ImportError:
            rep.warn('ledger', 'rp_slugs not importable yet — skipping CSV/ledger bijection')
            return
        with csv_path.open(newline='', encoding='utf-8') as f:
            csv_pids = {
                make_pid(r.get('Protocol URL', ''), r.get('Surgery Type', ''))
                for r in csv.DictReader(f)
            }
        active = {p for p, i in seen_pid.items() if rows[i - 2].get('status') != 'retired'}
        missing = csv_pids - active
        extra = active - csv_pids
        if missing:
            rep.fail('ledger', f'{len(missing)} CSV rows have no active ledger entry')
        if extra:
            rep.fail('ledger', f'{len(extra)} active ledger entries have no CSV row (should be retired)')


# ── Sitemap ───────────────────────────────────────────────────────────────────

def check_sitemap(rep):
    sm = ROOT / 'sitemap.xml'
    if not sm.exists():
        rep.warn('sitemap.xml', 'not present')
        return

    text = sm.read_text(encoding='utf-8')
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
    except ET.ParseError as e:
        rep.fail('sitemap.xml', f'malformed XML: {e}')
        return

    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    locs = [e.text for e in root.findall('.//sm:loc', ns)] or \
           [e.text for e in root.findall('.//loc')]

    if len(locs) > 50000:
        rep.fail('sitemap.xml', f'{len(locs)} URLs exceeds the 50,000 limit — needs a sitemap index')

    seen = set()
    for loc in locs:
        rep.checked += 1
        if loc in seen:
            rep.fail('sitemap.xml', f'duplicate <loc>: {loc}')
        seen.add(loc)

        if not loc.startswith(SITE):
            rep.fail('sitemap.xml', f'<loc> not on {SITE}: {loc}')
            continue

        rel = loc[len(SITE):]
        resolved = resolve(rel or '/')
        if resolved is None or not resolved.exists():
            rep.fail('sitemap.xml', f'<loc> has no file on disk: {loc}')
            continue

        # A noindex page in the sitemap is a Search Console warning.
        page = parse(resolved)
        if 'noindex' in page.meta.get('robots', ''):
            rep.fail('sitemap.xml', f'lists a noindex page: {loc}')


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pages', action='store_true')
    ap.add_argument('--links', action='store_true')
    ap.add_argument('--jsonld', action='store_true')
    ap.add_argument('--ledger', action='store_true')
    ap.add_argument('--sitemap', action='store_true')
    args = ap.parse_args()

    selected = any([args.pages, args.links, args.jsonld, args.ledger, args.sitemap])
    run = lambda flag: (not selected) or flag

    ok = True
    if run(args.pages):
        r = Report(); check_pages(r);   ok &= r.summary('Page structure')
    if run(args.links):
        r = Report(); check_links(r);   ok &= r.summary('Internal links')
    if run(args.jsonld):
        r = Report(); check_jsonld(r);  ok &= r.summary('JSON-LD')
    if run(args.ledger):
        r = Report(); check_ledger(r);  ok &= r.summary('Slug ledger')
    if run(args.sitemap):
        r = Report(); check_sitemap(r); ok &= r.summary('Sitemap')

    print()
    if ok:
        print('  ALL CHECKS PASSED')
        return 0
    print('  VERIFICATION FAILED')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
