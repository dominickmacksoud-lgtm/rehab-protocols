# Ingest Protocols

Given one or more URLs (PDF or web page), add new rehab protocols to the CSV.

## Steps

1. For each URL, download using WebFetch. If the content is a PDF or WebFetch returns binary/unusable content, switch immediately to pdfplumber via Bash:
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

2. Extract every protocol found in the document. Do not filter by body region or assumed scope.

3. Before editing any files, output a confirmation table with all candidates:
   | # | Protocol Name | Proposed Body Region | Surgery Type | Source Org |
   Wait for user confirmation and any tag corrections before proceeding.

4. For each confirmed protocol, extract all 13 CSV fields:
   - Body Region, Body Region Display, Surgery Category, Surgery Type
   - Source Organization, Surgeon(s)/Author(s), Protocol URL
   - Publication Date, Cataloged Date, WB Status, Key Restrictions, Timeline/Phases, Notes

5. Append rows to `protocols-import.csv` using Python `csv.DictWriter` (preserves quoting and encoding).

6. Run `python generate-protocols.py` and verify no unexpected errors.

7. Show a summary table of what was added, grouped by body region.

8. Stage changes but do not commit until user confirms the summary looks correct.
