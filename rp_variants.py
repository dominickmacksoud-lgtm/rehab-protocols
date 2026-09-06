"""Resolve protocol-variants.csv onto protocol rows.

Some catalogued PDFs cover several procedure variants with different
precautions: a THA protocol that spans posterior, anterior and lateral
approaches, or an ACL protocol that spans graft types. The Treatment Planner
shows a dropdown for those so the prompt names the variant and tells the
assistant to apply only that variant's precautions.

Hand-curated, like topics.csv and cpg_pairings.csv. Columns:
  pid      slug-ledger pid (stable primary key)
  label    what the clinician is choosing, e.g. "Surgical approach"
  options  pipe-separated choices, in the order to show them
  note     free text, ignored by the generator

Anything unlisted gets no dropdown. Shipped as a `variant` field on the
protocols.js entry: {"label": ..., "options": [...]}.
"""

import csv

from rp_data import ROOT, normalize

VARIANTS_PATH = ROOT / 'protocol-variants.csv'


def load(path=VARIANTS_PATH):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as f:
        return [dict(r) for r in csv.DictReader(f)]


def resolve(paths, rows=None):
    """Return ({row_index: {'label', 'options'}}, warnings).

    paths: {row_index: (url_path, topic_slug, slug, pid)} from rp_pages.resolve.
    """
    rows = load() if rows is None else rows
    by_pid = {pid: i for i, (_, _, _, pid) in paths.items()}

    out = {}
    warnings = []
    for n, row in enumerate(rows, start=2):
        pid = normalize(row.get('pid'))
        label = normalize(row.get('label'))
        options = [o.strip() for o in (row.get('options') or '').split('|') if o.strip()]
        if not pid or not label or len(options) < 2:
            warnings.append(f'protocol-variants.csv line {n}: needs a pid, a label and at least two options')
            continue
        if pid not in by_pid:
            warnings.append(f'protocol-variants.csv line {n}: pid {pid} matches no protocol')
            continue
        i = by_pid[pid]
        if i in out:
            warnings.append(f'protocol-variants.csv line {n}: pid {pid} listed twice; keeping the first')
            continue
        out[i] = {'label': label, 'options': options}
    return out, warnings
