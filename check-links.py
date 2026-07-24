#!/usr/bin/env python3
"""
check-links.py - RehabProtocols.com link health checker

Reads protocols-import.csv and guidelines-import.csv and verifies every URL:
  * resolves (with retries for transient failures)
  * is not a soft-404 (a .pdf URL that quietly serves HTML)
  * has not been permanently redirected

Hosts are checked in parallel, but requests to any single host stay sequential
and rate-limited, so no server ever receives concurrent traffic from us.

Usage:
    python check-links.py                      # check everything
    python check-links.py --filter lahey       # only URLs/orgs matching a substring
    python check-links.py --failed             # recheck only last run's failures
    python check-links.py --skip example.com   # temporarily exempt a domain

Exit codes: 0 = clean, 1 = broken links found, 2 = script/config error.

Transport note: this uses stdlib urllib on purpose.
  * `requests` cannot be imported here at all -- the site has a real page at
    ./requests/index.html, which shadows the package for anything run from the repo root.
  * httpx was tried and reverted: ~105 URLs (chop.edu, samhealth.org, sbortho.com,
    orthopedicsri.com and others) answer 200 to urllib but 403 to httpx, reproducibly,
    on both HEAD and GET, unaffected by headers, SSL context or request rate. The cause
    was never established -- only the effect, which is a ~12% false-positive rate.
Do not swap the transport without re-running a full check and comparing the 403 count.
"""

import argparse
import csv
import http.client
import json
import random
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

# Force UTF-8 output on Windows to handle non-ASCII characters in protocol names
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Configuration

USER_AGENT      = "RehabProtocols.com link-checker/2.0"
TIMEOUT         = 20     # seconds per request
DELAY           = 0.3    # seconds between requests to the SAME host
HOST_WORKERS    = 12     # how many distinct hosts to check in parallel
MAX_ATTEMPTS    = 3
PDF_SNIFF_BYTES = 2048
MIN_PDF_BYTES   = 1024   # a "PDF" smaller than this is almost certainly an error page

RETRY_STATUS = {429, 500, 502, 503, 504}
# Servers that reject HEAD frequently answer GET fine; confirm before crying broken.
HEAD_HOSTILE = {400, 403, 404, 405, 406, 501}

ROOT           = Path(__file__).resolve().parent
PROTOCOLS_CSV  = ROOT / "protocols-import.csv"
GUIDELINES_CSV = ROOT / "guidelines-import.csv"
REPORT_JSON    = ROOT / "link-report.json"

OK            = "OK"
BROKEN        = "BROKEN"
WARN          = "WARN"
WRONG_TYPE    = "WRONG_TYPE"
REDIRECT_PERM = "REDIRECT_PERM"
REDIRECT_TEMP = "REDIRECT_TEMP"
TIMEOUT_S     = "TIMEOUT"
ERROR         = "ERROR"
SKIPPED       = "SKIPPED"

ALL_STATUSES = [OK, REDIRECT_TEMP, REDIRECT_PERM, WRONG_TYPE, WARN,
                BROKEN, TIMEOUT_S, ERROR, SKIPPED]
# Statuses that mean "a human needs to look at this"
PROBLEM = {BROKEN, WRONG_TYPE, TIMEOUT_S, ERROR, WARN}
# Statuses that should fail the build
FAILING = {BROKEN, WRONG_TYPE}


# Loading

def load_entries():
    """Return one entry per catalog row that has a URL."""
    entries = []
    missing = 0

    specs = [
        (PROTOCOLS_CSV,  "protocols",  "Protocol URL",  "Surgery Type",
         "Surgery Category", "Source Organization"),
        (GUIDELINES_CSV, "guidelines", "Guideline URL", "Condition",
         None, "Issuing Organization"),
    ]

    for path, source, url_col, name_col, alt_name_col, org_col in specs:
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            missing += 1
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                url = (row.get(url_col) or "").strip()
                if not url:
                    continue
                name = (row.get(name_col) or "").strip()
                if not name and alt_name_col:
                    name = (row.get(alt_name_col) or "").strip()
                entries.append({
                    "url":          url,
                    "source":       source,
                    "surgery_type": name,
                    "source_org":   (row.get(org_col) or "").strip(),
                    "body_region":  (row.get("Body Region Display")
                                     or row.get("Body Region") or "").strip(),
                })

    if missing == len(specs):
        print("ERROR: no input CSVs found; nothing to check", file=sys.stderr)
        sys.exit(2)

    return entries


# HTTP

def make_ssl_context():
    """
    Allow legacy TLS renegotiation.

    Some hospital servers (notably lahey.org) run older TLS stacks that OpenSSL 3
    refuses by default with UNSAFE_LEGACY_RENEGOTIATION_DISABLED. Those URLs used to
    be blanket-skipped as "bot-blocked", which was a misdiagnosis -- they answer fine
    once renegotiation is permitted. This checker only issues unauthenticated GET/HEAD
    against public PDFs, so the relaxed setting carries no credential risk. Do not
    re-add a domain skip list for these.
    """
    ctx = ssl.create_default_context()
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    return ctx


class _RedirectTracker(urllib.request.HTTPRedirectHandler):
    """Records the redirect chain so permanent moves can be told from temporary ones."""

    def __init__(self):
        super().__init__()
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            self.chain.append(code)
        return new


def make_opener(ctx):
    """One opener per worker thread; handlers carry per-request state."""
    tracker = _RedirectTracker()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx), tracker)
    return opener, tracker


class _Resp:
    """Minimal response view over urllib's two shapes (success and HTTPError)."""
    __slots__ = ("status_code", "headers", "url", "redirects")

    def __init__(self, status_code, headers, url, redirects):
        self.status_code = status_code
        self.headers = headers        # HTTPMessage: .get() is case-insensitive
        self.url = url
        self.redirects = redirects


def _open(opener, tracker, url, method, extra_headers=None):
    """Perform one request. Returns (_Resp, body_bytes_or_None). Raises on transport errors."""
    tracker.chain.clear()
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, method=method, headers=headers)

    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            body = r.read(PDF_SNIFF_BYTES) if method == "GET" else None
            return _Resp(r.getcode(), r.headers, r.geturl(), list(tracker.chain)), body
    except urllib.error.HTTPError as e:
        try:
            return _Resp(e.code, e.headers, e.url, list(tracker.chain)), None
        finally:
            e.close()


def _result(status, code, final_url, note):
    return {"status": status, "code": code, "final_url": final_url, "note": note}


def _backoff(attempt, resp=None):
    """Exponential backoff with jitter, honoring Retry-After when present."""
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 30.0))
                return
            except (TypeError, ValueError):
                pass
    time.sleep(min(2 ** attempt, 8) * (0.5 + random.random() * 0.5))


def _is_pdf_url(url):
    return urllib.parse.urlsplit(url).path.lower().endswith(".pdf")


def _trivial_redirect(original, final):
    """http->https, www, and trailing-slash shuffles are not worth reporting."""
    def norm(u):
        p = urllib.parse.urlsplit(u)
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return (host, p.path.rstrip("/"), p.query)
    return norm(original) == norm(final)


# A .pdf URL answering with HTML is either a dead link dressed up as a page (a
# soft-404) or a download interstitial / bot wall. Only the first is a real failure;
# PMC, for one, serves a "Preparing to download" page that a browser gets past fine.
# Absent one of these markers we warn rather than fail -- a false BROKEN is the error
# that makes people stop trusting this script.
DEAD_PAGE_MARKERS = ("not found", "no longer available", "cannot be found",
                     "does not exist", "page has moved", "410 gone")


def _not_a_pdf(resp, final, ctype, sniff, notes):
    text = sniff.decode("utf-8", "replace").lower()
    hit = next((m for m in DEAD_PAGE_MARKERS if m in text), None)
    if hit:
        notes.append(f"expected PDF, got '{ctype or 'unknown'}' page matching "
                     f"'{hit}' - link is probably dead")
        return WRONG_TYPE, resp.status_code, final, "; ".join(notes)
    notes.append(f"expected PDF, got '{ctype or 'unknown'}' - download interstitial "
                 f"or bot protection; verify manually")
    return WARN, resp.status_code, final, "; ".join(notes)


def _ranged_get(opener, tracker, url):
    """Fetch just the first PDF_SNIFF_BYTES. Returns (_Resp, body) or None."""
    try:
        return _open(opener, tracker, url, "GET",
                     {"Range": f"bytes=0-{PDF_SNIFF_BYTES - 1}"})
    except (urllib.error.URLError, http.client.HTTPException,
            socket.timeout, TimeoutError, OSError):
        return None


def _classify(opener, tracker, url, resp, body):
    """Turn a non-error response into a status, checking redirects and PDF content."""
    final = resp.url or url
    notes = []
    status = OK

    if resp.redirects and not _trivial_redirect(url, final):
        first = resp.redirects[0]
        if first in (301, 308):
            status = REDIRECT_PERM
            notes.append(f"permanent redirect ({first})")
        else:
            status = REDIRECT_TEMP
            notes.append(f"temporary redirect ({first})")

    if _is_pdf_url(url):
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        sniff = body

        if sniff is None and "pdf" not in ctype:
            # Header says it isn't a PDF. Headers lie; check the actual bytes.
            got = _ranged_get(opener, tracker, final)
            if got is None:
                notes.append(f"content-type '{ctype or 'missing'}' could not be verified")
                return _result(WARN, resp.status_code, final, "; ".join(notes))
            sniff = got[1] or b""

        if sniff is not None and not sniff.startswith(b"%PDF"):
            return _result(*_not_a_pdf(resp, final, ctype, sniff, notes))

        clen = resp.headers.get("Content-Length")
        if clen and str(clen).isdigit() and int(clen) < MIN_PDF_BYTES:
            notes.append(f"suspiciously small ({clen} bytes)")
            return _result(WARN, resp.status_code, final, "; ".join(notes))

    return _result(status, resp.status_code, final, "; ".join(notes))


def check_url(opener, tracker, url):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp, _ = _open(opener, tracker, url, "HEAD")
            code = resp.status_code

            if code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                _backoff(attempt, resp)
                continue

            if code in HEAD_HOSTILE:
                got = _ranged_get(opener, tracker, url)
                if got is not None:
                    resp2, body = got
                    if resp2.status_code < 400:
                        return _classify(opener, tracker, url, resp2, body)
                    if resp2.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                        _backoff(attempt, resp2)
                        continue
                    resp, code = resp2, resp2.status_code

            if code == 429:
                return _result(WARN, 429, resp.url,
                               "rate-limited (429) after retries; verify manually")
            if code < 400:
                return _classify(opener, tracker, url, resp, None)
            if code == 403:
                return _result(WARN, 403, resp.url,
                               "403 - server blocks automated requests; verify manually")
            if code in RETRY_STATUS:
                return _result(BROKEN, code, resp.url,
                               f"HTTP {code} after {MAX_ATTEMPTS} attempts")
            return _result(BROKEN, code, resp.url, f"HTTP {code}")

        except (socket.timeout, TimeoutError):
            if attempt < MAX_ATTEMPTS:
                _backoff(attempt)
                continue
            return _result(TIMEOUT_S, None, url,
                           f"timed out after {MAX_ATTEMPTS} attempts")
        except urllib.error.URLError as e:
            reason = str(getattr(e, "reason", e))
            if "timed out" in reason.lower():
                if attempt < MAX_ATTEMPTS:
                    _backoff(attempt)
                    continue
                return _result(TIMEOUT_S, None, url,
                               f"timed out after {MAX_ATTEMPTS} attempts")
            if attempt < MAX_ATTEMPTS:
                _backoff(attempt)
                continue
            return _result(ERROR, None, url, f"network error: {reason}")
        except (http.client.HTTPException, ssl.SSLError, OSError) as e:
            if attempt < MAX_ATTEMPTS:
                _backoff(attempt)
                continue
            return _result(ERROR, None, url, f"{type(e).__name__}: {e}")

    return _result(ERROR, None, url, "retry attempts exhausted")


# Concurrency

class Progress:
    def __init__(self, total):
        self.total = total
        self.done = 0
        self.counts = {s: 0 for s in ALL_STATUSES}
        self.lock = threading.Lock()
        # Redrawing in place only makes sense on a terminal; when piped to a file or
        # a background task log, emit an occasional plain line instead.
        self.tty = sys.stdout.isatty()
        self.every = max(1, total // 20)

    def tick(self, status):
        with self.lock:
            self.done += 1
            self.counts[status] += 1
            bad = sum(self.counts[s] for s in PROBLEM)
            line = (f"  [{self.done}/{self.total}] ok={self.counts[OK]} "
                    f"broken={self.counts[BROKEN]} wrong-type={self.counts[WRONG_TYPE]} "
                    f"warn={self.counts[WARN]} needs-review={bad}")
            if self.tty:
                print(f"\r{line:<96}", end="", flush=True)
            elif self.done % self.every == 0 or self.done == self.total:
                print(line, flush=True)


def check_host(host, urls, ctx, progress, skip_domains):
    results = {}

    if host in skip_domains:
        for u in urls:
            results[u] = _result(SKIPPED, None, u, "skipped via --skip")
            progress.tick(SKIPPED)
        return results

    opener, tracker = make_opener(ctx)
    for i, u in enumerate(urls):
        if i:
            time.sleep(DELAY)   # politeness, per-host only
        r = check_url(opener, tracker, u)
        results[u] = r
        progress.tick(r["status"])
    return results


# Reporting

def _load_previous():
    if not REPORT_JSON.exists():
        return {}
    try:
        data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
        return {r["url"]: r["status"] for r in data.get("results", [])}
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return {}


def _print_group(title, rows, show_final=False):
    if not rows:
        return
    print(f"\n  {title} ({len(rows)}):\n")
    for r in rows:
        status = r["status"] + (f" ({r['code']})" if r.get("code") else "")
        print(f"    {status:<18} {r['url']}")
        if r.get("note"):
            print(f"        {r['note']}")
        if show_final and r.get("final_url") and r["final_url"] != r["url"]:
            print(f"        now at: {r['final_url']}")
        for row in r["rows"]:
            print(f"        - [{row['source']}] {row['surgery_type']} @ {row['source_org']}")
        print()


def run(args):
    entries = load_entries()

    if args.filter:
        needle = args.filter.lower()
        entries = [e for e in entries
                   if needle in e["url"].lower()
                   or needle in e["source_org"].lower()
                   or needle in e["surgery_type"].lower()]

    previous = _load_previous()

    if args.failed:
        stale = {u for u, s in previous.items() if s in PROBLEM}
        if not stale:
            print("\nNo failures recorded in the last run; nothing to recheck.\n")
            return 0
        entries = [e for e in entries if e["url"] in stale]

    if not entries:
        print("\nNo URLs matched; nothing to check.\n")
        return 0

    # One fetch per unique URL; shared PDFs (documented in CLAUDE.md) map back to
    # every catalog row that uses them.
    by_url = defaultdict(list)
    for e in entries:
        by_url[e["url"]].append(e)

    by_host = defaultdict(list)
    for url in by_url:
        by_host[urllib.parse.urlsplit(url).netloc.lower()].append(url)

    skip_domains = {d.lower() for d in (args.skip or [])}

    print("\nRehabProtocols.com link checker")
    print(f"  {len(entries)} catalog rows | {len(by_url)} unique URLs | "
          f"{len(by_host)} hosts | {HOST_WORKERS} hosts in parallel\n")

    progress = Progress(len(by_url))
    started = time.time()
    results = {}

    with ThreadPoolExecutor(max_workers=HOST_WORKERS) as pool:
        futures = [pool.submit(check_host, host, urls, make_ssl_context(),
                               progress, skip_domains)
                   for host, urls in by_host.items()]
        for fut in futures:
            results.update(fut.result())

    elapsed = time.time() - started
    print()

    merged = []
    for url, rows in by_url.items():
        r = dict(results[url])
        r["url"] = url
        r["rows"] = sorted(rows, key=lambda x: (x["source"], x["source_org"],
                                                x["surgery_type"]))
        merged.append(r)

    # Deterministic order so two runs diff cleanly
    merged.sort(key=lambda r: (r["rows"][0]["source"], r["rows"][0]["source_org"],
                               r["rows"][0]["surgery_type"], r["url"]))

    counts = {s: 0 for s in ALL_STATUSES}
    for r in merged:
        counts[r["status"]] += 1

    print("=" * 80)
    print(f"  {len(merged)} unique URLs ({len(entries)} rows) in {elapsed:.0f}s | "
          f"{counts[OK]} OK | {counts[REDIRECT_PERM]} moved | "
          f"{counts[REDIRECT_TEMP]} temp-redirect | {counts[WRONG_TYPE]} WRONG TYPE | "
          f"{counts[BROKEN]} BROKEN | {counts[WARN]} warn | "
          f"{counts[TIMEOUT_S]} timeout | {counts[ERROR]} error | "
          f"{counts[SKIPPED]} skipped")
    print("=" * 80)

    newly = [r for r in merged
             if r["status"] in FAILING and previous.get(r["url"]) not in (None, *FAILING)]
    if newly:
        print(f"\n  !! NEWLY BROKEN SINCE LAST RUN ({len(newly)}) !!\n")
        for r in newly:
            print(f"    {r['url']}\n"
                  f"        was {previous.get(r['url'], 'unknown')}, now {r['status']}")
        print()

    _print_group("PERMANENTLY MOVED - update the CSV",
                 [r for r in merged if r["status"] == REDIRECT_PERM], show_final=True)
    _print_group("TEMPORARY REDIRECTS - informational, do not edit the CSV",
                 [r for r in merged if r["status"] == REDIRECT_TEMP], show_final=True)

    attention = [r for r in merged if r["status"] in PROBLEM]
    if attention:
        order = {BROKEN: 0, WRONG_TYPE: 1, TIMEOUT_S: 2, ERROR: 3, WARN: 4}
        attention.sort(key=lambda r: (order[r["status"]], r["url"]))
        _print_group("NEEDS ATTENTION", attention)
    else:
        print("\n  All links healthy.\n")

    REPORT_JSON.write_text(json.dumps({
        "date":    str(date.today()),
        "elapsed": round(elapsed, 1),
        "rows":    len(entries),
        "unique":  len(merged),
        "counts":  counts,
        "results": merged,
    }, indent=2), encoding="utf-8")
    print(f"  Report written to {REPORT_JSON.name}\n")

    return 1 if any(counts[s] for s in FAILING) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check all RehabProtocols.com external links")
    parser.add_argument("--filter", metavar="TEXT",
                        help="only check URLs whose link, org, or name contains TEXT")
    parser.add_argument("--failed", action="store_true",
                        help="recheck only the URLs that failed in the last run")
    parser.add_argument("--skip", action="append", metavar="DOMAIN",
                        help="temporarily skip a domain (repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="deprecated; link-report.json is always written")
    try:
        sys.exit(run(parser.parse_args()))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(2)
