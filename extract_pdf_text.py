import urllib.request
import tempfile
import pathlib
import pdfplumber  # pip install pdfplumber

# ── Add PDF URLs here ─────────────────────────────────────────────────────────
URLS = [
    # "https://octanecdn.com/growthortho/growthortho_XXXXXXX.pdf",
]
# ─────────────────────────────────────────────────────────────────────────────

OUT = pathlib.Path("pdf_extracts.txt")

# Browser UA required — octanecdn.com returns 403 without it
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

if not URLS:
    raise SystemExit("No URLs listed. Add PDF URLs to the URLS list at the top of this script.")

with OUT.open("w", encoding="utf-8") as out:
    for i, url in enumerate(URLS, 1):
        print(f"  [{i}/{len(URLS)}] {url.split('/')[-1]}")
        out.write(f"\n{'=' * 60}\nURL: {url}\n{'=' * 60}\n")
        req = urllib.request.Request(url, headers=HEADERS)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        with urllib.request.urlopen(req) as resp, open(tmp_path, "wb") as f:
            f.write(resp.read())
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                out.write(text + "\n")
        pathlib.Path(tmp_path).unlink(missing_ok=True)

print(f"\nExtracted {len(URLS)} PDF(s) → {OUT}")
print("Paste the contents of pdf_extracts.txt into Claude.")
