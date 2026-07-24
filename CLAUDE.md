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
| `check-links.py` | Link health checker — verifies every URL in both CSVs (see below) |

## Data Pipeline

`protocols-import.csv` → `python generate-protocols.py` → `protocols.js`

CSV has 13 columns: Body Region, Body Region Display, Surgery Category, Surgery Type, Source Organization, Surgeon(s)/Author(s), Protocol URL, Publication Date, Cataloged Date, WB Status, Key Restrictions, Timeline/Phases, Notes

After editing CSV, always run `python generate-protocols.py` and commit both files.

Known expected generator warnings: MGH ACL protocol (one PDF covers BPTB, Hamstring, and Allograft variants — same URL, different Surgery Types), and Lahey Hospital THA variants (one PDF covers multiple approaches). These are intentional shared-URL entries.

## Protocol Ingestion

- When given a URL or PDF, use `pdfplumber` via Bash for extraction **first** — do not attempt WebFetch on PDFs.
- Completeness guard: if pdfplumber extracts under ~200 characters (image-only scan) or the protocol text ends mid-phase / is missing its later phases, do NOT add it to the CSV — report the rejected PDF and why instead. (Past incidents: image-only and incomplete PDFs reached production and needed removal commits.)
- Body Region Display must be one of the canonical values: Shoulder, Knee, Hip, Spine, Ankle/Foot, Elbow, Wrist/Hand, Leg, Multiple, Head. The generator warns on any other value — fix the CSV rather than ignoring the warning (variant spellings fragment the category filter).
- Go straight to extraction → CSV append → generate → commit → push. No enumeration or confirmation step needed.
- Do not silently filter or exclude protocols (other than the completeness guard above) — add all candidates found in the source.
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

## Link Checking

`python check-links.py` verifies every URL in both CSVs. ~900 URLs, ~2.5 min.

```
python check-links.py                    # everything
python check-links.py --filter lahey     # one org/domain (fast fix-verify loop)
python check-links.py --failed           # only what failed last run
```

Exit codes: `0` clean, `1` broken links found, `2` script error. Results land in
`link-report.json` (gitignored), which also powers `--failed` and the
"newly broken since last run" diff.

Statuses worth knowing:
- **BROKEN** — real HTTP failure. Fix the CSV.
- **WRONG_TYPE** — a `.pdf` URL returned 200 but served an HTML page whose text
  matches a dead-page marker. Also fix the CSV; the old checker reported these as OK.
- **WARN** — 403 bot walls, rate limits, and download interstitials (e.g. PMC's
  "Preparing to download" page). Verify in a browser; usually fine. Does not fail the run.

Three things here are deliberate and should not be "cleaned up":
1. **stdlib urllib, not requests/httpx.** `requests` cannot be imported from the repo
   root at all — the site has a real page at `requests/index.html` that shadows the
   package. httpx was tried and reverted: ~105 URLs answer 200 to urllib but 403 to
   httpx. Do not swap the transport without re-running a full check and comparing 403s.
2. **Legacy TLS renegotiation is enabled.** lahey.org (33 URLs) runs an old TLS stack
   that OpenSSL 3 rejects outright. These were previously blanket-skipped as
   "bot-blocked", which was a misdiagnosis.
3. **No domain skip list.** Every URL gets checked. Use `--skip <domain>` for a
   temporary, explicit exemption instead of hardcoding one.

## Session Handoff

At the end of any work session (when asked to "wrap up" or "finish"):

1. Run `git status` and `git diff --stat` to review what changed.
2. Stage, commit with a descriptive message, and push.
3. Output a handoff summary covering: files changed, commits made, what's next, and any blockers.
