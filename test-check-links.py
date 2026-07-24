#!/usr/bin/env python3
"""
test-check-links.py - regression tests for check-links.py classification logic.

Runs offline in ~2 seconds against a throwaway localhost server, so it needs no
network and cannot be thrown off by a real site changing its behaviour.

    python test-check-links.py        # exit 0 = all passed, 1 = something regressed

Each case pins down a decision that is easy to undo by accident. The two that
matter most:

  * soft-404 vs. interstitial. A .pdf URL that answers 200 with HTML is either a
    dead link wearing a page costume (must fail the run) or a download gate like
    PMC's "Preparing to download" (must NOT fail the run -- a browser gets the PDF
    fine). Collapsing these two into one status is what makes a link checker cry
    wolf until people stop reading it.
  * headers are not evidence. Servers mislabel PDFs, and servers reject HEAD on
    URLs that GET perfectly well. Both are settled by looking at the actual bytes.
"""

import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "check-links.py"

spec = importlib.util.spec_from_file_location("checklinks", TARGET)
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)


# Fixtures

REAL_PDF = b"%PDF-1.4\n" + b"x" * 4000       # valid magic, comfortably over MIN_PDF_BYTES
TINY_PDF = b"%PDF-1.4\n" + b"x" * 50         # valid magic but implausibly small
DEAD_PAGE = b"<html><body>Page not found</body></html>" * 40
INTERSTITIAL = (b"<html><head><title>Preparing to download ...</title></head>"
                b"<body>Please wait</body></html>") * 20

# path -> (status, content-type, body)
ROUTES = {
    "/real.pdf":     (200, "application/pdf", REAL_PDF),
    "/soft404.pdf":  (200, "text/html; charset=utf-8", DEAD_PAGE),
    "/tiny.pdf":     (200, "application/pdf", TINY_PDF),
    "/missing.pdf":  (404, "text/html", b"nope"),
    "/moved.pdf":    (301, None, None),
    "/temp.pdf":     (302, None, None),
    "/headless.pdf": (200, "application/pdf", REAL_PDF),   # but 403s on HEAD, see below
    "/liar.pdf":     (200, "text/plain", REAL_PDF),
    "/interst.pdf":  (200, "text/html; charset=utf-8", INTERSTITIAL),
}

# path -> (expected status, why this case exists)
CASES = {
    "/real.pdf":     (cl.OK, "ordinary healthy PDF"),
    "/soft404.pdf":  (cl.WRONG_TYPE, "200 + HTML naming a dead page must fail the run"),
    "/tiny.pdf":     (cl.WARN, "valid PDF under MIN_PDF_BYTES is probably an error page"),
    "/missing.pdf":  (cl.BROKEN, "a real 404 is broken"),
    "/moved.pdf":    (cl.REDIRECT_PERM, "301/308 means the CSV should be updated"),
    "/temp.pdf":     (cl.REDIRECT_TEMP, "302/307 must NOT invite a CSV edit"),
    "/headless.pdf": (cl.OK, "HEAD rejected with 403, ranged GET rescues it"),
    "/liar.pdf":     (cl.OK, "content-type lies; %PDF magic bytes win"),
    "/interst.pdf":  (cl.WARN, "download gate, not a dead link, so it must not fail"),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _serve(self, with_body):
        path = self.path.split("?")[0]
        if path not in ROUTES:
            self.send_response(404)
            self.end_headers()
            return

        code, ctype, body = ROUTES[path]

        # Mimic the servers that answer GET but slam the door on HEAD.
        if path == "/headless.pdf" and not with_body:
            self.send_response(403)
            self.end_headers()
            return

        if code in (301, 302):
            self.send_response(code)
            self.send_header("Location", "/real.pdf")
            self.end_headers()
            return

        self.send_response(code)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if with_body:
            self.wfile.write(body)

    def do_HEAD(self):
        self._serve(False)

    def do_GET(self):
        self._serve(True)


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    cl.DELAY = 0   # no politeness pause against ourselves
    opener, tracker = cl.make_opener(cl.make_ssl_context())

    print(f"\n  testing {TARGET.name} against {base}\n")
    failures = []

    try:
        for path, (expected, why) in CASES.items():
            got = cl.check_url(opener, tracker, base + path)["status"]
            ok = got == expected
            if not ok:
                failures.append((path, expected, got, why))
            print(f"  {'PASS' if ok else 'FAIL'}  {path:<15} "
                  f"{got if ok else f'{expected} -> {got}':<28} {why}")
    finally:
        server.shutdown()

    print(f"\n  {len(CASES) - len(failures)}/{len(CASES)} passed\n")
    for path, expected, got, why in failures:
        print(f"  {path} expected {expected}, got {got}\n      {why}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
