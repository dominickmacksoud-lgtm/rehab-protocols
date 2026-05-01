import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / 'protocols-import.csv'
OUT_PATH = ROOT / 'protocols.js'

if not CSV_PATH.exists():
    raise SystemExit(f"Missing file: {CSV_PATH}")

with CSV_PATH.open(newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    records = list(reader)

if not records:
    raise SystemExit('CSV file contains no data rows.')


def infer_type(record):
    surgery_type = (record.get('Surgery Type') or '').lower()
    surgery_category = (record.get('Surgery Category') or '').lower()
    if any(k in surgery_type for k in ['non-op', 'non op', 'nonoperative', 'non-operative']) or \
       any(k in surgery_category for k in ['non-op', 'non op', 'nonoperative', 'non-operative']):
        return 'nonop'
    if any(k in surgery_type for k in ['educat', 'patient', 'home']) or \
       any(k in surgery_category for k in ['educat', 'patient', 'home']):
        return 'education'
    if any(k in surgery_category for k in ['service', 'clinic', 'practice', 'team', 'provider']):
        return 'service'
    return 'postop'


def normalize(value):
    return (value or '').strip()


def dedupe_name(category, surgery_type):
    """Strip redundant category prefix from surgery_type before combining."""
    if not surgery_type or not category:
        return surgery_type
    if surgery_type.lower().startswith(category.lower()):
        remainder = surgery_type[len(category):].strip().lstrip('—–- :').strip()
        return remainder if remainder else None  # None = identical, just show category
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


protocols = []
for index, record in enumerate(records, start=2):
    url = normalize(record.get('Protocol URL'))
    if not url:
        raise SystemExit(f'Missing Protocol URL at CSV row {index}')

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
    pub_date = normalize(record.get('Publication Date'))
    surgeons = normalize(record.get('Surgeon(s) / Author(s)'))
    key_restrictions = normalize(record.get('Key Restrictions'))
    timeline_phases = normalize(record.get('Timeline / Phases'))
    additional_notes = normalize(record.get('Notes'))

    protocols.append({
        'url': url,
        'category': category,
        'name': name,
        'type': infer_type(record),
        'sourceOrganization': source_org,
        'sourceType': classify_source(url, source_org),
        'surgeons': surgeons,
        'publicationDate': pub_date,
        'wbStatus': wb_status,
        'wbInitial': extract_wb_initial(wb_status),
        'keyRestrictions': key_restrictions,
        'timelinePhases': timeline_phases,
        'notes': additional_notes,
        'isPdf': url.lower().endswith('.pdf'),
    })

OUT_PATH.write_text(f'const protocols = {json.dumps(protocols, indent=2)};\n', encoding='utf-8')
print(f'Generated {len(protocols)} protocols into {OUT_PATH}')
