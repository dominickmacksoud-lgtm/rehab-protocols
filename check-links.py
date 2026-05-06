#!/usr/bin/env python3
"""
check-links.py - RehabProtocols.com link health checker
Reads protocols-import.csv and guidelines-import.csv, checks every URL
via HTTP HEAD (fallback to GET), and reports broken or redirected links.

Usage:
    python check-links.py              # console report only
    python check-links.py --json       # also write link-report.json
"""

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import date
from pathlib import Path

# Configuration

USER_AGENT = "RehabProtocols.com link-checker/1.0"
TIMEOUT = 10
MAX_REDIRECTS = 5
DELAY = 0.5

ROOT = Path(__file__).resolve().parent
PROTOCOLS_CSV  = ROOT / "protocols-import.csv"
GUIDELINES_CSV = ROOT / "guidelines-import.csv"
REPORT_JSON    = ROOT / "link-report.json"

OK       = "OK"
BROKEN   = "BROKEN"
WARN     = "WARN"
TIMEOUT_S = "TIMEOUT"
ERROR    = "ERROR"
REDIRECT = "REDIRECT"


def load_urls():
    entries = []

    if not PROTOCOLS_CSV.exists():
        print(f"ERROR: {PROTOCOLS_CSV} not found", file=sys.stderr)
    else:
        with PROTOCOLS_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                url = (row.get("Protocol URL") or "").strip()
                if not url:
                    continue
                entries.append({
                    "url":          url,
                    "source":       "protocols",
                    "surgery_type": (row.get("Surgery Type") or row.get("Surgery Category") or "").strip(),
                    "source_org":   (row.get("Source Organization") or "").strip(),
                    "body_region":  (row.get("Body Region Display") or row.get("Body Region") or "").strip(),
                })

    if not GUIDELINES_CSV.exists():
        print(f"ERROR: {GUIDELINES_CSV} not found", file=sys.stderr)
    else:
        with GUIDELINES_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                url = (row.get("Guideline URL") or "").strip()
                if not url:
                    continue
                entries.append({
                    "url":          url,
                    "source":       "guidelines",
                    "surgery_type": (row.get("Condition") or "").strip(),
                    "source_org":   (row.get("Issuing Organization") or "").strip(),
                    "body_region":  (row.get("Body Region Display") or row.get("Body Region") or "").strip(),
                })

    return entries


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def check_url(original_url):
    url = original_url
    hops = 0
    redirected = False

    try:
        while hops <= MAX_REDIRECTS:
            try:
                req = urllib.request.Request(
                    url,
                    method="HEAD",
                    headers={"User-Agent": USER_AGENT},
                )
                opener = urllib.request.build_opener(NoRedirectHandler())
                resp = opener.open(req, timeout=TIMEOUT)
                code = resp.getcode()
                final_url = resp.geturl()
                if redirected and final_url != original_url:
                    return {"status": REDIRECT, "code": code, "final_url": final_url,
                            "note": f"Redirected to {final_url}"}
                return {"status": OK, "code": code, "final_url": final_url, "note": ""}

            except urllib.error.HTTPError as e:
                code = e.code

                if code in (301, 302, 303, 307, 308):
                    location = e.headers.get("Location", "")
                    if not location:
                        return {"status": ERROR, "code": code, "final_url": url,
                                "note": f"Redirect {code} with no Location header"}
                    url = urllib.parse.urljoin(url, location)
                    hops += 1
                    redirected = True
                    continue

                if code == 405:
                    try:
                        req2 = urllib.request.Request(
                            url,
                            method="GET",
                            headers={"User-Agent": USER_AGENT},
                        )
                        opener2 = urllib.request.build_opener(NoRedirectHandler())
                        resp2 = opener2.open(req2, timeout=TIMEOUT)
                        code2 = resp2.getcode()
                        final_url2 = resp2.geturl()
                        if redirected and final_url2 != original_url:
                            return {"status": REDIRECT, "code": code2, "final_url": final_url2,
                                    "note": f"Redirected (GET fallback) to {final_url2}"}
                        return {"status": OK, "code": code2, "final_url": final_url2,
                                "note": "HEAD not allowed; GET succeeded"}
                    except urllib.error.HTTPError as e2:
                        code = e2.code

                if code == 403:
                    return {"status": WARN, "code": 403, "final_url": url,
                            "note": "403 — server may block bots; verify manually"}

                return {"status": BROKEN, "code": code, "final_url": url, "note": f"HTTP {code}"}

        return {"status": ERROR, "code": None, "final_url": url,
                "note": f"Too many redirects (>{MAX_REDIRECTS})"}

    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            return {"status": TIMEOUT_S, "code": None, "final_url": original_url,
                    "note": f"Timed out after {TIMEOUT}s"}
        return {"status": ERROR, "code": None, "final_url": original_url,
                "note": f"Network error: {reason}"}
    except OSError as e:
        if "timed out" in str(e).lower():
            return {"status": TIMEOUT_S, "code": None, "final_url": original_url,
                    "note": f"Timed out after {TIMEOUT}s"}
        return {"status": ERROR, "code": None, "final_url": original_url, "note": f"OS error: {e}"}


def run(write_json=False):
    entries = load_urls()
    total = len(entries)
    print(f"\nRehabProtocols.com link checker — {total} URLs to check\n")

    results = []
    counts = {OK: 0, BROKEN: 0, WARN: 0, TIMEOUT_S: 0, ERROR: 0, REDIRECT: 0}

    for i, entry in enumerate(entries, 1):
        label = f"[{entry['source'].upper():<10}] {(entry['surgery_type'] or '?')[:40]:<40} | {entry['source_org'][:30]}"
        print(f"  [{i:>3}/{total}] {label:<85}", end=" ", flush=True)

        result = check_url(entry["url"])
        result.update(entry)
        results.append(result)
        counts[result["status"]] += 1

        status_display = result["status"]
        if result.get("code"):
            status_display += f" ({result['code']})"
        print(status_display)

        time.sleep(DELAY)

    print("\n" + "=" * 80)
    print(f"  {total} checked | {counts[OK]} OK | {counts[REDIRECT]} redirect | "
          f"{counts[BROKEN]} BROKEN | {counts[WARN]} warn(403) | "
          f"{counts[TIMEOUT_S]} timeout | {counts[ERROR]} error")
    print("=" * 80)

    redirects = [r for r in results if r["status"] == REDIRECT]
    needs_attention = [r for r in results if r["status"] in (BROKEN, WARN, TIMEOUT_S, ERROR)]

    if redirects:
        print(f"\n  REDIRECTED ({len(redirects)}) — original URLs have moved; consider updating CSV:\n")
        for r in redirects:
            print(f"    [{r['source']}] {r['surgery_type']} @ {r['source_org']}")
            print(f"    Original: {r['url']}")
            print(f"    Now at:   {r['final_url']}")
            print()

    if needs_attention:
        print(f"\n  NEEDS ATTENTION ({len(needs_attention)}):\n")
        for r in needs_attention:
            status_str = r["status"]
            if r.get("code"):
                status_str += f" ({r['code']})"
            print(f"    {status_str:<22} [{r['source']}] {r['surgery_type']} @ {r['source_org']}")
            print(f"    {r['note']}")
            print(f"    {r['url']}")
            print()
    else:
        print("\n  All links appear healthy.\n")

    if write_json:
        report = {
            "date":      str(date.today()),
            "total":     total,
            "counts":    counts,
            "broken":    [r for r in results if r["status"] == BROKEN],
            "warn":      [r for r in results if r["status"] == WARN],
            "redirects": redirects,
            "timeouts":  [r for r in results if r["status"] == TIMEOUT_S],
            "errors":    [r for r in results if r["status"] == ERROR],
        }
        REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  JSON report written to {REPORT_JSON.name}\n")

    sys.exit(1 if counts[BROKEN] > 0 else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check all RehabProtocols.com external links")
    parser.add_argument("--json", action="store_true",
                        help="Write link-report.json in addition to console output")
    args = parser.parse_args()
    run(write_json=args.json)
