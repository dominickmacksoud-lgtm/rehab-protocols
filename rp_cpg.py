"""Resolve cpg_pairings.csv onto protocol rows.

cpg_pairings.csv is hand-curated, like topics.csv. It says which clinical
practice guideline may accompany which protocols in the Treatment Planner
prompt. Region matching and category matching were both rejected on 2026-09-06:
region matching would have attached the Midportion Achilles Tendinopathy CPG to
a surgical Achilles repair. A guideline attaches only where it was written for
that specific procedure, and anything unlisted gets no guideline at all.

Columns: cpg_url, match_type, match_value, note
  match_type 'topic' matches every protocol whose pinned topic slug is match_value.
  match_type 'pid'   matches the one protocol whose slug-ledger pid is match_value,
                     for topics like `fracture` that mix body regions.

The planner reads the result as a `cpg` field on each protocols.js entry and
looks the guideline up in guidelines.js by URL.
"""

import csv

from rp_data import ROOT, normalize

PAIRINGS_PATH = ROOT / 'cpg_pairings.csv'
GUIDELINES_PATH = ROOT / 'guidelines-import.csv'

MATCH_TYPES = ('topic', 'pid')


def load_pairings(path=PAIRINGS_PATH):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as f:
        return [dict(r) for r in csv.DictReader(f)]


def guideline_urls(path=GUIDELINES_PATH):
    if not path.exists():
        return set()
    with path.open(newline='', encoding='utf-8') as f:
        return {normalize(r.get('Guideline URL')) for r in csv.DictReader(f)}


def resolve(paths, pairings=None, known_urls=None):
    """Return ({row_index: cpg_url}, warnings).

    paths: {row_index: (url_path, topic_slug, slug, pid)} from rp_pages.resolve,
    so topic matching uses the pinned ledger topic that the page URL uses.
    """
    pairings = load_pairings() if pairings is None else pairings
    known_urls = guideline_urls() if known_urls is None else known_urls

    by_topic = {}
    by_pid = {}
    for i, (_, topic, _, pid) in paths.items():
        by_topic.setdefault(topic, []).append(i)
        by_pid[pid] = i

    cpg = {}
    warnings = []
    for n, row in enumerate(pairings, start=2):
        url = normalize(row.get('cpg_url'))
        mtype = normalize(row.get('match_type'))
        value = normalize(row.get('match_value'))
        if not url or not mtype or not value:
            warnings.append(f'cpg_pairings.csv line {n}: incomplete row skipped')
            continue
        if mtype not in MATCH_TYPES:
            warnings.append(f'cpg_pairings.csv line {n}: unknown match_type {mtype!r}')
            continue
        if known_urls and url not in known_urls:
            warnings.append(f'cpg_pairings.csv line {n}: cpg_url is not in guidelines-import.csv: {url}')
            continue

        if mtype == 'topic':
            hits = by_topic.get(value, [])
        else:
            hits = [by_pid[value]] if value in by_pid else []
        if not hits:
            warnings.append(f'cpg_pairings.csv line {n}: {mtype} {value!r} matches no protocol')
            continue

        for i in hits:
            if i in cpg and cpg[i] != url:
                warnings.append(
                    f'cpg_pairings.csv line {n}: row {i + 2} already paired with '
                    f'{cpg[i]}; keeping the first')
                continue
            cpg[i] = url

    return cpg, warnings
