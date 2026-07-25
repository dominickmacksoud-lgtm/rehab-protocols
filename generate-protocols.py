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

    records, protocols = build(args)

    if args.emit_topics_skeleton:
        import rp_topics
        rp_topics.emit_skeleton(records)
        return 0

    write_protocols_js(protocols)
    sync_counts(protocols)

    if not args.skip_pages:
        # Imported lazily so --skip-pages stays usable if page generation is broken.
        import rp_pages
        rp_pages.generate(records, protocols, rekey=args.rekey)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
