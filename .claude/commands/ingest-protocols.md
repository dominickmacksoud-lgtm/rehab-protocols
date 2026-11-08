# Ingest Protocols

Given one or more URLs (PDF or web page), add new rehab protocols to the CSV.
The rules in CLAUDE.md's "Ingestion" section apply (completeness guard,
canonical Body Region Display values, no silent filtering, no confirmation step).

## Steps

1. For each URL, first check it is not already catalogued:
   `grep -F "<URL>" protocols-import.csv`. If it is, report it and skip it.

2. Extract the text. For a PDF (or any URL that downloads a file), run this from
   the repo root. It uses stdlib urllib and the link checker's TLS context, because
   `import requests` fails here (the site's `requests/` page shadows the package)
   and lahey.org needs the checker's legacy-TLS setting:
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
   the snippet above. Apply the completeness guard before going further.

3. Extract every protocol found in the document. Do not filter by body region or assumed scope.

4. For each protocol, fill all 13 CSV fields, in header order:
   Body Region, Body Region Display, Surgery Category, Surgery Type,
   Source Organization, Surgeon(s)/Author(s), Protocol URL, Publication Date,
   Cataloged Date, WB Status, Key Restrictions, Timeline/Phases, Notes.
   Match the existing spelling of the Source Organization if that org is already
   in the CSV. Every claim in the summary fields must be in the source document.

5. Write the new rows as a JSON list of lists (one list of 13 strings per row) to a
   file in the scratchpad, then append them with this snippet. It appends bytes
   only and never rewrites the existing file (a DictReader/DictWriter round trip
   truncates it; see CLAUDE.md). It refuses rows with the wrong field count.
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
   for r in rows:
       assert len(r) == len(header), f'{len(r)} fields, header has {len(header)}: {r[:4]}'
       assert not any('\n' in f or '\r' in f for f in r), 'fields must be single-line'
       w.writerow(r)
   add = buf.getvalue().encode('utf-8').replace(b'\n', nl)
   with open(csv_path, 'ab') as f:
       if raw and not raw.endswith(b'\n'):
           f.write(nl)
       f.write(add)
   print(f'appended {len(rows)} row(s) to {csv_path}')
   " protocols-import.csv "<rows.json>"
   ```

6. Run `python generate-protocols.py`. If it prints ERROR lines, a non-canonical
   Body Region warning, or exits non-zero, fix the row and re-run. The shared-URL
   and `topic would move` warnings listed in CLAUDE.md are expected.

7. Run `python rp_verify.py` and confirm `ALL CHECKS PASSED`.

8. Run `git status`. Stage `protocols-import.csv` and every file the generator
   changed or created (`protocols.js`, `protocols/**`, `protocol-slugs.csv`,
   `sitemap.xml`, region and about pages). Commit with a descriptive message and push.
