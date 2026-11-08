# Ingest Guidelines

Given one or more URLs (PDF or web page), add new clinical practice guidelines to the CSV.
The rules in CLAUDE.md's "Ingestion" section apply (no silent filtering, no
confirmation step). The protocol Body Region Display list does not apply here:
guidelines use `Other` for non-regional guidelines, so reuse a value already in
`guidelines-import.csv`.

## Steps

1. For each URL, first check it is not already catalogued:
   `grep -F "<URL>" guidelines-import.csv`. If it is, report it and skip it.

2. Extract the text. For a PDF (or any URL that downloads a file), run this from
   the repo root. It uses stdlib urllib and the link checker's TLS context, because
   `import requests` fails here (the site's `requests/` page shadows the package):
   ```bash
   python -c "
   import importlib.util as u, io, sys, urllib.request, pdfplumber
   s = u.spec_from_file_location('cl', 'check-links.py'); cl = u.module_from_spec(s); s.loader.exec_module(cl)
   req = urllib.request.Request(sys.argv[1], headers={'User-Agent': cl.USER_AGENT})
   data = urllib.request.build_opener(urllib.request.HTTPSHandler(context=cl.make_ssl_context())).open(req, timeout=60).read()
   with pdfplumber.open(io.BytesIO(data)) as pdf:
       text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
       print(f'[{len(pdf.pages)} pages, {len(text)} chars]')
   print(text)
   " "<URL>"
   ```
   For an HTML page, use WebFetch; if it returns binary or unusable content, use
   the snippet above.

3. Extract every guideline found in the document. Do not filter by body region or assumed scope.

4. For each guideline, fill all 9 CSV fields. Take the exact column names from
   `head -1 guidelines-import.csv`. Note that Cataloged Date is the **last** column.

5. Write the new rows to a file in the scratchpad as a JSON list of objects, one
   object per row, keyed by those exact column names (all 9 keys, string values).
   Then append them with this snippet. It fills columns in the file's own order, so
   key order does not matter, and it refuses any row with a missing or misspelled
   key. It appends bytes only and never rewrites the existing file.
   ```bash
   python -c "
   import csv, io, json, sys
   csv_path, rows_path = sys.argv[1], sys.argv[2]
   raw = open(csv_path, 'rb').read()
   first = raw.split(b'\n', 1)[0]
   nl = b'\r\n' if first.endswith(b'\r') else b'\n'
   header = next(csv.reader([first.decode('utf-8-sig').rstrip('\r')]))
   rows = json.load(open(rows_path, encoding='utf-8'))
   buf = io.StringIO()
   w = csv.writer(buf, lineterminator='\n')
   for d in rows:
       assert set(d) == set(header), f'missing keys {set(header) - set(d)}, unknown keys {set(d) - set(header)}'
       r = [d[h] for h in header]
       assert not any('\n' in f or '\r' in f for f in r), 'fields must be single-line'
       w.writerow(r)
   add = buf.getvalue().encode('utf-8').replace(b'\n', nl)
   with open(csv_path, 'ab') as f:
       if raw and not raw.endswith(b'\n'):
           f.write(nl)
       f.write(add)
   print(f'appended {len(rows)} row(s) to {csv_path}')
   " guidelines-import.csv "<rows.json>"
   ```

6. Run `python generate-guidelines.py` and verify no unexpected errors. If it
   prints ERROR lines or exits non-zero, fix the offending row and re-run.

7. Run `git status`. Stage `guidelines-import.csv` and every file the generator
   changed (`guidelines.js`, `guidelines-structured-data.js`,
   `guidelines/index.html`, `about/index.html`). Commit with a descriptive message and push.
