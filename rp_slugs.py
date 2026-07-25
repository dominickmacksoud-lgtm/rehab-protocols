"""URL slugs and the slug ledger — the site's URL contract.

Every protocol page URL is pinned in protocol-slugs.csv and, once allocated,
never changes. This module owns that guarantee.

Why it matters: protocols-import.csv is hand-edited and periodically re-sorted.
If a slug were derived from row position, inserting one row near the top would
shift the index of every row below it and change hundreds of URLs at once —
mass 404s and total loss of accumulated rankings and backlinks from a one-line
CSV edit. Row order therefore never enters the slug pipeline, not even as a
tiebreak. Identity comes from content: sha1(Protocol URL + Surgery Type).
"""

import csv
import hashlib
import re
import unicodedata
from datetime import date
from pathlib import Path

from rp_data import ROOT, normalize

LEDGER_PATH = ROOT / 'protocol-slugs.csv'

LEDGER_COLUMNS = [
    'pid', 'topic_slug', 'slug', 'status', 'first_seen',
    'content_sha', 'last_changed', 'source_url', 'surgery_type',
]

# Reserved device names on Windows. A directory named CON/ or PRN/ cannot be
# created, which would break generation on the maintainer's own machine.
WIN_RESERVED = (
    {'CON', 'PRN', 'AUX', 'NUL'}
    | {f'COM{i}' for i in range(1, 10)}
    | {f'LPT{i}' for i in range(1, 10)}
)

MAX_TOPIC_SEG = 60
MAX_SLUG_SEG = 70


def slugify(text, maxlen=MAX_TOPIC_SEG):
    """Lowercase ASCII slug, cut on a word boundary.

    Character handling is driven by what actually appears in the CSV:
    337 slashes, 142 em-dashes, 516 paren pairs, 40 ampersands.
    """
    s = unicodedata.normalize('NFKD', text or '')

    # Dashes to space before the alnum pass, so "A — B" reads "a-b" not "a---b".
    s = s.replace('—', ' ').replace('–', ' ')
    s = s.replace('≤', ' lte ').replace('≥', ' gte ')

    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.encode('ascii', 'ignore').decode('ascii')
    s = s.lower()

    s = s.replace('&', ' and ').replace('+', ' plus ')
    # Slash to space, NOT hyphen: "Ankle/Foot" must become "ankle-foot" to match
    # the existing /ankle-foot/ directory.
    s = s.replace('/', ' ')
    # Strip apostrophes before the alnum pass: "Sever's" -> "severs", not "sever-s".
    s = re.sub(r"['’ʼ]", '', s)

    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')

    if len(s) > maxlen:
        cut = s[:maxlen]
        # Never truncate mid-word; fall back to a hard cut if there's no hyphen.
        s = cut.rsplit('-', 1)[0].strip('-') or cut.strip('-')

    if s.upper() in WIN_RESERVED or s.upper().split('.')[0] in WIN_RESERVED:
        s = f'{s}-x'

    return s or 'protocol'


def pid(url, surgery_type):
    """Stable content-derived identity for one protocol row.

    (Protocol URL, Surgery Type) is a verified primary key across all 887 rows.
    Independent of row order, so re-sorting the CSV cannot move any URL.
    """
    key = f'{normalize(url)}\x1f{normalize(surgery_type)}'
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]


def content_sha(record):
    """Hash of the fields that get rendered, so sitemap lastmod is honest.

    Bumped only when the visible content of the page actually changes — not on
    every run, and not when unrelated CSV columns are touched.
    """
    fields = [
        'Surgery Category', 'Surgery Type', 'Source Organization',
        'Surgeon(s) / Author(s)', 'Publication Date', 'WB Status',
        'Key Restrictions', 'Timeline / Phases', 'Notes',
        'Body Region Display', 'Protocol URL',
    ]
    blob = '\x1f'.join(normalize(record.get(f)) for f in fields)
    return hashlib.sha1(blob.encode('utf-8')).hexdigest()[:12]


def surname(surgeons):
    """First surgeon's surname, for readable collision tiebreaks."""
    if not surgeons:
        return ''
    first = re.split(r'[;,(]', surgeons)[0].strip()
    first = re.sub(r'\b(Dr|MD|DO|PT|DPT|PhD|OCS|SCS|ATC|MS|MPT)\b\.?', '', first, flags=re.I)
    parts = [p for p in re.split(r'\s+', first.strip()) if p]
    return parts[-1] if parts else ''


# ── Ledger ────────────────────────────────────────────────────────────────────

def load_ledger(path=LEDGER_PATH):
    if not path.exists():
        return {}
    with path.open(newline='', encoding='utf-8') as f:
        return {r['pid']: dict(r) for r in csv.DictReader(f)}


def write_ledger(entries, path=LEDGER_PATH):
    """Write sorted by (topic_slug, slug) so diffs stay readable and stable."""
    rows = sorted(entries.values(), key=lambda r: (r['topic_slug'], r['slug'], r['pid']))
    lines = [','.join(LEDGER_COLUMNS)]
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=LEDGER_COLUMNS, lineterminator='\n')
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, '') for c in LEDGER_COLUMNS})

    from rp_data import write_text
    return write_text(path, buf.getvalue())


def base_slug(record, topic_slug):
    """org, or org-variant when the surgery type adds information beyond the topic."""
    org = slugify(normalize(record.get('Source Organization')), 40)
    variant_src = _dedupe(record)
    variant = slugify(variant_src, 40) if variant_src else ''

    # Drop a variant that merely restates the topic (e.g. topic acl-reconstruction,
    # variant acl-reconstruction) so URLs don't stutter.
    if variant and variant == topic_slug:
        variant = ''

    if not org:
        org = 'protocol'
    combined = f'{org}-{variant}' if variant else org
    return slugify(combined, MAX_SLUG_SEG)


def _dedupe(record):
    from rp_data import dedupe_name
    return dedupe_name(
        normalize(record.get('Surgery Category')),
        normalize(record.get('Surgery Type')),
    )


def _with_suffix(base, suffix, maxlen=MAX_SLUG_SEG):
    """Append a disambiguator, trimming the base to make room for it.

    Re-slugifying f'{base}-{suffix}' at the same cap would truncate the suffix
    straight back off whenever base is already near the limit, returning a string
    equal to base — so the "disambiguated" slug still collides.
    """
    suffix = slugify(suffix, 20)
    if not suffix:
        return base
    room = maxlen - len(suffix) - 1
    if room <= 0:
        return suffix[:maxlen]
    trimmed = base[:room]
    # Prefer a word boundary, but never return empty.
    trimmed = trimmed.rsplit('-', 1)[0].strip('-') or base[:room].strip('-')
    return f'{trimmed}-{suffix}' if trimmed else suffix


def allocate(records, topic_of, ledger=None, rekey=None, today=None):
    """Assign a (topic_slug, slug) to every record, reusing pinned values.

    topic_of: callable(record) -> topic_slug
    rekey:    list of "OLDPID=NEWPID" to carry a slug across a changed key
    Returns (entries, assignments, report).
    """
    ledger = dict(ledger if ledger is not None else load_ledger())
    today = today or date.today().isoformat()

    for mapping in (rekey or []):
        old, _, new = mapping.partition('=')
        if old in ledger and new:
            entry = ledger.pop(old)
            entry['pid'] = new
            ledger[new] = entry

    report = {'new': [], 'retired': [], 'moved': [], 'changed': []}
    assignments = {}
    taken = set()

    # Slugs already pinned stay pinned, and their names are reserved before any
    # new allocation runs so a newcomer can never steal an existing URL.
    for entry in ledger.values():
        taken.add((entry['topic_slug'], entry['slug']))

    pending = []
    for record in records:
        p = pid(record.get('Protocol URL'), record.get('Surgery Type'))
        topic = topic_of(record)
        sha = content_sha(record)

        entry = ledger.get(p)
        if entry and entry.get('status') != 'retired':
            if entry['topic_slug'] != topic:
                report['moved'].append((p, entry['topic_slug'], topic))
            if entry.get('content_sha') != sha:
                entry['content_sha'] = sha
                entry['last_changed'] = today
                report['changed'].append(p)
            entry['status'] = 'active'
            entry['source_url'] = normalize(record.get('Protocol URL'))
            entry['surgery_type'] = normalize(record.get('Surgery Type'))
            assignments[p] = (entry['topic_slug'], entry['slug'])
        elif entry:
            # Was retired, now back — reuse its original URL.
            entry['status'] = 'active'
            entry['content_sha'] = sha
            entry['last_changed'] = today
            assignments[p] = (entry['topic_slug'], entry['slug'])
        else:
            pending.append((p, record, topic, sha))

    # Deterministic allocation order, independent of CSV row order.
    pending.sort(key=lambda t: (t[2], base_slug(t[1], t[2]), t[0]))

    for p, record, topic, sha in pending:
        base = base_slug(record, topic)
        slug = base
        if (topic, slug) in taken:
            sn = slugify(surname(normalize(record.get('Surgeon(s) / Author(s)'))), 12)
            if sn:
                slug = _with_suffix(base, sn)
        if (topic, slug) in taken:
            slug = _with_suffix(base, p[:6])

        # Guaranteed-unique fallback. Everything above is best-effort readability;
        # this loop is what makes a collision impossible. Without it, two rows can
        # land on the same path and one silently overwrites the other.
        if (topic, slug) in taken:
            stem, n = slug, 2
            while (topic, slug) in taken:
                slug = _with_suffix(stem, str(n))
                n += 1

        taken.add((topic, slug))
        ledger[p] = {
            'pid': p,
            'topic_slug': topic,
            'slug': slug,
            'status': 'active',
            'first_seen': today,
            'content_sha': sha,
            'last_changed': today,
            'source_url': normalize(record.get('Protocol URL')),
            'surgery_type': normalize(record.get('Surgery Type')),
        }
        assignments[p] = (topic, slug)
        report['new'].append(p)

    # Anything in the ledger with no CSV row is retired, but its slug stays
    # reserved forever so a future protocol can't resurrect a dead URL.
    live = set(assignments)
    for p, entry in ledger.items():
        if p not in live and entry.get('status') != 'retired':
            entry['status'] = 'retired'
            report['retired'].append(p)

    return ledger, assignments, report


def print_report(report):
    if report['new']:
        print(f"  Slugs: {len(report['new'])} new")
    if report['changed']:
        print(f"  Slugs: {len(report['changed'])} content updated")
    if report['retired']:
        print(f"  Slugs: {len(report['retired'])} retired")
    if report['new'] and report['retired']:
        print(f"  NOTE: {len(report['retired'])} retired + {len(report['new'])} new — "
              f'possible renames? If a Surgery Type or URL was edited, the key changed '
              f'and the old URL will 404. Use --rekey OLD=NEW to carry the slug across.')
    for p, was, now in report['moved']:
        print(f'  WARNING: {p} topic would move {was} -> {now}; keeping pinned URL '
              f'(URL stability wins). Delete the ledger row only if you accept a 404.')
