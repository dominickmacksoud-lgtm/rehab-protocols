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
| `rp_*.py` | Generator modules imported by `generate-protocols.py` |
| `rp_verify.py` | Read-only checker for pages, links, JSON-LD, ledger, sitemap |
| `protocols/**` | Auto-generated static pages (one per protocol, plus topic hubs and an index) |
| `protocol-slugs.csv` | **URL contract** — auto-managed, never hand-edit (see below) |
| `sitemap.xml` | Auto-generated — do not hand-edit |
| `topics.csv` | Hand-curated surgery-topic taxonomy (see below) |
| `protocol-variants.csv` | Hand-curated variant dropdowns (graft type, approach), keyed by **pid** |
| `cpg_pairings.csv` | Hand-curated protocol-to-guideline pairings shown on protocol pages |
| `popularity.json` | Auto-managed GA4 usage data behind the Popular/Trending/Planned tags |
| `ga-popularity.py` | Weekly GA4 export that writes `popularity.json` |
| `search-synonyms.js` | Search synonym map used by `index.html` |
| `treatment-planner.js` | Treatment Planner app (`/treatment-planner/`) |
| `templates/` | Page templates used by the generator |
| `guidelines-import.csv` | Guidelines master data |
| `generate-guidelines.py` | Guidelines generator |
| `terms-of-use/index.html` | Legal terms page at /terms-of-use/ |
| `check-links.py` | Link health checker — verifies every URL in both CSVs (see below) |
| `test-check-links.py` | Offline regression tests for the link checker — run after editing it |
| `link-issue.py` | Turns `link-report.json` into the weekly GitHub issue body, with verified Wayback suggestions (see below) |
| `wayback-repoints.csv` | Revert ledger for protocols repointed at web.archive.org (see below) |

## Data Pipeline

`protocols-import.csv` → `python generate-protocols.py` → `protocols.js`, `protocols/**`,
`protocol-slugs.csv`, `sitemap.xml`, and the region pages.

CSV has 13 columns, in this order: Body Region, Body Region Display, Surgery Category, Surgery Type, Source Organization, Surgeon(s) / Author(s), Protocol URL, Publication Date, Cataloged Date, WB Status, Key Restrictions, Timeline / Phases, Notes

```
python generate-protocols.py                    # everything
python generate-protocols.py --skip-pages       # fast validation only (see warning)
python generate-protocols.py --emit-topics-skeleton  # draft topics.csv
python rp_verify.py                             # check the result
```

**Never commit `protocols.js` from a `--skip-pages` run.** That mode writes it
without each entry's page `path` and usage `tags`, which strips every card's link
and badges. It is fine for a quick validation pass; run the full generator before
committing.

After editing the CSV, run the generator, then `python rp_verify.py` (read-only, a
few seconds), and commit every file they changed. Also confirm idempotency: run the
generator twice and check that `git status --porcelain` is empty on the second run.

**Edit `protocols-import.csv` line by line, never with a whole-file
DictReader/DictWriter round trip.** Three OSMS rows carry more than 13 fields
(unescaped quotes in their Notes), so `csv.DictWriter` raises *after* truncating
the file it opened. A round trip also re-quotes hundreds of untouched rows. To
change a row, parse and rewrite only that line; to add rows, append bytes (the
`/ingest-protocols` command has a tested snippet). The file is bare-LF, no BOM,
one record per line.

**Known expected generator warnings.** Neither needs action:
- `Shares URL with row N but different Surgery Type` (21 rows). One PDF covers
  several approaches or graft types: MGH ACL, Lahey THA, University Hospitals ACL
  and hip arthroscopy, nine UW Health hand/upper-extremity PDFs, SOMOS Bankart,
  and SAM meniscus repair.
- `topic would move X -> Y; keeping pinned URL` (about 30, full runs only).
  `topics.csv` has been refined since those pages were allocated; the ledger keeps
  the original topic so the URL never changes. This is the ledger working.

### The slug ledger — `protocol-slugs.csv`

This file is the site's URL contract. Every protocol page URL is pinned here and,
once allocated, never changes. **Never hand-edit it, and never delete and
regenerate it** — doing so can reassign hundreds of URLs at once, 404-ing pages
that Google has already indexed.

Identity is `sha1(Protocol URL + Surgery Type)` (the pid), a verified primary key
across all rows. Row order plays no part, so reordering the CSV or inserting rows
anywhere moves zero existing URLs.

Removing a row from the CSV marks its ledger entry `retired` and reserves that
slug forever, so a future protocol cannot inherit a dead URL.

If you edit a Protocol URL or Surgery Type on an existing row, the pid changes and
the generator reports it as one retirement plus one new page — the old URL will
404. It prints a `possible renames?` note when it sees that pattern. To carry the
existing URL across, run `python generate-protocols.py --rekey OLDPID=NEWPID`
(repeat `--rekey` once per row). Compute pids from the repo root with
`python -c "import rp_slugs; print(rp_slugs.pid(URL, SURGERY_TYPE))"`. A correct
rekey shows as `content updated` in the generator output, not as a matching count
of `new` and `retired`.

**After a rekey, update `protocol-variants.csv`.** It is keyed by pid, so a rekeyed
row silently loses its variant dropdown. The generator warns
`protocol-variants.csv line N: pid ... matches no protocol`; replace the old pid
with the new one.

**The generator does not delete retired pages.** Removing a row drops it from
`protocols.js` and `sitemap.xml`, but the already-written
`protocols/<topic>/<slug>/index.html` stays on disk and keeps being served. After
retiring a protocol, delete its directory by hand and re-run `rp_verify.py`:

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

Catch-all categories are excluded on purpose. `Non-Operative`, `Surgical`, `Knee`,
`Other` and `General` are hardcoded in `DEFAULT_EXCLUDE` in `rp_topics.py`; `Total
Joint Replacement` is an `exclude` row in `topics.csv`. Excluding it is what splits
it into Total Hip and Total Knee, since nobody searches the merged term. Leave
`intro` blank to get a synthesized factual paragraph, or write your own.

### Region page sentinels

The 7 region pages contain `<!-- RP:PROTOCOL-LIST:START/END -->` and
`<!-- RP:TOPIC-LINKS:START/END -->` markers. The generator replaces only what is
between them; the hand-written intro paragraph on each page sits outside and is
never overwritten. If a sentinel goes missing the generator warns rather than
failing silently.

## Guidelines Pipeline

`guidelines-import.csv` → `python generate-guidelines.py` → `guidelines.js`, plus
`guidelines-structured-data.js`, the JSON-LD block in `guidelines/index.html`, and
the guideline count in `about/index.html`.

CSV has 9 columns, in this order: Condition, Body Region, Body Region Display, Issuing Organization, Publication Date, Guideline URL, Key Recommendations, Notes, Cataloged Date

After editing the CSV, run `python generate-guidelines.py` and commit every file it
changed. Never edit `guidelines.js` manually. The guidelines page lives at
`guidelines/index.html` and references `../styles.css` and `../guidelines.js`.

## Ingestion (protocols and guidelines)

`/ingest-protocols` and `/ingest-guidelines` hold the step-by-step procedure and
tested snippets. These rules apply to both:

- When given a URL or PDF, use `pdfplumber` via Bash for extraction **first** — do not attempt WebFetch on PDFs. Use stdlib urllib to download; `import requests` fails from the repo root (see Link Checking).
- Go straight to extraction → CSV append → generate → commit → push. No enumeration or confirmation step needed.
- Do not silently filter or exclude entries — add all candidates found in the source (other than the completeness guard below).
- Run the generator and verify no unexpected errors before committing.

Protocols only:
- Completeness guard: if pdfplumber extracts under ~200 characters (image-only scan) or the protocol text ends mid-phase / is missing its later phases, do NOT add it to the CSV — report the rejected PDF and why instead. (Past incidents: image-only and incomplete PDFs reached production and needed removal commits.)
- Body Region Display must be one of the canonical values: Shoulder, Knee, Hip, Spine, Ankle/Foot, Elbow, Wrist/Hand, Leg, Multiple, Head. The generator warns on any other value — fix the CSV rather than ignoring the warning (variant spellings fragment the category filter). Guidelines use their own values, including `Other`.

## Link Checking

`python check-links.py` verifies every URL in both CSVs. About 970 URLs, about 3 min.

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
  matches a dead-page marker. Also fix the CSV.
- **REDIRECT_PERM** — a 301/308. The link still works, but update the CSV to the
  final URL (with a rekey). A 302/307 (`REDIRECT_TEMP`) does not call for an edit.
- **WARN** — 403 bot walls, rate limits, and download interstitials (e.g. PMC's
  "Preparing to download" page). Verify in a browser; usually fine. Does not fail the run.

After changing `check-links.py`, run `python test-check-links.py` — offline cases
against a localhost server, ~2 seconds, no network. It pins the classification rules
that are easy to break by accident (soft-404 vs. interstitial, HEAD-hostile fallback,
mislabeled content types, permanent vs. temporary redirects).

To verify a single URL the way the checker does (curl can disagree):

```
python -c "import importlib.util as u;s=u.spec_from_file_location('c','check-links.py');m=u.module_from_spec(s);s.loader.exec_module(m);o,t=m.make_opener(m.make_ssl_context());print(m.check_url(o,t,'URL'))"
```

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
   Manage it at https://claude.ai/code/routines. It runs in the "Full Network"
   cloud environment (the Default one blocks all outbound traffic). Even there,
   web.archive.org resets connections from the sandbox, so Wayback captures are
   verified by the detector, not the routine. The sandbox has no `gh`; the
   routine uses the GitHub MCP tools instead. **Its prompt tells it to read this
   file's slug ledger, archived Wayback links and 2026-09-06 restoration
   sections, so keep those headings and their rules intact.**

Three things here are deliberate and should not be "cleaned up":
1. **stdlib urllib, not requests/httpx.** `requests` cannot be imported from the repo
   root at all — the site has a real page at `requests/index.html` that shadows the
   package. httpx was tried and reverted: ~105 URLs answer 200 to urllib but 403 to
   httpx. Do not swap the transport without re-running a full check and comparing 403s.
2. **Legacy TLS renegotiation is enabled.** lahey.org (33 URLs) runs an old TLS stack
   that OpenSSL 3 rejects outright, so it is not "bot-blocked".
3. **No domain skip list.** Every URL gets checked. Use `--skip <domain>` for a
   temporary, explicit exemption instead of hardcoding one.

## Repointing a source that moved its PDFs

Hospitals migrate their sites wholesale (MGB in 2026-08, UVA in 2026-11), so a whole
organization's links break at once. Repoint rather than delete; a dead link is
usually a CMS move, not a withdrawn protocol.

1. Find the republished copies on the **same organization's** site. Never point a
   row at another organization's document, even for the same surgery.
2. Match each row to its new document by filename or link text, then download the
   PDF and confirm its title, procedure and completeness against the row.
3. Verify every new URL with the `check_url` one-liner above.
4. Swap old URL for new with a byte-level replace in `protocols-import.csv` (assert
   each old URL occurs once). Do not round-trip the CSV.
5. Compute one `--rekey OLDPID=NEWPID` per row from the old and new URL, then
   regenerate with all of them. Confirm `content updated`, not `new`/`retired`.
6. Fix any stale pid in `protocol-variants.csv`, run `rp_verify.py`, check
   idempotency, and re-run `check-links.py --filter <domain>`.
7. Anything not republished goes to its Wayback capture (next section).

Per-source notes:
- **UVA (2026-11-07).** Orthopaedics moved under `med.virginia.edu/clinical/`; PDFs
  are `https://brand.uvahealth.com/api/asset/<token>/download` links on the
  department pages (`.../sports-medicine/protocols`,
  `.../hand-and-upper-extremity/post-operative-rehabilitation`,
  `.../trauma/clinic-information/trauma-protocols`). Each document is also on
  `.../orthopaedic-education/protocols` under a *different* token; the CSV uses the
  department-page tokens. The URL carries no filename, so match on link text.
  Achilles Tendon Repair was not republished and is on Wayback.
- **MGB.** See the restoration section below.

## Archived (Wayback) protocol links

14 protocols point at `web.archive.org` captures rather than the hospital's own
site: 12 Brigham and Women's rows, MGH pediatric ACL, and UVA Achilles. In August
2026 Mass General Brigham retired the MGH and Brigham and Women's PDF asset trees in
a CMS migration (every `massgeneral.org/assets/**` and `brighamandwomens.org/assets/**`
PDF began 301-ing to a generic marketing page), so 82 rows were repointed at their
last good capture rather than deleted. One protocol, MGH's Lower Trapezius Tendon
Transfer, had no capture at all and was removed.

**Archived URLs must use the `id_` modifier** — `/web/<timestamp>id_/<original-url>`.
The plain `/web/<timestamp>/` form content-negotiates: browsers and curl get the
PDF, but urllib (and therefore `check-links.py`) gets Wayback's HTML toolbar page
instead, so every archived link reads as a broken PDF forever. Verify any new
archive.org link through the checker's own code path, not curl — curl cannot see
this failure. `id_` serves the archived file itself and returns `application/pdf`.
Find captures with the CDX API
(`https://web.archive.org/cdx/search/cdx?url=<url>&output=json&filter=statuscode:200&limit=-3`);
the availability API rate-limits quickly.

Each archived row gets an `[Archived copy. ...]` note at the end of its Notes field,
and a row in `wayback-repoints.csv`, the revert ledger: `original_url`, `wayback_url`,
`snapshot_date`, `snapshot_timestamp`, `surgery_type`, `source_org`,
`repointed_on`. `original_url` holds the **exact** value that was in
`protocols-import.csv`, which is what a revert must write back and what the slug
ledger's pid is derived from — not the archive's normalized copy of it, which
differs in case.

If a source republishes, revert by writing `original_url` back over `wayback_url` in
`protocols-import.csv`, strip the archived note, remove the ledger row, then
regenerate **with rekeys**, since Protocol URL is half the identity hash. This
prints the rekeys for every row still in the ledger (trim to the rows you revert):

```
python -c "import csv,importlib.util as u;s=u.spec_from_file_location('r','rp_slugs.py');m=u.module_from_spec(s);s.loader.exec_module(m);[print(f'--rekey {m.pid(r[\"wayback_url\"],r[\"surgery_type\"])}={m.pid(r[\"original_url\"],r[\"surgery_type\"])}',end=' ') for r in csv.DictReader(open('wayback-repoints.csv',newline='',encoding='utf-8'))]"
```

If the republished URL differs from `original_url`, rekey from `wayback_url` to the
new URL instead.

### Restoration, 2026-09-06

Mass General Brigham republished the MGH protocols inside its new site's asset
store: `https://www.massgeneralbrigham.org/content/dam/unified-xwalk/pdf/patient-education/english/<file>.pdf`,
mostly under the original filenames. The patient-education page lists that
folder through one JSON endpoint, which is the fast way to enumerate it:

```
https://www.massgeneralbrigham.org/bin/mgb/pdflist?path=/content/dam/unified-xwalk/pdf/patient-education/english
```

69 MGH rows were repointed at the live URLs with `--rekey`. Still archived, deliberately:

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
- Because that workflow pushes to `master` every Monday, a local branch started
  before then will be rejected on push. Rebase; if `protocols.js` or `sitemap.xml`
  conflict, take either side and re-run the generator rather than merging by hand.
- Thresholds live in `rp_signals.py`, not the export script, so tags are a pure
  function of the committed data. `new` = catalogued within 60 days, from the
  CSV's Cataloged Date (mixed formats, parsed) falling back to the ledger's
  first_seen. Because `new` depends on today's date, the generator's output
  drifts as protocols age out; the weekly workflow run is what keeps it current.
- `python ga-popularity.py --selftest` exercises the path parsing offline.

## Session Handoff

When asked to "wrap up" or "finish", follow `.claude/commands/handoff.md`
(review changes, commit, push, then summarize files changed, commits, what's
next, and blockers).
