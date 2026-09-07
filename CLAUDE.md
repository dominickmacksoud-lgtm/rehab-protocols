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
| `protocols/**` | Auto-generated static pages (887 protocol + 241 hub + 1 index) |
| `protocol-slugs.csv` | **URL contract** — auto-managed, never hand-edit (see below) |
| `topics.csv` | Hand-curated surgery-topic taxonomy |
| `sitemap.xml` | Auto-generated — do not hand-edit |
| `rp_*.py` | Generator modules imported by `generate-protocols.py` |
| `rp_verify.py` | Read-only checker for pages, links, JSON-LD, ledger, sitemap |
| `terms-of-use/index.html` | Legal terms page at /terms-of-use/ |
| `check-links.py` | Link health checker — verifies every URL in both CSVs (see below) |
| `test-check-links.py` | Offline regression tests for the link checker — run after editing it |
| `link-issue.py` | Turns `link-report.json` into the weekly GitHub issue body, with verified Wayback suggestions (see below) |
| `wayback-repoints.csv` | Revert ledger for protocols repointed at web.archive.org (see below) |

## Data Pipeline

`protocols-import.csv` → `python generate-protocols.py` → `protocols.js`

CSV has 13 columns: Body Region, Body Region Display, Surgery Category, Surgery Type, Source Organization, Surgeon(s)/Author(s), Protocol URL, Publication Date, Cataloged Date, WB Status, Key Restrictions, Timeline/Phases, Notes

After editing CSV, always run `python generate-protocols.py` and commit the changed
files. One command still does everything; it now also writes `protocols/**`,
`protocol-slugs.csv`, and `sitemap.xml`, so expect more files in `git status`.

```
python generate-protocols.py                    # everything
python generate-protocols.py --skip-pages       # protocols.js only (fast)
python generate-protocols.py --emit-topics-skeleton  # draft topics.csv
python rp_verify.py                             # check the result
```

Then run `python rp_verify.py` before committing. It is read-only and takes a few
seconds. Also confirm idempotency: run the generator twice and check that
`git status --porcelain` is empty on the second run.

### The slug ledger — `protocol-slugs.csv`

This file is the site's URL contract. Every protocol page URL is pinned here and,
once allocated, never changes. **Never hand-edit it, and never delete and
regenerate it** — doing so can reassign hundreds of URLs at once, 404-ing pages
that Google has already indexed.

Identity is `sha1(Protocol URL + Surgery Type)`, which is a verified primary key
across all rows. Row order deliberately plays no part: the CSV is hand-edited and
periodically re-sorted, and a position-derived slug would change every URL below
an inserted row. Reordering the CSV or inserting rows at the top is verified to
move zero existing URLs.

Removing a row from the CSV marks its ledger entry `retired` and reserves that
slug forever, so a future protocol cannot inherit a dead URL.

If you edit a Protocol URL or Surgery Type on an existing row, the key changes and
the generator reports it as one retirement plus one new page — the old URL will
404. It prints a `possible renames?` note when it sees that pattern. To carry the
existing URL across, run `python generate-protocols.py --rekey OLDPID=NEWPID`.

**The generator does not delete retired pages.** Removing a row marks the ledger
entry `retired` and drops it from `protocols.js` and `sitemap.xml`, but the
already-written `protocols/<topic>/<slug>/index.html` stays on disk and keeps
being served — pointing at whatever dead source made you remove the row. There is
no prune step anywhere in `rp_pages.py`. After retiring a protocol, delete its
directory by hand and re-run `rp_verify.py`:

```
git rm -r protocols/<topic>/<slug>
python rp_verify.py
```

The slug stays reserved in the ledger either way, so nothing can inherit the URL.

### Curating `topics.csv`

Hand-maintained. Maps raw `Surgery Category` values onto the hub pages under
`/protocols/<topic>/`. Columns: `topic_slug, display_name, h1, region, status,
aliases, intro`.

`status` is one of:
- `hub` — indexable hub page (needs 3+ protocols)
- `noindex` — rendered and crawlable but `noindex,follow`; used for thin topics
- `merge:<slug>` — alias-only, rows resolve to `<slug>`
- `exclude` — never a topic; rows fall through to their Surgery Type

Catch-all categories (`Non-Operative`, `Surgical`, `Knee`, `Total Joint
Replacement`) are `exclude` on purpose. Excluding them is what splits Total Joint
Replacement into Total Hip and Total Knee, since nobody searches the merged term.
Leave `intro` blank to get a synthesized factual paragraph, or write your own.

### Region page sentinels

The 7 region pages contain `<!-- RP:PROTOCOL-LIST:START/END -->` and
`<!-- RP:TOPIC-LINKS:START/END -->` markers. The generator replaces only what is
between them; the hand-written intro paragraph on each page sits outside and is
never overwritten. If a sentinel goes missing the generator warns rather than
failing silently.

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

After changing `check-links.py`, run `python test-check-links.py` — 9 offline cases
against a localhost server, ~2 seconds, no network. It pins the classification rules
that are easy to break by accident (soft-404 vs. interstitial, HEAD-hostile fallback,
mislabeled content types, permanent vs. temporary redirects).

### Weekly automation

Link health runs in two halves, both on Mondays:

1. **Detector**, `.github/workflows/link-check.yml`, 09:00 UTC. Runs the checker,
   then `python link-issue.py` reads `link-report.json` and files or refreshes one
   issue labeled `link-check` (title `Link health: N broken, M moved (date)`),
   closing it automatically once everything passes. Only BROKEN, WRONG_TYPE and
   REDIRECT_PERM trigger an issue; WARN/TIMEOUT/ERROR are listed collapsed because
   the Actions IP range hits bot walls that a browser does not. For each broken
   URL it asks the Wayback availability API for the latest capture, rewrites it in
   the `id_` form, and verifies it through `check_url` so the suggestion is known
   to serve a PDF. The previous week's report is carried in the Actions cache so
   the issue can say which failures are new. `issue-body.md` and
   `link-report.previous.json` are its gitignored scratch files.
2. **Triage**, a claude.ai routine named "Link health triage" (Sonnet 5), 11:00
   UTC. Reads the open issue, searches the source org's own site for a
   republished copy, verifies candidates through the checker, computes the
   `--rekey` argument, and posts ONE comment with replacement URLs and the exact
   commands. It is advisory only: it never edits, commits, pushes, or opens PRs.
   Manage it at https://claude.ai/code/routines.

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

## Archived (Wayback) protocol links

13 protocols point at `web.archive.org` captures rather than the hospital's own
site (down from 82; see the restoration note below). In August 2026 Mass General Brigham retired the MGH and Brigham and Women's
PDF asset trees in a CMS migration: every
`massgeneral.org/assets/**` and `brighamandwomens.org/assets/**` protocol PDF
began 301-ing to a generic marketing page. The documents were not withdrawn on
clinical grounds — the whole tree went at once, index page included — so they were
repointed at their last good capture rather than deleted.

**Archived URLs must use the `id_` modifier** — `/web/<timestamp>id_/<original-url>`.
The plain `/web/<timestamp>/` form content-negotiates: browsers and curl get the
PDF, but urllib (and therefore `check-links.py`) gets Wayback's HTML toolbar page
instead, so every archived link reads as a broken PDF forever. Verify any new
archive.org link through the checker's own code path, not curl — curl cannot see
this failure. `id_` serves the archived file itself and returns `application/pdf`.

`wayback-repoints.csv` is the revert ledger: `original_url`, `wayback_url`,
`snapshot_date`, `snapshot_timestamp`, `surgery_type`, `source_org`,
`repointed_on`. `original_url` holds the **exact** value that was in
`protocols-import.csv`, which is what a revert must write back and what the slug
ledger's pid is derived from — not the archive's normalized copy of it, which
differs in case.

If MGB republishes, revert by writing `original_url` back over `wayback_url` in
`protocols-import.csv`, then regenerate **with rekeys**, since Protocol URL is
half the identity hash:

```
python -c "import csv,importlib.util as u;s=u.spec_from_file_location('r','rp_slugs.py');m=u.module_from_spec(s);s.loader.exec_module(m);[print(f'--rekey {m.pid(r[\"wayback_url\"],r[\"surgery_type\"])}={m.pid(r[\"original_url\"],r[\"surgery_type\"])}',end=' ') for r in csv.DictReader(open('wayback-repoints.csv',newline='',encoding='utf-8'))]"
```

Without `--rekey`, changing 82 Protocol URLs retires 82 slugs and allocates 82 new
ones, 404-ing every indexed page. Confirm the generator reports `content updated`,
not a matching count of `new` and `retired`.

One protocol, MGH's Lower Trapezius Tendon Transfer, had no capture in the Wayback
CDX index at all and was removed instead.

### Restoration, 2026-09-06

Mass General Brigham republished the MGH protocols inside its new site's asset
store: `https://www.massgeneralbrigham.org/content/dam/unified-xwalk/pdf/patient-education/english/<file>.pdf`,
mostly under the original filenames. The patient-education page lists that
folder through one JSON endpoint, which is the fast way to enumerate it:

```
https://www.massgeneralbrigham.org/bin/mgb/pdflist?path=/content/dam/unified-xwalk/pdf/patient-education/english
```

69 MGH rows were repointed at the live URLs (with `--rekey`, so every page kept
its URL; the generator reported content updates, not retirements), their
`[Archived copy ...]` notes stripped, and their rows removed from
`wayback-repoints.csv`. Still archived, deliberately:

- **12 Brigham and Women's rows.** Their documents were not republished. The
  folder's THA, TKA, rTSA, TSA, hip arthroscopy and ACL PDFs are the MGH
  documents, already claimed by MGH rows. Pointing a Brigham row at one would
  misattribute the source, so they stay on Wayback until Brigham's own files
  reappear. Re-run the endpoint above and match on the original filenames in
  `wayback-repoints.csv` to check.
- **MGH pediatric ACL reconstruction.** Listed in the folder tree but returns
  404 on both hosts, so it is unpublished.

## Usage tags (Popular, Trending, Most planned, New)

`popularity.json` → `rp_signals.py` → a `tags` array on each protocols.js entry.
Cards badge `popular` and `new`; the homepage Highlights filter offers all four
and hides any button whose tag has no protocols yet.

- `popularity.json` is **auto-managed**: `.github/workflows/popularity.yml` runs
  `ga-popularity.py` every Monday, which pulls 28-day and 7-day protocol page
  views plus `/treatment-planner/?p=` selections from Google Analytics (built-in
  dimensions only, no custom definitions), then regenerates and pushes. It
  needs two repository secrets, `GA4_PROPERTY_ID` and `GA4_SA_KEY`; without
  them it leaves the file alone and only the `new` tag refreshes.
- Thresholds live in `rp_signals.py`, not the export script, so tags are a pure
  function of the committed data. `new` = catalogued within 60 days, from the
  CSV's Cataloged Date (mixed formats, parsed) falling back to the ledger's
  first_seen. Because `new` depends on today's date, the generator's output
  drifts as protocols age out; the weekly workflow run is what keeps it current.
- `python ga-popularity.py --selftest` exercises the path parsing offline.

## Session Handoff

At the end of any work session (when asked to "wrap up" or "finish"):

1. Run `git status` and `git diff --stat` to review what changed.
2. Stage, commit with a descriptive message, and push.
3. Output a handoff summary covering: files changed, commits made, what's next, and any blockers.
