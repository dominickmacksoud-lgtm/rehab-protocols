#!/usr/bin/env python3
"""
Turn link-report.json (written by check-links.py) into a GitHub issue body.

Runs inside .github/workflows/link-check.yml after the checker. Selects the
statuses that need a human (BROKEN, WRONG_TYPE, REDIRECT_PERM), diffs them
against the previous week's report so newly broken links stand out, and for each
broken URL asks the Wayback Machine for its latest capture, rewrites it in the
`id_` form the site requires, and verifies that capture through the checker's
own fetch path (curl cannot see the toolbar-page failure; see CLAUDE.md).

    python link-issue.py                          # reads link-report.json
    python link-issue.py --previous prev.json     # enables "newly broken"
    python link-issue.py --no-wayback             # offline / tests

Writes the Markdown body to --out (default issue-body.md) and, when
GITHUB_OUTPUT is set, the workflow outputs has_problems, title and run_date.
"""

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

AVAILABILITY_API = "https://archive.org/wayback/available?"
WAYBACK_DELAY = 2.5          # archive.org drops connections when hit faster
LOOKUP_TIMEOUT = 30

FAILING = {"BROKEN", "WRONG_TYPE"}
MOVED = {"REDIRECT_PERM"}
SOFT = {"WARN", "TIMEOUT", "ERROR"}


def _load_checker():
    """Import check-links.py (hyphenated name) so the verification step uses the
    exact code path the weekly run uses."""
    spec = importlib.util.spec_from_file_location("check_links", ROOT / "check-links.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wayback_id_url(timestamp, original):
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def lookup_capture(url):
    """Latest 200 capture for url via the availability API, or None."""
    q = AVAILABILITY_API + urllib.parse.urlencode({"url": url})
    req = urllib.request.Request(q, headers={"User-Agent": "RehabProtocols.com link-checker/2.0"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=LOOKUP_TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
            closest = (data.get("archived_snapshots") or {}).get("closest") or {}
            if closest.get("available") and closest.get("timestamp"):
                return closest["timestamp"]
            return None
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            if attempt == 0:
                time.sleep(WAYBACK_DELAY)
    return None


def suggest_wayback(rows, checker):
    """Attach a `wayback` dict to each failing row: suggested id_ URL plus the
    checker's verdict on it."""
    opener, tracker = checker.make_opener(checker.make_ssl_context())
    for r in rows:
        url = r["url"]
        if "web.archive.org" in url:
            r["wayback"] = {"note": "already an archived copy; pick a different capture by hand"}
            continue
        ts = lookup_capture(url)
        if not ts:
            r["wayback"] = {"note": "no capture in the Wayback Machine"}
            continue
        suggestion = wayback_id_url(ts, url)
        time.sleep(WAYBACK_DELAY)
        try:
            verdict = checker.check_url(opener, tracker, suggestion)
        except Exception as e:  # never let a verification hiccup sink the issue
            verdict = {"status": "ERROR", "code": None, "note": str(e)[:120]}
        r["wayback"] = {
            "timestamp": ts,
            "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
            "url": suggestion,
            "status": verdict.get("status"),
            "code": verdict.get("code"),
            "note": verdict.get("note") or "",
        }
        time.sleep(WAYBACK_DELAY)


def _cell(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def _rows_cell(r):
    return "<br>".join(
        f"{_cell(x['surgery_type'])} @ {_cell(x['source_org'])} [{x['source']}]"
        for x in r["rows"])


def _status_cell(r):
    s = r["status"]
    if r.get("code"):
        s += f" ({r['code']})"
    if r.get("note"):
        s += f"<br><sub>{_cell(r['note'])}</sub>"
    return s


def _wayback_cell(r):
    w = r.get("wayback")
    if not w:
        return "not looked up"
    if "url" not in w:
        return w["note"]
    ok = w["status"] == "OK"
    verdict = "verified, serves the PDF" if ok else f"capture answers {w['status']}" + (
        f" ({w['code']})" if w.get("code") else "")
    return f"`{w['url']}`<br><sub>capture {w['date']}, {verdict}</sub>"


def build_body(report, previous):
    results = report["results"]
    counts = report["counts"]
    run_date = report["date"]

    broken = [r for r in results if r["status"] in FAILING]
    moved = [r for r in results if r["status"] in MOVED]
    soft = [r for r in results if r["status"] in SOFT]

    prev_status = {r["url"]: r["status"] for r in (previous or {}).get("results", [])}
    newly = [r for r in broken if prev_status and prev_status.get(r["url"]) not in FAILING]

    L = []
    L.append(f"**Run date:** {run_date}  ")
    L.append(f"**Checked:** {report['unique']} unique URLs across {report['rows']} catalog rows  ")
    L.append(f"**Broken:** {counts.get('BROKEN', 0)} broken, {counts.get('WRONG_TYPE', 0)} wrong type "
             f"(a .pdf URL that now serves an HTML page)  ")
    L.append(f"**Moved:** {counts.get('REDIRECT_PERM', 0)} permanent redirects  ")
    L.append("")

    if previous:
        if newly:
            L.append(f"### Newly broken since {previous.get('date', 'the last run')} ({len(newly)})")
            L.append("")
            for r in newly:
                L.append(f"- `{r['url']}` was {prev_status.get(r['url'], 'unchecked')}, now {r['status']}")
            L.append("")
        else:
            L.append(f"No new failures since {previous.get('date', 'the last run')}. "
                     "Everything below was already failing.")
            L.append("")
    else:
        L.append("No previous report was available, so every failure below counts as new.")
        L.append("")

    if broken:
        L.append(f"### Broken links ({len(broken)})")
        L.append("")
        L.append("| Protocol | Status | URL | Wayback suggestion |")
        L.append("|---|---|---|---|")
        for r in broken:
            L.append(f"| {_rows_cell(r)} | {_status_cell(r)} | `{_cell(r['url'])}` | {_wayback_cell(r)} |")
        L.append("")

    if moved:
        L.append(f"### Permanently moved ({len(moved)})")
        L.append("")
        L.append("The content still loads, so these are low priority. Updating the CSV keeps the "
                 "catalog pointing at the canonical address.")
        L.append("")
        L.append("| Protocol | Old URL | Now at |")
        L.append("|---|---|---|")
        for r in moved:
            L.append(f"| {_rows_cell(r)} | `{_cell(r['url'])}` | `{_cell(r.get('final_url'))}` |")
        L.append("")

    if soft:
        L.append("<details>")
        L.append(f"<summary>{len(soft)} warnings, timeouts and errors (usually bot walls hit by the "
                 "GitHub Actions IP range; verify in a browser, no action needed unless one persists)</summary>")
        L.append("")
        L.append("| Protocol | Status | URL |")
        L.append("|---|---|---|")
        for r in soft:
            L.append(f"| {_rows_cell(r)} | {_status_cell(r)} | `{_cell(r['url'])}` |")
        L.append("")
        L.append("</details>")
        L.append("")

    L.append("---")
    L.append("### How to fix")
    L.append("")
    L.append("1. Look for a republished copy on the source organization's site first. "
             "Fall back to the Wayback suggestion only if the document is really gone. "
             "Archived URLs must keep the `id_` form shown above.")
    L.append("2. Edit the URL in `protocols-import.csv` or `guidelines-import.csv`. "
             "For a Wayback repoint also add a row to `wayback-repoints.csv` and note the archived copy in the row's Notes.")
    L.append("3. Changing a Protocol URL changes the page's identity. Regenerate with a rekey so the page keeps its address "
             "(see the slug ledger section of CLAUDE.md): `python generate-protocols.py --rekey OLDPID=NEWPID`, "
             "then `python rp_verify.py`. Guidelines only need `python generate-guidelines.py`.")
    L.append("4. If the document is gone for good, remove the row and delete its `protocols/<topic>/<slug>/` directory.")
    L.append("5. Confirm with `python check-links.py --failed`, then commit and push.")
    L.append("")
    L.append("*Generated by the [link-check workflow](../../actions/workflows/link-check.yml). "
             "The weekly triage routine reads this issue and comments with replacement URLs it can find.*")
    return "\n".join(L), broken, moved


def build_title(run_date, broken, moved):
    parts = []
    if broken:
        parts.append(f"{len(broken)} broken")
    if moved:
        parts.append(f"{len(moved)} moved")
    return f"Link health: {', '.join(parts) or 'all clear'} ({run_date})"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", default=str(ROOT / "link-report.json"))
    ap.add_argument("--previous", help="last run's link-report.json, for the newly-broken diff")
    ap.add_argument("--out", default=str(ROOT / "issue-body.md"))
    ap.add_argument("--no-wayback", action="store_true", help="skip archive.org lookups")
    args = ap.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"ERROR: {report_path} not found; did check-links.py run?", file=sys.stderr)
        return 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if "results" not in report:
        print("ERROR: report has no 'results' list; check-links.py format changed?", file=sys.stderr)
        return 2

    previous = None
    if args.previous and Path(args.previous).exists():
        try:
            previous = json.loads(Path(args.previous).read_text(encoding="utf-8"))
            if "results" not in previous:
                previous = None
        except ValueError:
            previous = None

    failing = [r for r in report["results"] if r["status"] in FAILING]
    if failing and not args.no_wayback:
        print(f"Looking up Wayback captures for {len(failing)} broken URL(s)...")
        suggest_wayback(failing, _load_checker())

    body, broken, moved = build_body(report, previous)
    title = build_title(report["date"], broken, moved)
    has_problems = bool(broken or moved)

    Path(args.out).write_text(body, encoding="utf-8")
    print(f"{title}\n  body written to {args.out} ({len(body)} chars), has_problems={has_problems}")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"has_problems={'true' if has_problems else 'false'}\n")
            fh.write(f"run_date={report['date']}\n")
            fh.write(f"title={title}\n")
            fh.write(f"broken_count={len(broken)}\n")
            fh.write(f"moved_count={len(moved)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
