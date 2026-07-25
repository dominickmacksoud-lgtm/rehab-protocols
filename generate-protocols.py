"""Generate protocols.js and the static protocol pages from protocols-import.csv.

This is the single command to run after editing protocols-import.csv:

    python generate-protocols.py

Flags:
    --emit-topics-skeleton   print a draft topics.csv to stdout and exit
    --skip-pages             regenerate protocols.js only (fast; skips protocols/)
    --rekey OLD=NEW          carry a slug across a changed primary key (see rp_slugs)

Everything it writes is derived output — protocols.js, protocols/**, sitemap.xml,
and the counts patched into existing HTML. protocol-slugs.csv is the URL contract
and is append-mostly: never hand-edit it.
"""

import argparse
import json

import rp_data
from rp_data import ROOT

OUT_PATH = ROOT / 'protocols.js'


def build(args):
    records, fieldnames = rp_data.load_records()

    errors, warnings = rp_data.validate(records, fieldnames)

    if warnings:
        print(f'\n  {len(warnings)} warning(s):')
        for w in warnings:
            print(f'    {w}')

    if errors:
        print(f'\n  {len(errors)} error(s) — generation aborted:')
        for e in errors:
            print(f'    {e}')
        raise SystemExit(1)

    print(f'  Validation passed — {len(records)} rows, 0 errors, {len(warnings)} warning(s)')

    protocols = rp_data.build_protocols(records)
    return records, protocols


def write_protocols_js(protocols):
    payload = json.dumps(protocols, separators=(',', ':'))
    rp_data.write_text(OUT_PATH, f'const protocols = {payload};\n')
    print(f'  Generated {len(protocols)} protocols -> {OUT_PATH.name}')


def sync_home_jsonld(protocols):
    """Emit the homepage WebSite + CollectionPage block.

    Replaces markup that declared numberOfItems: 887 while listing 7 items, each
    pointing at a `?category=` URL that nothing on the page parsed. The list now
    points at the real region landing pages and its count is derived, so the two
    cannot disagree.
    """
    import rp_templates as T

    counts = rp_data.region_counts(protocols)
    entries = [
        (f'{region} Rehabilitation Protocols ({counts.get(region, 0)})', path)
        for region, path in rp_data.REGION_PATHS.items()
    ]
    collection = {
        '@type': 'CollectionPage',
        'name': 'Rehab Protocols — Post-Op & Rehabilitation Protocol Library',
        'url': f'{T.SITE}/',
        'description': ('A library of post-op and non-operative rehabilitation protocols '
                        'from academic medical centers, hospitals, and orthopedic surgeons.'),
        'inLanguage': 'en-US',
        'audience': {'@type': 'Audience',
                     'audienceType': 'Licensed Physical Therapists and PT Students'},
        'publisher': {'@id': T.ORG_ID},
        'mainEntity': T.item_list(entries, name='Protocols by body region'),
    }
    block = (f'<script type="application/ld+json">'
             f'{T.escj(T.graph(T.organization(), T.website(), collection))}</script>')
    rp_data.splice(ROOT / 'index.html', 'HOME-JSONLD', block, label='homepage JSON-LD')


def sync_counts(protocols):
    """Patch hardcoded counts in the hand-maintained HTML pages."""
    total = len(protocols)
    index_path = ROOT / 'index.html'

    rp_data.sync_count(
        index_path, r'(<span id="protocol-count">)\d+(</span>)',
        rf'\g<1>{total}\2', f'protocol-count -> {total}')
    rp_data.sync_count(
        ROOT / 'about' / 'index.html',
        r'(<span class="stat-number" id="about-protocol-count">)\d+(</span>)',
        rf'\g<1>{total}\2', f'about-protocol-count -> {total}')

    counts = rp_data.region_counts(protocols)

    for region in sorted(counts):
        if region not in rp_data.LANDING_PAGES and region not in rp_data.NO_LANDING_PAGE:
            print(f"  WARNING: region '{region}' ({counts[region]} protocols) is not in "
                  f'LANDING_PAGES or NO_LANDING_PAGE — check Body Region Display for typos')

    for region, path in rp_data.LANDING_PAGES.items():
        if not path.exists():
            print(f"  WARNING: landing page for '{region}' missing at "
                  f'{path.relative_to(ROOT)} — counts NOT synced')
            continue
        count = counts.get(region, 0)
        rp_data.sync_count(path, r'(<span id="region-count">)\d+(</span>)',
                           rf'\g<1>{count}\2', f'region-count -> {count}')
        rp_data.sync_count(path, r'(<meta name="description" content="Browse )\d+',
                           rf'\g<1>{count}', f'meta description count -> {count}')


def main():
    rp_data.setup_console()

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--emit-topics-skeleton', action='store_true',
                    help='print a draft topics.csv and exit')
    ap.add_argument('--skip-pages', action='store_true',
                    help='regenerate protocols.js only')
    ap.add_argument('--rekey', action='append', default=[], metavar='OLD=NEW',
                    help='carry a ledger slug across a changed primary key')
    args = ap.parse_args()

    records, _ = build(args)

    if args.emit_topics_skeleton:
        import rp_topics
        rp_topics.emit_skeleton(records)
        return 0

    if args.skip_pages:
        protocols = rp_data.build_protocols(records)
        write_protocols_js(protocols)
        sync_counts(protocols)
        sync_home_jsonld(protocols)
        return 0

    # Resolve slugs first so protocols.js can carry each protocol's page path
    # from the same resolution the static pages use.
    import rp_pages
    import rp_sitemap

    resolved = rp_pages.resolve(records, rekey=args.rekey)
    protocols = rp_data.build_protocols(records, paths=resolved['paths'])

    write_protocols_js(protocols)
    sync_counts(protocols)
    sync_home_jsonld(protocols)

    rp_pages.generate(records, protocols, resolved=resolved)
    rp_sitemap.generate(ledger=resolved['ledger'])

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
