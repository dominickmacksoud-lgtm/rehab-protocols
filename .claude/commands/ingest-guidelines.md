# Ingest Guidelines

Given one or more URLs (PDF or web page), add new clinical practice guidelines to the CSV.

## Steps

1. For each URL:
   - If the URL ends in `.pdf`, go directly to pdfplumber via Bash:
     ```bash
     python -c "
     import pdfplumber, sys, requests, tempfile, os
     url = sys.argv[1]
     r = requests.get(url)
     with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
         f.write(r.content); path = f.name
     with pdfplumber.open(path) as pdf:
         print('\n'.join(p.extract_text() or '' for p in pdf.pages))
     os.unlink(path)
     " "<URL>"
     ```
   - If the URL is an HTML page, use WebFetch first. If WebFetch returns binary/unusable content, fall back to pdfplumber above.

2. Extract every guideline found in the document. Do not filter by body region or assumed scope.

3. For each guideline, extract all 9 CSV fields:
   - Condition, Body Region, Body Region Display
   - Issuing Organization, Publication Date, Cataloged Date
   - Guideline URL, Key Recommendations, Notes

4. Append rows to `guidelines-import.csv` using Python `csv.DictWriter` (preserves quoting and encoding).

5. Run `python generate-guidelines.py` and verify no unexpected errors. If the generator prints any ERROR lines or exits non-zero, fix the offending CSV row and re-run before proceeding. Do not commit until the generator exits cleanly.

6. Commit both `guidelines-import.csv` and `guidelines.js` with a descriptive message, then push.
