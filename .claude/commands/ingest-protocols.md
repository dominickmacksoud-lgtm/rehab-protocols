# Ingest Protocols

Given one or more URLs (PDF or web page), add new rehab protocols to the CSV.

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

2. Extract every protocol found in the document. Do not filter by body region or assumed scope.

3. For each protocol, extract all 13 CSV fields:
   - Body Region, Body Region Display, Surgery Category, Surgery Type
   - Source Organization, Surgeon(s)/Author(s), Protocol URL
   - Publication Date, Cataloged Date, WB Status, Key Restrictions, Timeline/Phases, Notes

4. Append rows to `protocols-import.csv` using Python `csv.DictWriter` (preserves quoting and encoding).

5. Run `python generate-protocols.py` and verify no unexpected errors. If the generator prints any ERROR lines or exits non-zero, fix the offending CSV row and re-run before proceeding. Do not commit until the generator exits cleanly.

6. Commit both `protocols-import.csv` and `protocols.js` with a descriptive message, then push.
