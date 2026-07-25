"""Topic taxonomy — maps raw CSV categories onto curated hub topics.

The CSV has 185 distinct Surgery Category values, but many are catch-all buckets
("Non-Operative", "Surgical", "Knee") that describe nothing a person would search
for, and several are spelling variants of each other ("Meniscus Repair" vs
"Meniscal Repair"). topics.csv is the hand-curated mapping that turns those into
hub pages worth ranking.

topics.csv columns:
    topic_slug     URL segment, e.g. acl-reconstruction
    display_name   "ACL Reconstruction"
    h1             page heading; blank -> "{display_name} Rehabilitation Protocols"
    region         Body Region Display for breadcrumbs; blank -> inferred majority
    status         hub | noindex | merge:<slug> | exclude
    aliases        |-separated raw strings that map here
    intro          optional hand-written paragraph; blank -> synthesized

status values:
    hub       indexable hub page
    noindex   rendered and crawlable but noindex,follow — for thin topics
    merge:X   alias-only; rows resolve to topic X
    exclude   never a topic; rows fall through to their Surgery Type
"""

import csv
import re
from collections import Counter, defaultdict

from rp_data import ROOT, normalize, write_text

TOPICS_PATH = ROOT / 'topics.csv'

TOPIC_COLUMNS = ['topic_slug', 'display_name', 'h1', 'region', 'status', 'aliases', 'intro']

# Catch-all buckets that must never become hub pages. Rows carrying these fall
# through to their Surgery Type, which is where the real topic lives.
# Compared against norm_key() output, which folds hyphens to spaces — so these
# must be written in normalized form ("non operative", not "non-operative").
DEFAULT_EXCLUDE = {'non operative', 'surgical', 'knee', 'other', 'general'}

# Minimum protocols for an indexable hub. Below this, the hub still renders and
# still passes link equity to its protocol pages, but is noindex so ~180 thin
# pages don't bloat the index.
HUB_MIN = 3


def norm_key(text):
    """Normalized alias key: case/punctuation-insensitive."""
    s = (text or '').lower().strip()
    s = s.replace('—', ' ').replace('–', ' ').replace('/', ' ')
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def derived_type(record):
    """Surgery Type reduced to its head clause.

    'ACL Reconstruction — Quad Tendon Autograft (Adult)' -> 'ACL Reconstruction'
    Used when Surgery Category is a junk bucket.
    """
    t = normalize(record.get('Surgery Type'))
    if not t:
        return ''
    t = re.split(r'[—–]', t)[0]
    t = re.sub(r'\([^)]*\)', '', t)
    t = re.split(r'\bwith\b|\bw/\b|\+', t, flags=re.I)[0]
    return re.sub(r'\s+', ' ', t).strip(' -:/')


def load_topics(path=TOPICS_PATH):
    """Return (by_slug, alias_index). Empty when topics.csv is absent."""
    if not path.exists():
        return {}, {}
    with path.open(newline='', encoding='utf-8') as f:
        rows = [dict(r) for r in csv.DictReader(f)]

    by_slug = {}
    alias_index = {}
    for r in rows:
        slug = normalize(r.get('topic_slug'))
        if not slug:
            continue
        r['status'] = normalize(r.get('status')) or 'hub'
        by_slug[slug] = r
        keys = {norm_key(slug), norm_key(r.get('display_name'))}
        for a in (r.get('aliases') or '').split('|'):
            if a.strip():
                keys.add(norm_key(a))
        for k in filter(None, keys):
            alias_index.setdefault(k, slug)
    return by_slug, alias_index


def resolve_topic(record, by_slug, alias_index):
    """Map one record to a topic slug.

    Order: Surgery Category -> (if excluded/unknown) derived Surgery Type ->
    raw Surgery Type -> auto-create from derived type.
    """
    from rp_slugs import slugify

    candidates = [
        normalize(record.get('Surgery Category')),
        derived_type(record),
        normalize(record.get('Surgery Type')),
    ]

    for cand in candidates:
        if not cand:
            continue
        key = norm_key(cand)

        # Junk buckets are rejected BEFORE the alias lookup. If a catch-all name
        # ever leaks into some topic's alias list, checking aliases first would
        # funnel every row carrying that category into one nonsense hub.
        if key in DEFAULT_EXCLUDE:
            continue

        slug = alias_index.get(key)
        if slug:
            entry = by_slug.get(slug, {})
            status = entry.get('status', 'hub')
            if status.startswith('merge:'):
                return status.split(':', 1)[1]
            if status == 'exclude':
                continue          # fall through to the next candidate
            return slug

        # Unknown but usable — auto-create.
        return slugify(cand)

    # Everything was excluded or empty; last resort keeps the row addressable.
    return slugify(normalize(record.get('Body Region Display')) or 'other')


def assign_topics(records, by_slug=None, alias_index=None):
    """Return (topic_of, topic_members, warnings)."""
    if by_slug is None or alias_index is None:
        by_slug, alias_index = load_topics()

    topic_of = {}
    members = defaultdict(list)
    for i, r in enumerate(records):
        slug = resolve_topic(r, by_slug, alias_index)
        topic_of[i] = slug
        members[slug].append(i)

    warnings = []
    for slug, idxs in sorted(members.items()):
        if slug not in by_slug and len(idxs) >= HUB_MIN:
            warnings.append(
                f"topic '{slug}' ({len(idxs)} protocols) is auto-created — "
                f'add it to topics.csv to give it a curated name and intro'
            )
    return topic_of, members, warnings


def topic_meta(slug, by_slug, records, idxs):
    """Resolve display name, h1, region, and indexability for one topic."""
    entry = by_slug.get(slug, {})

    display = normalize(entry.get('display_name'))
    if not display:
        cats = Counter(
            normalize(records[i].get('Surgery Category')) or derived_type(records[i])
            for i in idxs
        )
        cats.pop('', None)
        display = cats.most_common(1)[0][0] if cats else slug.replace('-', ' ').title()

    h1 = normalize(entry.get('h1')) or f'{display} Rehabilitation Protocols'

    region = normalize(entry.get('region'))
    if not region:
        regions = Counter(
            normalize(records[i].get('Body Region Display')) for i in idxs
        )
        regions.pop('', None)
        region = regions.most_common(1)[0][0] if regions else ''

    status = entry.get('status', 'hub')
    indexable = status == 'hub' and len(idxs) >= HUB_MIN

    return {
        'slug': slug,
        'display': display,
        'h1': h1,
        'region': region,
        'intro': normalize(entry.get('intro')),
        'indexable': indexable,
        'count': len(idxs),
    }


def emit_skeleton(records):
    """Print a draft topics.csv for curation, sorted by protocol count."""
    by_slug, alias_index = load_topics()
    topic_of, members, _ = assign_topics(records, by_slug, alias_index)

    rows = []
    for slug, idxs in sorted(members.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        meta = topic_meta(slug, by_slug, records, idxs)
        existing = by_slug.get(slug, {})
        raw = Counter(normalize(records[i].get('Surgery Category')) for i in idxs)
        raw.pop('', None)
        # Never record a catch-all bucket as an alias. Doing so would make every
        # row carrying that category resolve to whichever topic listed it first.
        raw = {k: v for k, v in raw.items() if norm_key(k) not in DEFAULT_EXCLUDE}
        rows.append({
            'topic_slug': slug,
            'display_name': meta['display'],
            'h1': normalize(existing.get('h1')),
            'region': meta['region'],
            'status': existing.get('status') or ('hub' if len(idxs) >= HUB_MIN else 'noindex'),
            'aliases': '|'.join(sorted(k for k in raw if k)),
            'intro': normalize(existing.get('intro')),
        })

    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TOPIC_COLUMNS, lineterminator='\n')
    w.writeheader()
    for r in rows:
        w.writerow(r)
    print(buf.getvalue())
    print(f'  {len(rows)} topics; '
          f"{sum(1 for r in rows if r['status'] == 'hub')} would be indexable hubs",
          flush=True)
