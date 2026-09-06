"""Refresh popularity.json from Google Analytics 4.

Runs weekly in .github/workflows/popularity.yml and can be run by hand:

    GA4_PROPERTY_ID=123456789 GA4_SA_KEY='{...service account json...}' python ga-popularity.py
    python ga-popularity.py --selftest      # no network, exercises the parsing

Two reports, both on built-in dimensions so no custom definitions are needed
in the Analytics property:

  1. pagePath views for /protocols/<topic>/<slug>/ pages, over the last 28 days
     and the last 7 days (two date ranges in one request).
  2. pagePathPlusQueryString views for /treatment-planner/?p=<path>, last 28
     days. Enhanced measurement fires a page_view when the planner rewrites the
     URL on selection, so this counts protocols chosen in the planner.

Output is keyed by the protocol page path, which is the slug ledger's URL
contract. rp_signals.py turns the numbers into tags at generate time; this
script deliberately stores raw counts only.

Exit code 0 with a message when credentials are absent, so the workflow still
regenerates the site (which refreshes the `new` tag) on a fork or before setup.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / 'popularity.json'
WINDOW_DAYS = 28


def normalize_protocol_path(raw):
    """'/protocols/a/b' or '/protocols/a/b/index.html' -> '/protocols/a/b/'; else None."""
    if not raw:
        return None
    path = unquote(raw.split('?', 1)[0].split('#', 1)[0])
    if path.endswith('/index.html'):
        path = path[:-len('index.html')]
    if not path.endswith('/'):
        path += '/'
    parts = [p for p in path.split('/') if p]
    if len(parts) != 3 or parts[0] != 'protocols':
        return None
    return '/' + '/'.join(parts) + '/'


def planner_target(path_plus_query):
    """'/treatment-planner/?p=%2Fprotocols%2Fa%2Fb%2F' -> '/protocols/a/b/'; else None."""
    if not path_plus_query:
        return None
    parts = urlsplit(path_plus_query)
    if not parts.path.rstrip('/').endswith('/treatment-planner'):
        return None
    p = parse_qs(parts.query).get('p')
    return normalize_protocol_path(p[0]) if p else None


def aggregate(protocol_rows, planner_rows):
    """protocol_rows: (pagePath, dateRangeName, views); planner_rows: (pathPlusQuery, views)."""
    out = defaultdict(lambda: {'views': 0, 'views7': 0, 'planned': 0})
    for page_path, range_name, views in protocol_rows:
        key = normalize_protocol_path(page_path)
        if not key:
            continue
        if range_name == 'last28':
            out[key]['views'] += int(views)
        elif range_name == 'last7':
            out[key]['views7'] += int(views)
    for ppq, views in planner_rows:
        key = planner_target(ppq)
        if key:
            out[key]['planned'] += int(views)
    return {k: v for k, v in sorted(out.items()) if any(v.values())}


def write_output(protocols, generated=None):
    payload = {
        'generated': (generated or date.today()).isoformat(),
        'window_days': WINDOW_DAYS,
        'source': 'Google Analytics 4, refreshed by .github/workflows/popularity.yml',
        'protocols': protocols,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=1, sort_keys=True) + '\n', encoding='utf-8')


def fetch(property_id, credentials_json):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Filter, FilterExpression, Metric, RunReportRequest)
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    client = BetaAnalyticsDataClient(credentials=creds)
    prop = f'properties/{property_id}'

    def run(dimensions, metric, date_ranges, dim_filter, limit=100000):
        rows = []
        offset = 0
        while True:
            req = RunReportRequest(
                property=prop,
                dimensions=[Dimension(name=d) for d in dimensions],
                metrics=[Metric(name=metric)],
                date_ranges=date_ranges,
                dimension_filter=dim_filter,
                limit=limit, offset=offset,
            )
            resp = client.run_report(req)
            for r in resp.rows:
                rows.append(([d.value for d in r.dimension_values], int(r.metric_values[0].value)))
            offset += limit
            if offset >= resp.row_count:
                break
        return rows

    protocol_rows = run(
        ['pagePath', 'dateRange'], 'screenPageViews',
        [DateRange(start_date=f'{WINDOW_DAYS}daysAgo', end_date='today', name='last28'),
         DateRange(start_date='7daysAgo', end_date='today', name='last7')],
        FilterExpression(filter=Filter(
            field_name='pagePath',
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.BEGINS_WITH, value='/protocols/'))),
    )
    planner_rows = run(
        ['pagePathPlusQueryString'], 'screenPageViews',
        [DateRange(start_date=f'{WINDOW_DAYS}daysAgo', end_date='today')],
        FilterExpression(filter=Filter(
            field_name='pagePathPlusQueryString',
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.CONTAINS, value='/treatment-planner/?p='))),
    )
    return ([(dims[0], dims[1], v) for dims, v in protocol_rows],
            [(dims[0], v) for dims, v in planner_rows])


def selftest():
    proto = [
        ('/protocols/acl-reconstruction/moon-group/', 'last28', 40),
        ('/protocols/acl-reconstruction/moon-group/', 'last7', 12),
        ('/protocols/acl-reconstruction/moon-group/index.html', 'last28', 2),
        ('/protocols/acl-reconstruction/', 'last28', 99),          # hub, ignored
        ('/protocols/', 'last28', 50),                             # index, ignored
        ('/knee/', 'last28', 30),                                  # region, ignored
        ('/protocols/tka/mgh/', 'last7', 3),
    ]
    planner = [
        ('/treatment-planner/?p=%2Fprotocols%2Facl-reconstruction%2Fmoon-group%2F', 7),
        ('/treatment-planner/?p=/protocols/tka/mgh/&theme=dark', 1),
        ('/treatment-planner/', 500),                               # no protocol, ignored
        ('/treatment-planner/?p=/protocols/tka/', 9),               # hub path, ignored
    ]
    got = aggregate(proto, planner)
    want = {
        '/protocols/acl-reconstruction/moon-group/': {'views': 42, 'views7': 12, 'planned': 7},
        '/protocols/tka/mgh/': {'views': 0, 'views7': 3, 'planned': 1},
    }
    assert got == want, json.dumps(got, indent=1)
    print('selftest ok')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return 0

    property_id = os.environ.get('GA4_PROPERTY_ID', '').strip()
    key = os.environ.get('GA4_SA_KEY', '').strip()
    if not property_id or not key:
        print('ga-popularity: GA4_PROPERTY_ID or GA4_SA_KEY not set; leaving popularity.json unchanged.')
        return 0

    protocol_rows, planner_rows = fetch(property_id, key)
    protocols = aggregate(protocol_rows, planner_rows)
    write_output(protocols)
    print(f'ga-popularity: {len(protocols)} protocols with activity in the last {WINDOW_DAYS} days -> {OUT_PATH.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
