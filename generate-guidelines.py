#!/usr/bin/env python3
"""Generates guidelines.js from guidelines-import.csv. Run after any CSV edit."""

import csv
import json
import re
import sys
from pathlib import Path

INPUT  = Path(__file__).parent / "guidelines-import.csv"
OUTPUT = Path(__file__).parent / "guidelines.js"

REQUIRED_COLS = {
    "Condition", "Body Region", "Body Region Display",
    "Issuing Organization", "Publication Date", "Guideline URL",
    "Key Recommendations", "Notes", "Cataloged Date",
}

def abort(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr)

def main():
    if not INPUT.exists():
        abort(f"{INPUT} not found")

    rows = []
    seen_urls = {}

    with open(INPUT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLS - set(reader.fieldnames or [])
        if missing:
            abort(f"CSV missing columns: {missing}")

        errors = []

        for i, row in enumerate(reader, start=2):  # row 1 is header
            url = row["Guideline URL"].strip()
            if not url:
                errors.append(f"Row {i}: empty URL")
                continue
            if not url.startswith(("http://", "https://")):
                errors.append(f"Row {i}: invalid URL (must start with http:// or https://): '{url}'")
                continue

            if url in seen_urls:
                warn(
                    f"Duplicate URL on rows {seen_urls[url]} and {i}: {url}\n"
                    "  Intentional duplicates (e.g. one CPG covering multiple conditions) are allowed."
                )
            seen_urls[url] = i

            rows.append({
                "condition":        row["Condition"].strip(),
                "bodyRegion":       row["Body Region"].strip().lower(),
                "bodyRegionDisplay":row["Body Region Display"].strip(),
                "issuingOrg":       row["Issuing Organization"].strip(),
                "publicationDate":  row["Publication Date"].strip(),
                "catalogedDate":    row["Cataloged Date"].strip(),
                "url":              url,
                "keyRecommendations": row["Key Recommendations"].strip(),
                "notes":            row["Notes"].strip(),
            })

        if errors:
            for e in errors:
                print(f"  ERROR: {e}", file=sys.stderr)
            abort(f"{len(errors)} error(s) — generation aborted")

    js = f"const guidelines = {json.dumps(rows, separators=(',', ':'), ensure_ascii=False)};\n"

    OUTPUT.write_text(js, encoding="utf-8")
    print(f"OK: wrote {len(rows)} guidelines to {OUTPUT.name}")

    # Emit the CollectionPage/ItemList block in full.
    #
    # This previously synced only "numberOfItems" via regex while the nine
    # itemListElement entries stayed hand-written, so the markup claimed 36 items
    # and listed 9 — all nine pointing at the same URL. Generating the whole
    # block keeps the count and the items definitionally in agreement.
    ROOT = Path(__file__).parent
    import rp_data
    import rp_templates as T

    def anchor(row):
        slug = re.sub(r'[^a-z0-9]+', '-', (row['condition'] or '').lower()).strip('-')
        return f"/guidelines/#{slug}" if slug else "/guidelines/"

    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Clinical Practice Guidelines — Rehab Protocols",
        "description": ("Evidence-based clinical practice guidelines from APTA, AAOS, "
                        "JOSPT, and other professional bodies. Free reference tool for "
                        "physical therapists."),
        "url": "https://rehabprotocols.com/guidelines/",
        "inLanguage": "en-US",
        "audience": {"@type": "Audience",
                     "audienceType": "Licensed Physical Therapists and PT Students"},
        "publisher": {"@id": T.ORG_ID},
        "mainEntity": T.item_list(
            [(f"{r['condition']} — {r['issuingOrg']}".strip(' —'), anchor(r)) for r in rows],
            name="Clinical Practice Guidelines Library"),
    }
    block = f'<script type="application/ld+json">{T.escj(collection)}</script>'
    rp_data.splice(ROOT / 'guidelines' / 'index.html', 'GUIDELINES-JSONLD', block,
                   label=f'guidelines ItemList ({len(rows)} items)')

    # Per-guideline MedicalGuideline structured data
    def build_sd_item(row):
        item = {
            "@type": "MedicalGuideline",
            "name": f"{row['condition']} — {row['issuingOrg']}",
            "url": row['url'],
            "inLanguage": "en-US",
            "evidenceLevel": "Clinical Practice Guideline",
            "audience": {"@type": "Audience", "audienceType": "Physical Therapists"},
        }
        if row['condition']:
            item["guidelineSubject"] = {"@type": "MedicalCondition", "name": row['condition']}
        if row['issuingOrg']:
            item["recognizingAuthority"] = {"@type": "Organization", "name": row['issuingOrg']}
        if row['publicationDate']:
            item["guidelineDate"] = row['publicationDate']
        return item

    graph = [build_sd_item(row) for row in rows]
    payload_json = json.dumps({"@context": "https://schema.org", "@graph": graph}, separators=(',', ':'), ensure_ascii=False)
    sd_path = ROOT / 'guidelines-structured-data.js'
    sd_path.write_text(
        f'(function(){{var e=document.createElement("script");'
        f'e.type="application/ld+json";'
        f'e.text={json.dumps(payload_json)};'
        f'document.head.appendChild(e);}})();\n',
        encoding='utf-8',
    )
    print(f"OK: generated guidelines-structured-data.js ({len(graph)} MedicalGuideline items)")

    about_path = ROOT / 'about' / 'index.html'
    about_html = about_path.read_text(encoding='utf-8')
    updated_about, n_about = re.subn(r'(<span class="stat-number" id="about-guideline-count">)\d+(</span>)', rf'\g<1>{len(rows)}\2', about_html)
    if n_about == 0:
        print("WARNING: about-guideline-count pattern matched nothing in about/index.html — count NOT synced")
    elif updated_about != about_html:
        about_path.write_text(updated_about, encoding='utf-8')
        print(f"OK: updated about-guideline-count -> {len(rows)} in about/index.html")

if __name__ == "__main__":
    main()
