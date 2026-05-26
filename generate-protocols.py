import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / 'protocols-import.csv'
OUT_PATH = ROOT / 'protocols.js'

EXPECTED_COLUMNS = {
    'Body Region', 'Body Region Display', 'Surgery Category', 'Surgery Type',
    'Source Organization', 'Surgeon(s) / Author(s)', 'Protocol URL',
    'Publication Date', 'Cataloged Date', 'WB Status', 'Key Restrictions',
    'Timeline / Phases', 'Notes',
}

if not CSV_PATH.exists():
    raise SystemExit(f"Missing file: {CSV_PATH}")

with CSV_PATH.open(newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames or [])
    records = list(reader)

if not records:
    raise SystemExit('CSV file contains no data rows.')


def normalize(value):
    return (value or '').strip()


# ── Validation ────────────────────────────────────────────────────────────────

def validate(records, fieldnames):
    errors = []
    warnings = []

    # Schema: all expected columns must be present
    missing_cols = EXPECTED_COLUMNS - set(fieldnames)
    if missing_cols:
        errors.append(f"CSV is missing expected columns: {', '.join(sorted(missing_cols))}")

    # url → (first_row, surgery_type) for duplicate detection
    seen_urls = {}

    for i, record in enumerate(records, start=2):
        row = f"Row {i}"
        url = normalize(record.get('Protocol URL'))
        surgery_type = normalize(record.get('Surgery Type'))

        # URL required
        if not url:
            errors.append(f"{row}: Missing Protocol URL")
        else:
            # URL must be a real web address
            if not url.startswith(('http://', 'https://')):
                errors.append(f"{row}: URL does not start with http:// or https:// — '{url[:80]}'")
            if url in seen_urls:
                first_row, first_type = seen_urls[url]
                if surgery_type == first_type:
                    # Same URL + same Surgery Type = true accidental duplicate
                    errors.append(
                        f"{row}: Duplicate protocol — same URL and Surgery Type as row {first_row} — '{url[:80]}'"
                    )
                else:
                    # Same URL, different Surgery Type = one PDF covering multiple approaches (intentional)
                    warnings.append(
                        f"{row}: Shares URL with row {first_row} but different Surgery Type — "
                        f"verify this is intentional (one PDF, multiple approaches)"
                    )
            else:
                seen_urls[url] = (i, surgery_type)

        # Without Surgery Category + Surgery Type the name becomes "Untitled Protocol"
        surgery_category = normalize(record.get('Surgery Category'))
        surgery_type = normalize(record.get('Surgery Type'))
        if not surgery_category and not surgery_type:
            warnings.append(
                f"{row}: Missing both Surgery Category and Surgery Type — "
                f"protocol name will be 'Untitled Protocol'"
            )

        # Source Organization powers the source-type badge and search
        source_org = normalize(record.get('Source Organization'))
        if not source_org:
            warnings.append(f"{row}: Missing Source Organization")

        # Body Region drives the category filter buttons
        body_region_display = normalize(record.get('Body Region Display'))
        body_region = normalize(record.get('Body Region'))
        if not body_region_display and not body_region:
            warnings.append(
                f"{row}: Missing Body Region and Body Region Display — "
                f"protocol will appear under 'Other'"
            )

    return errors, warnings


errors, warnings = validate(records, fieldnames)

if warnings:
    print(f"\n  {len(warnings)} warning(s):")
    for w in warnings:
        print(f"    {w}")

if errors:
    print(f"\n  {len(errors)} error(s) — generation aborted:")
    for e in errors:
        print(f"    {e}")
    raise SystemExit(1)

print(f"  Validation passed — {len(records)} rows, 0 errors, {len(warnings)} warning(s)")


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Build output ──────────────────────────────────────────────────────────────

protocols = []
for index, record in enumerate(records, start=2):
    url = normalize(record.get('Protocol URL'))
    category = normalize(record.get('Body Region Display')) or normalize(record.get('Body Region')) or 'Other'
    surgery_category = normalize(record.get('Surgery Category'))
    surgery_type = normalize(record.get('Surgery Type'))
    cleaned_type = dedupe_name(surgery_category, surgery_type)
    if surgery_category and cleaned_type:
        name = f"{surgery_category} — {cleaned_type}"
    else:
        name = surgery_category or surgery_type or 'Untitled Protocol'

    source_org = normalize(record.get('Source Organization'))
    wb_status = normalize(record.get('WB Status'))

    protocols.append({
        'url': url,
        'category': category,
        'name': name,
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
        'isPdf': url.lower().endswith('.pdf'),
    })

OUT_PATH.write_text(f'const protocols = {json.dumps(protocols, separators=(",", ":"))};\n', encoding='utf-8')
print(f"  Generated {len(protocols)} protocols -> {OUT_PATH.name}")

# Keep JSON-LD numberOfItems in sync with actual protocol count
INDEX_PATH = ROOT / 'index.html'
index_html = INDEX_PATH.read_text(encoding='utf-8')
updated_html = re.sub(r'"numberOfItems":\s*\d+', f'"numberOfItems": {len(protocols)}', index_html)
if updated_html != index_html:
    INDEX_PATH.write_text(updated_html, encoding='utf-8')
    print(f"  Updated numberOfItems -> {len(protocols)} in index.html")


# ── Per-protocol MedicalWebPage structured data ───────────────────────────────

def build_sd_item(p, record):
    item = {
        "@type": "MedicalWebPage",
        "name": p['name'],
        "url": p['url'],
        "inLanguage": "en-US",
        "audience": {"@type": "Audience", "audienceType": "Physical Therapists"},
    }
    surgery_category = normalize(record.get('Surgery Category'))
    if surgery_category:
        item["about"] = {"@type": "MedicalCondition", "name": surgery_category}
    if p['sourceOrganization']:
        item["publisher"] = {"@type": "Organization", "name": p['sourceOrganization']}
    surgeons = p['surgeons']
    if surgeons and 'clinical team' not in surgeons.lower():
        item["author"] = {"@type": "Person", "name": surgeons}
    if p['publicationDate']:
        item["datePublished"] = p['publicationDate']
    return item

graph = [build_sd_item(p, rec) for p, rec in zip(protocols, records)]
payload_json = json.dumps({"@context": "https://schema.org", "@graph": graph}, separators=(",", ":"), ensure_ascii=False)
SD_PATH = ROOT / 'structured-data.js'
SD_PATH.write_text(
    f'(function(){{var e=document.createElement("script");'
    f'e.type="application/ld+json";'
    f'e.text={json.dumps(payload_json)};'
    f'document.head.appendChild(e);}})();\n',
    encoding='utf-8',
)
print(f"  Generated structured-data.js ({len(graph)} MedicalWebPage items)")


# ── Auto-sync region counts on landing pages ──────────────────────────────────

from collections import Counter
region_counts = Counter(p['category'] for p in protocols)

LANDING_PAGES = {
    'Shoulder':   ROOT / 'shoulder'   / 'index.html',
    'Knee':       ROOT / 'knee'       / 'index.html',
    'Hip':        ROOT / 'hip'        / 'index.html',
    'Spine':      ROOT / 'spine'      / 'index.html',
    'Ankle/Foot': ROOT / 'ankle-foot' / 'index.html',
    'Elbow':      ROOT / 'elbow'      / 'index.html',
    'Wrist/Hand': ROOT / 'wrist-hand' / 'index.html',
}

for region, path in LANDING_PAGES.items():
    if not path.exists():
        continue
    count = region_counts.get(region, 0)
    html = path.read_text(encoding='utf-8')
    updated = re.sub(r'(<span id="region-count">)\d+(</span>)', rf'\g<1>{count}\2', html)
    if updated != html:
        path.write_text(updated, encoding='utf-8')
        print(f"  Updated region-count -> {count} in {path.parent.name}/index.html")

# Also sync homepage intro count
index_html2 = INDEX_PATH.read_text(encoding='utf-8')
updated_home = re.sub(r'(<span id="protocol-count">)\d+(</span>)', rf'\g<1>{len(protocols)}\2', index_html2)
if updated_home != index_html2:
    INDEX_PATH.write_text(updated_home, encoding='utf-8')
    print(f"  Updated protocol-count -> {len(protocols)} in index.html")

# Sync about page protocol count
ABOUT_PATH = ROOT / 'about' / 'index.html'
about_html = ABOUT_PATH.read_text(encoding='utf-8')
updated_about = re.sub(r'(<span class="stat-number" id="about-protocol-count">)\d+(</span>)', rf'\g<1>{len(protocols)}\2', about_html)
if updated_about != about_html:
    ABOUT_PATH.write_text(updated_about, encoding='utf-8')
    print(f"  Updated about-protocol-count -> {len(protocols)} in about/index.html")
