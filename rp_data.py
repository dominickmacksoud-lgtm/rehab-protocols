"""Shared CSV loading, validation, and field-derivation for the protocol pipeline.

Extracted from generate-protocols.py so the page/slug/sitemap generators can
reuse the exact same derivations. The protocol record shape produced by
build_protocols() is what ends up in protocols.js, so changing it changes the
site's client-side data — do that deliberately.

Module name note: never name a module or top-level directory after an importable
package. This repo already shadows `requests` via requests/index.html (see
CLAUDE.md), so everything here takes the rp_ prefix.
"""

import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / 'protocols-import.csv'

EXPECTED_COLUMNS = {
    'Body Region', 'Body Region Display', 'Surgery Category', 'Surgery Type',
    'Source Organization', 'Surgeon(s) / Author(s)', 'Protocol URL',
    'Publication Date', 'Cataloged Date', 'WB Status', 'Key Restrictions',
    'Timeline / Phases', 'Notes',
}

LANDING_PAGES = {
    'Shoulder':   ROOT / 'shoulder'   / 'index.html',
    'Knee':       ROOT / 'knee'       / 'index.html',
    'Hip':        ROOT / 'hip'        / 'index.html',
    'Spine':      ROOT / 'spine'      / 'index.html',
    'Ankle/Foot': ROOT / 'ankle-foot' / 'index.html',
    'Elbow':      ROOT / 'elbow'      / 'index.html',
    'Wrist/Hand': ROOT / 'wrist-hand' / 'index.html',
}

# Region -> URL path for the landing page, used for internal links and JSON-LD.
REGION_PATHS = {
    'Shoulder':   '/shoulder/',
    'Knee':       '/knee/',
    'Hip':        '/hip/',
    'Spine':      '/spine/',
    'Ankle/Foot': '/ankle-foot/',
    'Elbow':      '/elbow/',
    'Wrist/Hand': '/wrist-hand/',
}

# Regions intentionally without a landing page — reachable via the homepage
# 'Other' category button. A region in neither list gets a warning.
NO_LANDING_PAGE = {'Leg', 'Multiple', 'Head'}


def setup_console():
    """Make stdout UTF-8 safe.

    Warnings print Surgery Types containing em-dashes. On a cp1252 console that
    raises UnicodeEncodeError *after* files are written — the worst failure mode
    available here, since it aborts mid-run with the repo half-updated.
    """
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def normalize(value):
    return (value or '').strip()


def load_records(path=CSV_PATH):
    if not path.exists():
        raise SystemExit(f'Missing file: {path}')
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        records = list(reader)
    if not records:
        raise SystemExit('CSV file contains no data rows.')
    return records, fieldnames


# ── Validation ────────────────────────────────────────────────────────────────

def validate(records, fieldnames):
    """Return (errors, warnings).

    (Protocol URL, Surgery Type) is the primary key the slug ledger is built on,
    so its uniqueness is a hard error checked against *every* prior row. The
    previous implementation stored only the first row's surgery type per URL, so
    the sequence X/T1, X/T2, X/T2 compared row 3 against T1, failed to match, and
    passed as a warning — letting a true duplicate through into the ledger.
    """
    errors = []
    warnings = []

    missing_cols = EXPECTED_COLUMNS - set(fieldnames)
    if missing_cols:
        errors.append(f"CSV is missing expected columns: {', '.join(sorted(missing_cols))}")

    seen_pairs = {}   # (url, surgery_type) -> first row   — hard uniqueness
    seen_urls = {}    # url -> first row                   — shared-PDF warning

    for i, record in enumerate(records, start=2):
        row = f'Row {i}'
        url = normalize(record.get('Protocol URL'))
        surgery_type = normalize(record.get('Surgery Type'))

        if not url:
            errors.append(f'{row}: Missing Protocol URL')
        else:
            if not url.startswith(('http://', 'https://')):
                errors.append(f"{row}: URL does not start with http:// or https:// — '{url[:80]}'")

            pair = (url, surgery_type)
            if pair in seen_pairs:
                errors.append(
                    f'{row}: Duplicate protocol — same URL and Surgery Type as '
                    f"row {seen_pairs[pair]} — '{url[:80]}'"
                )
            else:
                seen_pairs[pair] = i
                # Same URL, different Surgery Type = one PDF covering multiple
                # approaches. Intentional; CLAUDE.md documents MGH ACL and Lahey THA.
                if url in seen_urls:
                    warnings.append(
                        f'{row}: Shares URL with row {seen_urls[url]} but different '
                        f'Surgery Type — verify this is intentional (one PDF, multiple approaches)'
                    )
                else:
                    seen_urls[url] = i

        surgery_category = normalize(record.get('Surgery Category'))
        if not surgery_category and not surgery_type:
            warnings.append(
                f"{row}: Missing both Surgery Category and Surgery Type — "
                f"protocol name will be 'Untitled Protocol'"
            )

        if not normalize(record.get('Source Organization')):
            warnings.append(f'{row}: Missing Source Organization')

        if not normalize(record.get('Body Region Display')) and not normalize(record.get('Body Region')):
            warnings.append(
                f"{row}: Missing Body Region and Body Region Display — "
                f"protocol will appear under 'Other'"
            )

    return errors, warnings


# ── Field derivation ──────────────────────────────────────────────────────────

def infer_type(record):
    surgery_type = (record.get('Surgery Type') or '').lower()
    surgery_category = (record.get('Surgery Category') or '').lower()
    if any(k in surgery_type for k in ['non-op', 'non op', 'nonoperative', 'non-operative']) or \
       any(k in surgery_category for k in ['non-op', 'non op', 'nonoperative', 'non-operative']):
        return 'nonop'
    if any(k in surgery_type for k in ['educat', 'patient', 'home']) or \
       any(k in surgery_category for k in ['educat', 'patient', 'home']):
        return 'education'
    return 'postop'


def dedupe_name(category, surgery_type):
    """Strip a redundant category prefix off the surgery type.

    'ACL Reconstruction' + 'ACL Reconstruction — BPTB Autograft' -> 'BPTB Autograft'
    Also used to build the protocol-page slug so URLs don't stutter.
    """
    if not surgery_type or not category:
        return surgery_type
    if surgery_type.lower().startswith(category.lower()):
        remainder = surgery_type[len(category):].strip().lstrip('—–- :').strip()
        return remainder if remainder else None
    return surgery_type


def extract_wb_initial(wb_text):
    if not wb_text:
        return ''
    text = wb_text.upper()
    positions = {}
    for status in ['NWB', 'TDWB', 'PWB', 'WBAT', 'FWB']:
        idx = text.find(status)
        if idx >= 0:
            positions[status] = idx
    if not positions:
        return ''
    return min(positions, key=positions.get)


def classify_source(url, source_org):
    url_lower = (url or '').lower()
    org_lower = (source_org or '').lower()
    if '.edu' in url_lower or any(x in org_lower for x in ['university', 'college']):
        return 'academic'
    if any(x in org_lower for x in ['hospital', 'medical center', 'health system', 'health']):
        return 'hospital'
    if any(x in org_lower for x in [' md', ' do', 'dr. ', 'dr ']):
        return 'surgeon'
    return 'clinic'


def protocol_name(record):
    surgery_category = normalize(record.get('Surgery Category'))
    surgery_type = normalize(record.get('Surgery Type'))
    cleaned_type = dedupe_name(surgery_category, surgery_type)
    if surgery_category and cleaned_type:
        return f'{surgery_category} — {cleaned_type}'
    return surgery_category or surgery_type or 'Untitled Protocol'


def build_protocols(records):
    """Build the record list that becomes protocols.js.

    Field order and content must stay stable — protocols.js is consumed by
    index.html's search/filter/modal code.
    """
    protocols = []
    for record in records:
        url = normalize(record.get('Protocol URL'))
        category = (normalize(record.get('Body Region Display'))
                    or normalize(record.get('Body Region')) or 'Other')
        source_org = normalize(record.get('Source Organization'))
        wb_status = normalize(record.get('WB Status'))

        protocols.append({
            'url': url,
            'category': category,
            'name': protocol_name(record),
            'type': infer_type(record),
            'sourceOrganization': source_org,
            'sourceType': classify_source(url, source_org),
            'surgeons': normalize(record.get('Surgeon(s) / Author(s)')),
            'publicationDate': normalize(record.get('Publication Date')),
            'wbStatus': wb_status,
            'wbInitial': extract_wb_initial(wb_status),
            'keyRestrictions': normalize(record.get('Key Restrictions')),
            'timelinePhases': normalize(record.get('Timeline / Phases')),
            'notes': normalize(record.get('Notes')),
            'isPdf': url.lower().split('?')[0].endswith('.pdf'),
        })
    return protocols


def region_counts(protocols):
    return Counter(p['category'] for p in protocols)


# ── HTML patching ─────────────────────────────────────────────────────────────

def sync_count(path, pattern, replacement, label):
    """Patch a count in an HTML file; warn loudly if the pattern stops matching."""
    html = path.read_text(encoding='utf-8')
    updated, n = re.subn(pattern, replacement, html)
    if n == 0:
        print(f'  WARNING: {label}: pattern matched nothing in {path.relative_to(ROOT)} — count NOT synced')
    elif updated != html:
        write_text(path, updated)
        print(f'  Updated {label} in {path.relative_to(ROOT)}')


SENTINEL = '<!-- RP:{name}:START -->'
SENTINEL_END = '<!-- RP:{name}:END -->'


def splice(path, name, payload, label=None):
    """Replace content between <!-- RP:NAME:START --> and <!-- RP:NAME:END -->.

    Uses a callable replacement because re.sub interprets backslash escapes
    (\\g<1>, \\1, \\\\) inside *string* replacements — generated HTML containing a
    backslash would silently corrupt the page. sync_count() above is safe only
    because its replacements are literal digits.

    Returns True if the file changed.
    """
    label = label or name
    start = SENTINEL.format(name=name)
    end = SENTINEL_END.format(name=name)
    html = path.read_text(encoding='utf-8')

    pattern = re.compile(
        f'({re.escape(start)})(.*?)({re.escape(end)})',
        re.DOTALL,
    )
    if not pattern.search(html):
        print(f'  WARNING: sentinel {name} not found in {path.relative_to(ROOT)} — NOT spliced')
        return False

    updated = pattern.sub(lambda m: m.group(1) + payload + m.group(3), html)
    if updated != html:
        write_text(path, updated)
        print(f'  Spliced {label} into {path.relative_to(ROOT)}')
        return True
    return False


def write_text(path, text):
    """Write UTF-8 with LF endings, creating parents. Idempotent: skips no-op writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            if path.read_text(encoding='utf-8') == text:
                return False
        except UnicodeDecodeError:
            pass
    with path.open('w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return True
