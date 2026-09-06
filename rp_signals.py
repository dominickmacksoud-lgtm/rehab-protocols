"""Usage and freshness tags for protocol cards: popular, trending, planned, new.

Three of the four come from popularity.json, which ga-popularity.py refreshes
weekly from Google Analytics (see .github/workflows/popularity.yml). The
fourth, `new`, comes from the catalog itself. Thresholds live here, not in the
export script, so a re-run of the generator against the same data always
yields the same tags and the rules can be tuned without touching Analytics.

popularity.json shape (paths are the slug ledger's URL contract):
  {"generated": "YYYY-MM-DD", "window_days": 28,
   "protocols": {"/protocols/<topic>/<slug>/": {"views": n, "views7": n, "planned": n}}}

Rules (all relative, so they keep working as traffic grows):
  popular   views over the window in the top POPULAR_SHARE of protocols that
            have any views (never fewer than POPULAR_LIST protocols when that
            many have views), and at least POPULAR_MIN views
  planned   planner selections in the top PLANNED_SHARE (never fewer than
            PLANNED_LIST), at least PLANNED_MIN
  trending  at least TREND_MIN views in the last 7 days, and that week at least
            TREND_RATIO times the average of the three weeks before it
  new       catalogued within NEW_DAYS of today, from the CSV's Cataloged Date
            (falling back to the ledger's first_seen)
"""

import json
import re
from datetime import date, timedelta

from rp_data import ROOT, normalize

POPULARITY_PATH = ROOT / 'popularity.json'

POPULAR_SHARE = 0.10
POPULAR_MIN = 5
POPULAR_LIST = 10     # never fewer than this many when enough protocols qualify
PLANNED_SHARE = 0.10
PLANNED_MIN = 2
PLANNED_LIST = 5
TREND_MIN = 5
TREND_RATIO = 2.0
NEW_DAYS = 60

TAG_ORDER = ('popular', 'trending', 'planned', 'new')

MONTHS = {m: i for i, m in enumerate(
    ['january', 'february', 'march', 'april', 'may', 'june', 'july',
     'august', 'september', 'october', 'november', 'december'], start=1)}


def load_popularity(path=POPULARITY_PATH):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data.get('protocols') or {}


def parse_catalog_date(text):
    """'2026-08-02' -> date; 'April 2026' -> first of that month; else None."""
    text = normalize(text)
    if not text:
        return None
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r'^([A-Za-z]+)\s+(\d{4})$', text)
    if m and m.group(1).lower() in MONTHS:
        return date(int(m.group(2)), MONTHS[m.group(1).lower()], 1)
    return None


def _cutoff(values, share, floor, min_list):
    """Smallest value that admits the top `share` of nonzero values.

    A percentage alone collapses to one or two protocols while traffic is low,
    which makes a filter nobody would use, so the list is at least `min_list`
    long when that many protocols have any activity. `floor` still applies, so
    a protocol never earns a tag on a handful of views.
    """
    nonzero = sorted((v for v in values if v > 0), reverse=True)
    if not nonzero:
        return None
    k = max(min_list, int(round(len(nonzero) * share)))
    k = min(k, len(nonzero))
    return max(floor, nonzero[k - 1])


def resolve(records, paths, ledger=None, today=None, popularity=None):
    """Return ({row_index: [tags]}, summary dict)."""
    today = today or date.today()
    pop = load_popularity() if popularity is None else popularity
    ledger = ledger or {}

    stats = {}
    for i, (url_path, _, _, pid) in paths.items():
        s = pop.get(url_path) or {}
        stats[i] = {
            'views': int(s.get('views') or 0),
            'views7': int(s.get('views7') or 0),
            'planned': int(s.get('planned') or 0),
            'pid': pid,
        }

    pop_cut = _cutoff([s['views'] for s in stats.values()], POPULAR_SHARE, POPULAR_MIN, POPULAR_LIST)
    plan_cut = _cutoff([s['planned'] for s in stats.values()], PLANNED_SHARE, PLANNED_MIN, PLANNED_LIST)
    new_since = today - timedelta(days=NEW_DAYS)

    tags = {}
    counts = {t: 0 for t in TAG_ORDER}
    for i, s in stats.items():
        t = []
        if pop_cut is not None and s['views'] >= pop_cut:
            t.append('popular')
        prior_weekly = max(0.0, (s['views'] - s['views7']) / 3.0)
        if s['views7'] >= TREND_MIN and s['views7'] >= TREND_RATIO * max(prior_weekly, 1.0):
            t.append('trending')
        if plan_cut is not None and s['planned'] >= plan_cut:
            t.append('planned')

        catalogued = parse_catalog_date(records[i].get('Cataloged Date'))
        if catalogued is None:
            entry = ledger.get(s['pid']) or {}
            catalogued = parse_catalog_date(entry.get('first_seen'))
        if catalogued and catalogued >= new_since:
            t.append('new')

        if t:
            tags[i] = t
            for x in t:
                counts[x] += 1

    return tags, {'counts': counts, 'popular_cutoff': pop_cut, 'planned_cutoff': plan_cut,
                  'with_views': sum(1 for s in stats.values() if s['views'] > 0)}
