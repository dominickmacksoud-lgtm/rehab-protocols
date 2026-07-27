"""Template loading, HTML escaping, and JSON-LD builders.

string.Template (${name}) rather than str.format or f-strings: Jinja2 is not
installed and the site has no build step, and str.format would require doubling
every CSS brace in the templates. Verified safe — there are no '$' characters in
styles.css or the inline CSS these templates carry.
"""

import html
import json
import re
from string import Template
from urllib.parse import urlparse

from rp_data import ROOT

TEMPLATE_DIR = ROOT / 'templates'
SITE = 'https://rehabprotocols.com'
ORG_ID = f'{SITE}/#organization'
WEBSITE_ID = f'{SITE}/#website'

_cache = {}


def load(name):
    if name not in _cache:
        _cache[name] = (TEMPLATE_DIR / name).read_text(encoding='utf-8')
    return _cache[name]


def tmpl(name):
    return Template(load(name))


def esc(s):
    """Escape for text nodes and attribute values alike."""
    return html.escape(s or '', quote=True)


def escj(obj):
    """Serialize JSON-LD.

    Not HTML-escaped — JSON-LD is consumed as JSON. '</' is neutralized so a
    Notes field containing '</script>' cannot break out of the script element.
    """
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('</', r'<\/')


def truncate(text, limit=155):
    """Trim to a word boundary for meta descriptions."""
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(' ,;:.—-')
    return f'{cut}…'


BRAND_SUFFIX = ' | Rehab Protocols'


def fit_title(name, org=None, limit=70):
    """Assemble a title within the length budget, dropping the least useful part first.

    Keeps the searched term (the procedure) leftmost — Google truncates the
    display but indexes the whole string, so losing the procedure name to make
    room for branding would be the wrong trade.
    """
    name = ' '.join((name or '').split())
    org = ' '.join((org or '').split())

    # Don't append "Protocol" to a name that already says it — that produced
    # titles like "ACL Reconstruction Protocols — 53 Compared Protocol".
    says_protocol = 'protocol' in name.lower()

    candidates = []
    if org:
        if not says_protocol:
            candidates.append(f'{name} Protocol — {org}{BRAND_SUFFIX}')
        candidates += [f'{name} — {org}{BRAND_SUFFIX}', f'{name} — {org}']
    if not says_protocol:
        candidates.append(f'{name} Protocol{BRAND_SUFFIX}')
    candidates += [f'{name}{BRAND_SUFFIX}', name]

    for c in candidates:
        if len(c) <= limit:
            return c

    # Everything is still too long: trim the org, then the name.
    if org:
        room = limit - len(name) - 3
        if room >= 12:
            return f'{name} — {truncate(org, room)}'
    return truncate(name, limit)


def host_of(url):
    try:
        return urlparse(url).netloc.replace('www.', '') or 'the source site'
    except ValueError:
        return 'the source site'


# ── JSON-LD nodes ─────────────────────────────────────────────────────────────

def organization():
    return {
        '@type': 'Organization',
        '@id': ORG_ID,
        'name': 'Rehab Protocols',
        'url': f'{SITE}/',
        'description': 'A free reference library of rehabilitation protocols and '
                       'clinical practice guidelines for physical therapists.',
    }


def website():
    return {
        '@type': 'WebSite',
        '@id': WEBSITE_ID,
        'url': f'{SITE}/',
        'name': 'Rehab Protocols',
        'publisher': {'@id': ORG_ID},
        'potentialAction': {
            '@type': 'SearchAction',
            'target': {
                '@type': 'EntryPoint',
                'urlTemplate': f'{SITE}/?q={{search_term_string}}',
            },
            'query-input': 'required name=search_term_string',
        },
    }


def breadcrumb(trail):
    """trail: [(name, path_or_None)] — positions must be contiguous from 1."""
    items = []
    for i, (name, path) in enumerate(trail, start=1):
        item = {'@type': 'ListItem', 'position': i, 'name': name}
        if path:
            item['item'] = f'{SITE}{path}'
        items.append(item)
    return {'@type': 'BreadcrumbList', 'itemListElement': items}


ISO_DATE_RE = re.compile(r'\d{4}(-\d{2}(-\d{2})?)?$')


def medical_web_page(*, url, name, description, condition, source_url,
                     publisher=None, author=None, published=None):
    """The page's own URL is canonical here.

    The previous client-injected markup set url to the third-party PDF, which
    attributed ~887 entities to other domains. The source document is now a
    citation instead.

    `published` must already be ISO-8601 (see rp_data.parse_pub_date) or None.
    Anything else is dropped rather than emitted: raw CSV text used to flow
    straight through, publishing 443 invalid datePublished values including 144
    literal "Not listed". Omitting the key costs nothing; an invalid Date makes
    Search Console reject the whole node.
    """
    node = {
        '@type': 'MedicalWebPage',
        'url': url,
        'name': name,
        'description': description,
        'inLanguage': 'en-US',
        'isPartOf': {'@id': WEBSITE_ID},
        'audience': {'@type': 'Audience', 'audienceType': 'Physical Therapists'},
    }
    if condition:
        node['about'] = {'@type': 'MedicalCondition', 'name': condition}
    if source_url:
        node['citation'] = {'@type': 'CreativeWork', 'url': source_url}
    if publisher:
        node['sourceOrganization'] = {'@type': 'Organization', 'name': publisher}
    if author:
        node['author'] = {'@type': 'Person', 'name': author}
    if published and ISO_DATE_RE.match(published):
        node['datePublished'] = published
    return node


def item_list(entries, name=None):
    """entries: [(name, path)]. numberOfItems always matches the items listed."""
    items = [
        {'@type': 'ListItem', 'position': i, 'name': n, 'url': f'{SITE}{p}'}
        for i, (n, p) in enumerate(entries, start=1)
    ]
    node = {'@type': 'ItemList', 'numberOfItems': len(items), 'itemListElement': items}
    if name:
        node['name'] = name
    return node


def graph(*nodes):
    return {'@context': 'https://schema.org', '@graph': [n for n in nodes if n]}
