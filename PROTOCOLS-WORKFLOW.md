# Protocols Workflow

This workspace includes the source-of-truth CSV file, a PDF text extractor, and a generator script.

## Files

- `protocols-import.csv` — master protocol metadata source (source of truth)
- `extract_pdf_text.py` — downloads PDF URLs and extracts text to `pdf_extracts.txt` for Claude
- `generate-protocols.py` — Python script that converts the CSV into `protocols.js`

## Adding new protocols (PDF sources)

This is the recommended workflow for adding protocols from PDF links:

1. Paste the PDF URLs into the `URLS` list at the top of `extract_pdf_text.py`.
2. Run the extractor:

```powershell
cd C:\Users\iprom\Documents\my-pt-website
python extract_pdf_text.py
```

3. Paste the contents of the generated `pdf_extracts.txt` file into Claude.
4. Claude extracts all 13 fields and writes an append script — no PDF image rendering needed.
5. Run the append script, then regenerate (see below).

> **Why this matters:** Having Claude fetch and render PDFs as images uses ~4–8× more tokens than
> processing the same content as plain text. With this approach, 20+ protocols can be added in a
> single Claude exchange with no batch-size limits.

## How to regenerate `protocols.js`

1. Update `protocols-import.csv` with new protocol rows (via Claude's append script).
2. Run the generator:

```powershell
cd C:\Users\iprom\Documents\my-pt-website
python generate-protocols.py
```

3. Commit the updated `protocols-import.csv` and `protocols.js`.

## Validation

The generator validates the CSV before writing any output. It will:

- **Abort with errors** if a required column is missing, a URL is blank or malformed, or the same URL appears twice with the same Surgery Type (true duplicate).
- **Warn (but continue)** if Source Organization or Body Region is missing, if Surgery Category and Surgery Type are both blank, or if the same URL appears with different Surgery Types (one PDF covering multiple approaches — verify this is intentional).

If errors are found, `protocols.js` is not updated and the exit code is non-zero.

## Notes

- The generator outputs 13 structured fields per protocol: `url`, `category`, `name`, `type`, `sourceOrganization`, `sourceType`, `surgeons`, `publicationDate`, `wbStatus`, `wbInitial`, `keyRestrictions`, `timelinePhases`, `notes`, `isPdf`.
- `wbInitial` is extracted from `wbStatus` and used for badge color coding on the site.
- `sourceType` is inferred from the URL/org name (academic / hospital / surgeon / clinic).
