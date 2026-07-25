"""Render the static hub, protocol, and topic-index pages under protocols/."""

from collections import Counter, defaultdict

import rp_data
import rp_slugs
import rp_templates as T
import rp_topics
from rp_data import ROOT, REGION_PATHS, normalize, write_text
from rp_templates import esc, escj, truncate

OUT_DIR = ROOT / 'protocols'

# Protocol pages thinner than this are noindex — too little unique content to
# stand on their own, though they stay crawlable and keep passing link equity.
MIN_WORDS_INDEXABLE = 50

FACT_FIELDS = [
    ('WB Status', 'Weight-Bearing'),
    ('Key Restrictions', 'Key Restrictions'),
    ('Timeline / Phases', 'Timeline &amp; Phases'),
    ('Notes', 'Notes'),
    ('Surgeon(s) / Author(s)', 'Surgeon / Author'),
    ('Publication Date', 'Published'),
]


def unique_words(record):
    fields = ['WB Status', 'Key Restrictions', 'Timeline / Phases', 'Notes']
    return len(' '.join(normalize(record.get(f)) for f in fields).split())


def render_breadcrumb(trail):
    parts = []
    for name, path in trail:
        if path:
            parts.append(f'<a href="{esc(path)}">{esc(name)}</a>')
        else:
            parts.append(f'<span aria-current="page">{esc(name)}</span>')
    sep = ' <span class="rp-crumb-sep" aria-hidden="true">&rsaquo;</span> '
    return sep.join(parts)


def render_facts(record):
    rows = []
    for key, label in FACT_FIELDS:
        val = normalize(record.get(key))
        if not val:
            continue
        rows.append(f'        <dt>{label}</dt>\n        <dd>{esc(val)}</dd>')
    return '\n'.join(rows)


def protocol_card(entry):
    """entry: dict with path, name, org, meta."""
    meta = f'<div class="rp-card-meta">{esc(entry["meta"])}</div>' if entry['meta'] else ''
    org = f'<div class="rp-card-org">{esc(entry["org"])}</div>' if entry['org'] else ''
    return (
        f'      <a class="rp-card" href="{esc(entry["path"])}">\n'
        f'        <span class="rp-card-name">{esc(entry["name"])}</span>\n'
        f'        {org}{meta}\n'
        f'      </a>'
    )


def build_intro(display, records, idxs):
    """Synthesize a factual intro sentence from the data."""
    orgs = {normalize(records[i].get('Source Organization')) for i in idxs}
    orgs.discard('')
    years = []
    for i in idxs:
        for tok in normalize(records[i].get('Publication Date')).replace('-', ' ').split():
            if tok.isdigit() and len(tok) == 4:
                years.append(int(tok))
    n = len(idxs)
    # Keep the display name's own casing — lowercasing turns "ACL" into "acl".
    bits = [
        f'{n} {display} rehabilitation protocol{"s" if n != 1 else ""} '
        f'from {len(orgs)} institution{"s" if len(orgs) != 1 else ""}'
    ]
    if years:
        lo, hi = min(years), max(years)
        bits.append(f'published {lo}' + (f'&ndash;{hi}' if hi != lo else ''))
    sentence = ', '.join(bits) + '.'

    wb = Counter(normalize(records[i].get('WB Status')).split(';')[0].split(',')[0].strip()
                 for i in idxs)
    wb.pop('', None)
    if len(wb) > 1:
        sentence += (' Weight-bearing progressions vary by institution &mdash; compare them '
                     'in the table below before selecting a protocol.')
    return sentence


def comparison_table(records, idxs, entries):
    """Cross-institution comparison — the reason a hub outranks any single PDF."""
    rows = []
    for i, entry in zip(idxs, entries):
        wb = truncate(normalize(records[i].get('WB Status')), 90)
        restr = truncate(normalize(records[i].get('Key Restrictions')), 110)
        rows.append(
            '          <tr>\n'
            f'            <th scope="row"><a href="{esc(entry["path"])}">{esc(entry["label"])}</a></th>\n'
            f'            <td>{esc(wb) or "&mdash;"}</td>\n'
            f'            <td>{esc(restr) or "&mdash;"}</td>\n'
            '          </tr>'
        )
    if not rows:
        return ''
    body = '\n'.join(rows)
    return (
        '    <h2 id="compare">Compare by institution</h2>\n'
        '    <div class="rp-table-wrap">\n'
        '      <table class="rp-compare">\n'
        '        <thead>\n'
        '          <tr><th scope="col">Institution</th><th scope="col">Weight-Bearing</th>'
        '<th scope="col">Key Restrictions</th></tr>\n'
        '        </thead>\n'
        '        <tbody>\n'
        f'{body}\n'
        '        </tbody>\n'
        '      </table>\n'
        '    </div>\n'
    )


def sibling_ring(entries, pos, k=8):
    """k neighbours, wrapping around.

    A ring guarantees every protocol receives inbound sibling links. Taking the
    "first k" instead would orphan the tail of every topic.
    """
    n = len(entries)
    if n <= 1:
        return []
    k = min(k, n - 1)
    return [entries[(pos + off) % n] for off in range(1, k + 1)]


def resolve(records, rekey=None):
    """Assign topics and slugs, and write the ledger.

    Split out from generate() so protocols.js can carry each protocol's page path
    without resolving slugs twice (the two must never disagree).
    """
    rp_data.setup_console()

    by_slug, alias_index = rp_topics.load_topics()
    topic_map, members, warnings = rp_topics.assign_topics(records, by_slug, alias_index)
    for w in warnings:
        print(f'  WARNING: {w}')

    idx_of = {id(r): i for i, r in enumerate(records)}
    ledger, assignments, report = rp_slugs.allocate(
        records, lambda r: topic_map[idx_of[id(r)]], rekey=rekey)
    rp_slugs.print_report(report)
    rp_slugs.write_ledger(ledger)

    paths = {}
    for i, record in enumerate(records):
        pid = rp_slugs.pid(record.get('Protocol URL'), record.get('Surgery Type'))
        topic, slug = assignments[pid]
        paths[i] = (f'/protocols/{topic}/{slug}/', topic, slug, pid)

    return {'paths': paths, 'members': members, 'by_slug': by_slug, 'ledger': ledger}


def generate(records, protocols, resolved=None, rekey=None):
    resolved = resolved or resolve(records, rekey=rekey)
    paths = resolved['paths']
    members = resolved['members']
    by_slug = resolved['by_slug']

    head_t = T.tmpl('_head.html.tmpl')
    header = T.load('_header.html')
    footer = T.load('_footer.html')
    disclaimer = T.load('_disclaimer.html')
    protocol_t = T.tmpl('protocol.html.tmpl')
    hub_t = T.tmpl('hub.html.tmpl')
    index_t = T.tmpl('protocols-index.html.tmpl')

    written = 0
    topic_infos = {}

    # ── Hub + protocol pages, topic by topic ─────────────────────────────────
    for topic, idxs in sorted(members.items()):
        meta = rp_topics.topic_meta(topic, by_slug, records, idxs)
        region = meta['region']
        region_path = REGION_PATHS.get(region, '/protocols/')
        topic_infos[topic] = meta

        # Stable display order — never CSV order, so re-sorting the CSV produces
        # no diff in the generated HTML.
        ordered = sorted(idxs, key=lambda i: (paths[i][2], paths[i][0]))
        entries = []
        for i in ordered:
            org = normalize(records[i].get('Source Organization'))
            bits = [b for b in (normalize(records[i].get('Surgeon(s) / Author(s)')),
                                normalize(records[i].get('Publication Date'))) if b]
            # Within a hub the topic is constant, so the org alone often repeats
            # (one institution publishing several graft variants). Append the
            # variant so sibling links and table rows are distinguishable.
            variant = rp_data.dedupe_name(
                normalize(records[i].get('Surgery Category')),
                normalize(records[i].get('Surgery Type')))
            label = org or rp_data.protocol_name(records[i])
            if variant and org and variant.lower() not in org.lower():
                label = f'{org} — {variant}'
            entries.append({
                'path': paths[i][0],
                'name': rp_data.protocol_name(records[i]),
                'org': org,
                'label': truncate(label, 62),
                'meta': truncate(' · '.join(bits), 70),
            })

        hub_path = f'/protocols/{topic}/'
        hub_trail = [('Home', '/')]
        if region and region in REGION_PATHS:
            hub_trail.append((region, REGION_PATHS[region]))
        hub_trail.append((meta['display'], None))

        # ── protocol pages ──
        for pos, i in enumerate(ordered):
            record = records[i]
            path, t_slug, slug, pid = paths[i]
            name = rp_data.protocol_name(record)
            org = normalize(record.get('Source Organization'))
            source_url = normalize(record.get('Protocol URL'))

            title = T.fit_title(name, org)
            desc_src = ' '.join(filter(None, [
                normalize(record.get('WB Status')),
                normalize(record.get('Key Restrictions')),
            ])) or normalize(record.get('Timeline / Phases'))
            description = truncate(
                f'{name} rehabilitation protocol' + (f' from {org}' if org else '') +
                (f'. {desc_src}' if desc_src else '.'), 155)

            thin = unique_words(record) < MIN_WORDS_INDEXABLE
            robots = 'noindex, follow' if thin else 'index, follow'

            trail = hub_trail[:-1] + [(meta['display'], hub_path), (org or name, None)]
            jsonld = T.graph(
                T.organization(),
                T.breadcrumb([(n, p) for n, p in trail]),
                T.medical_web_page(
                    url=f'{T.SITE}{path}', name=name, description=description,
                    condition=meta['display'], source_url=source_url,
                    publisher=org or None,
                    author=normalize(record.get('Surgeon(s) / Author(s)')) or None,
                    published=normalize(record.get('Publication Date')) or None,
                ),
            )

            sibs = sibling_ring(entries, pos)
            sib_html = ''
            if sibs:
                links = '\n'.join(
                    f'      <a class="rp-sib" href="{esc(s["path"])}">'
                    f'{esc(s["label"])}</a>' for s in sibs)
                sib_html = (
                    f'    <section class="rp-siblings">\n'
                    f'      <h2>Other {esc(meta["display"])} protocols</h2>\n'
                    f'{links}\n'
                    f'    </section>\n')

            surgeons = normalize(record.get('Surgeon(s) / Author(s)'))
            org_meta = f' &middot; {esc(truncate(surgeons, 80))}' if surgeons else ''

            html_out = protocol_t.substitute(
                head=head_t.substitute(
                    title=esc(title), description=esc(description),
                    canonical=f'{T.SITE}{path}', robots=robots, jsonld=escj(jsonld)),
                header=header, footer=footer, disclaimer=disclaimer,
                breadcrumb=render_breadcrumb(trail),
                h1=esc(name),
                org=esc(org), org_meta=org_meta,
                facts=render_facts(record),
                source_url=esc(source_url),
                source_host=esc(T.host_of(source_url)),
                siblings=sib_html,
                topic_slug=esc(topic), topic_display=esc(meta['display']),
                region=esc(region or 'All'), region_path=esc(region_path),
            )
            if write_text(OUT_DIR / topic / slug / 'index.html', html_out):
                written += 1

        # ── hub page ──
        hub_title = T.fit_title(f'{meta["display"]} Protocols — {len(idxs)} Compared')
        hub_desc = truncate(
            f'Compare {len(idxs)} {meta["display"]} rehabilitation protocols from '
            f'leading orthopedic institutions — weight-bearing status, key restrictions, '
            f'and phase timelines, free.', 155)
        hub_jsonld = T.graph(
            T.organization(),
            T.breadcrumb(hub_trail),
            T.item_list([(e['label'], e['path']) for e in entries],
                        name=f'{meta["display"]} protocols'),
        )
        related = ''
        sibling_topics = [
            (s, m) for s, m in topic_infos.items()
            if m['region'] == region and s != topic and m['indexable']
        ][:8]
        if sibling_topics:
            links = '\n'.join(
                f'      <a class="rp-sib" href="/protocols/{esc(s)}/">{esc(m["display"])}</a>'
                for s, m in sibling_topics)
            related = (f'    <section class="rp-siblings">\n'
                       f'      <h2>Related {esc(region)} topics</h2>\n{links}\n    </section>\n')

        hub_html = hub_t.substitute(
            head=head_t.substitute(
                title=esc(hub_title), description=esc(hub_desc),
                canonical=f'{T.SITE}{hub_path}',
                robots='index, follow' if meta['indexable'] else 'noindex, follow',
                jsonld=escj(hub_jsonld)),
            header=header, footer=footer, disclaimer=disclaimer,
            breadcrumb=render_breadcrumb(hub_trail),
            h1=esc(meta['h1']),
            intro=meta['intro'] or build_intro(meta['display'], records, idxs),
            comparison=comparison_table(records, ordered, entries),
            count=len(idxs), display=esc(meta['display']),
            cards='\n'.join(protocol_card(e) for e in entries),
            related=related,
            region=esc(region or 'All'), region_path=esc(region_path),
        )
        if write_text(OUT_DIR / topic / 'index.html', hub_html):
            written += 1

    # ── /protocols/ topic index ──────────────────────────────────────────────
    by_region = defaultdict(list)
    for topic, meta in topic_infos.items():
        by_region[meta['region'] or 'Other'].append((topic, meta))

    sections = []
    for region in sorted(by_region):
        rows = sorted(by_region[region], key=lambda tm: -tm[1]['count'])
        links = '\n'.join(
            f'      <a class="rp-topic-link" href="/protocols/{esc(t)}/">'
            f'{esc(m["display"])} <span class="rp-topic-count">{m["count"]}</span></a>'
            for t, m in rows)
        head = (f'<h2 id="{esc(rp_slugs.slugify(region))}">'
                f'<a href="{esc(REGION_PATHS.get(region, "#"))}">{esc(region)}</a></h2>'
                if region in REGION_PATHS else f'<h2>{esc(region)}</h2>')
        sections.append(f'    {head}\n    <div class="rp-topic-grid">\n{links}\n    </div>\n')

    total_topics = len(topic_infos)
    idx_trail = [('Home', '/'), ('Protocol Topics', None)]
    index_html = index_t.substitute(
        head=head_t.substitute(
            title='Browse Rehabilitation Protocols by Surgery Type | Rehab Protocols',
            description=truncate(
                f'Browse {len(records)} rehabilitation protocols across {total_topics} surgery '
                f'types — ACL reconstruction, rotator cuff repair, arthroplasty, and more.', 155),
            canonical=f'{T.SITE}/protocols/', robots='index, follow',
            jsonld=escj(T.graph(
                T.organization(), T.website(), T.breadcrumb(idx_trail),
                T.item_list([(m['display'], f'/protocols/{t}/')
                             for t, m in sorted(topic_infos.items(),
                                                key=lambda tm: -tm[1]['count'])[:25]],
                            name='Most common protocol topics')))),
        header=header, footer=footer, disclaimer=disclaimer,
        breadcrumb=render_breadcrumb(idx_trail),
        h1='Browse Rehabilitation Protocols by Surgery Type',
        intro=(f'{len(records)} post-operative and non-operative rehabilitation protocols, '
               f'grouped into {total_topics} surgery types and sourced from academic medical '
               f'centers, hospital systems, and orthopedic surgeons. Every protocol links to '
               f'its original source document.'),
        sections='\n'.join(sections),
    )
    if write_text(OUT_DIR / 'index.html', index_html):
        written += 1

    # ── Splice server-rendered lists into the 7 region pages ─────────────────
    # These previously rendered client-side from a 1.24 MB protocols.js, so
    # crawlers saw only "Loading protocols…". The hand-written .lp-intro
    # paragraph on each page sits outside the sentinels and is never touched.
    region_members = defaultdict(list)
    for i, record in enumerate(records):
        region_members[normalize(record.get('Body Region Display'))].append(i)

    for region, page_path in rp_data.LANDING_PAGES.items():
        if not page_path.exists():
            print(f'  WARNING: {page_path.name} missing for {region} — not spliced')
            continue
        idxs = sorted(region_members.get(region, []),
                      key=lambda i: (paths[i][1], paths[i][2]))

        cards = []
        for i in idxs:
            org = normalize(records[i].get('Source Organization'))
            bits = [b for b in (normalize(records[i].get('Surgeon(s) / Author(s)')),
                                normalize(records[i].get('Publication Date'))) if b]
            cards.append(protocol_card({
                'path': paths[i][0],
                'name': rp_data.protocol_name(records[i]),
                'org': org,
                'meta': truncate(' · '.join(bits), 70),
            }))
        # The grid wrapper is part of the payload: the sentinels replaced the old
        # <div class="lp-grid">, so without it the cards would render unstyled.
        grid = ('\n    <div class="rp-card-grid">\n' + '\n'.join(cards) +
                '\n    </div>\n    ') if cards else ''
        rp_data.splice(page_path, 'PROTOCOL-LIST', grid,
                       label=f'{len(cards)} {region} protocol cards')

        topics_here = sorted(
            ((t, m) for t, m in topic_infos.items()
             if m['region'] == region and m['indexable']),
            key=lambda tm: -tm[1]['count'])
        if topics_here:
            links = '\n'.join(
                f'      <a class="rp-sib" href="/protocols/{esc(t)}/">'
                f'{esc(m["display"])} <span class="rp-topic-count">{m["count"]}</span></a>'
                for t, m in topics_here)
            block = (f'\n    <section class="rp-siblings">\n'
                     f'      <h2>Browse {esc(region)} protocols by surgery type</h2>\n'
                     f'{links}\n    </section>\n    ')
        else:
            block = ''
        rp_data.splice(page_path, 'TOPIC-LINKS', block,
                       label=f'{len(topics_here)} {region} topic links')

    hubs = sum(1 for m in topic_infos.values() if m['indexable'])
    print(f'  Generated {len(records)} protocol pages + {len(topic_infos)} hubs '
          f'({hubs} indexable) + 1 index -> protocols/')
    print(f'  {written} file(s) changed')
    return paths, topic_infos
