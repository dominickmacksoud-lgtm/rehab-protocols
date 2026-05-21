# RehabProtocols.com

Static HTML/CSS/JS site. No build step. Push to `master` on GitHub (dominickmacksoud-lgtm/rehab-protocols) → live at rehabprotocols.com in ~2 min.

## Key Files

| File | Purpose |
|------|---------|
| `index.html` | Entire app — search, filters, cards, modals, favorites, disclaimer |
| `styles.css` | All styling |
| `protocols-import.csv` | Master data (source of truth — never edit protocols.js manually) |
| `protocols.js` | Auto-generated output |
| `generate-protocols.py` | Only generator — do not delete |
| `terms-of-use/index.html` | Legal terms page at /terms-of-use/ |
| `check-links.py` | Link health checker — verifies all URLs in both CSVs via HTTP HEAD/GET |

## Data Pipeline

`protocols-import.csv` → `python generate-protocols.py` → `protocols.js`

CSV has 13 columns: Body Region, Body Region Display, Surgery Category, Surgery Type, Source Organization, Surgeon(s)/Author(s), Protocol URL, Publication Date, Cataloged Date, WB Status, Key Restrictions, Timeline/Phases, Notes

After editing CSV, always run `python generate-protocols.py` and commit both files.

Known expected generator warnings: MGH ACL protocol (one PDF covers BPTB, Hamstring, and Allograft variants — same URL, different Surgery Types), and Lahey Hospital THA variants (one PDF covers multiple approaches). These are intentional shared-URL entries.

## Protocol Ingestion

- When given a URL or PDF, use `pdfplumber` via Bash for extraction **first** — do not attempt WebFetch on PDFs.
- Go straight to extraction → CSV append → generate → commit → push. No enumeration or confirmation step needed.
- Do not silently filter or exclude protocols — add all candidates found in the source.
- Run the generator and verify no unexpected errors before committing.

## Guidelines Pipeline

`guidelines-import.csv` → `python generate-guidelines.py` → `guidelines.js`

CSV has 9 columns: Condition, Body Region, Body Region Display, Issuing Organization, Publication Date, Cataloged Date, Guideline URL, Key Recommendations, Notes

After editing the CSV, run `python generate-guidelines.py` and commit both files. Never edit `guidelines.js` manually.

The guidelines page lives at `guidelines/index.html` and references `../styles.css` and `../guidelines.js`.

## Guideline Ingestion

- When given a URL or PDF, use `pdfplumber` via Bash for extraction **first** — do not attempt WebFetch on PDFs.
- Go straight to extraction → CSV append → generate → commit → push. No enumeration or confirmation step needed.
- Do not silently filter or exclude guidelines — add all candidates found in the source.
- Run the generator and verify no unexpected errors before committing.

## Session Handoff

At the end of any work session (when asked to "wrap up" or "finish"):

1. Run `git status` and `git diff --stat` to review what changed.
2. Stage, commit with a descriptive message, and push.
3. Output a handoff summary covering: files changed, commits made, what's next, and any blockers.
