// Search abbreviation and misspelling dictionary, shared by the homepage
// library search (index.html) and the Treatment Planner (treatment-planner.js).
//
// Search is a plain substring match on every field of a protocol. That falls
// down on the abbreviations clinicians actually type: "TKA" only matches
// protocols whose text happens to spell out the acronym, so it found 19 of 46
// total-knee protocols, "RCR" 10 of 76 rotator cuff repairs, "ACLR" 2 of 94,
// and the common misspelling "menisectomy" found nothing at all.
//
// Each key is one lowercase query token. A token matches a protocol when the
// haystack contains the token itself OR any phrase listed for it. Phrases are
// substrings, so "total knee" also covers "total knee arthroplasty" and
// "total knee replacement". Keep keys to things people actually type; do not
// add two-letter keys, a bare "ac" or "rc" substring matches half the catalog
// on its own already.
//
// Loaded as a plain script (no module) so it works in both pages without a
// build step. Attaches one global: window.RP_SEARCH_SYNONYMS.
(function () {
  'use strict';

  var S = {
    // ── Joint replacement ────────────────────────────────────────────────
    tka: ['total knee'],
    tkr: ['total knee'],
    tha: ['total hip'],
    thr: ['total hip'],
    tsa: ['total shoulder'],
    rtsa: ['reverse total shoulder', 'reverse shoulder'],
    rsa: ['reverse total shoulder', 'reverse shoulder'],
    taa: ['total ankle'],
    replacement: ['arthroplasty'],
    arthroplasty: ['replacement'],
    uka: ['unicompartmental', 'partial knee'],

    // ── Shoulder ─────────────────────────────────────────────────────────
    rcr: ['rotator cuff repair', 'rotator cuff'],
    rtc: ['rotator cuff'],
    rct: ['rotator cuff'],
    cuff: ['rotator cuff'],
    supraspinatus: ['rotator cuff'],
    subscap: ['subscapularis'],
    scr: ['superior capsular reconstruction'],
    sad: ['subacromial decompression'],
    acromioplasty: ['subacromial decompression'],
    dcr: ['distal clavicle'],
    acj: ['ac joint', 'acromioclavicular'],
    acromioclavicular: ['ac joint'],
    labrum: ['labral'],
    labral: ['labrum'],
    bankart: ['labral', 'instability'],
    latarjet: ['instability'],
    slap: ['labral'],
    tenodesis: ['biceps'],
    bicep: ['biceps'],
    frozen: ['adhesive capsulitis'],
    capsulitis: ['adhesive capsulitis'],
    manipulation: ['mua'],
    mua: ['manipulation'],
    humeral: ['humerus'],
    humerus: ['humeral'],

    // ── Knee ─────────────────────────────────────────────────────────────
    aclr: ['acl reconstruction', 'acl'],
    acl: ['anterior cruciate'],
    pclr: ['pcl reconstruction', 'pcl'],
    pcl: ['posterior cruciate'],
    mcl: ['medial collateral'],
    lcl: ['lateral collateral'],
    plc: ['posterolateral corner'],
    mpflr: ['mpfl'],
    mpfl: ['patellofemoral'],
    bptb: ['patellar tendon', 'bone-patellar', 'bone patellar'],
    btb: ['patellar tendon', 'bone-patellar', 'bone patellar'],
    quad: ['quadriceps'],
    quadriceps: ['quad'],
    hamstring: ['hs autograft'],
    menisectomy: ['meniscectomy'],
    meniscetomy: ['meniscectomy'],
    meniscal: ['meniscus'],
    meniscus: ['meniscal'],
    hto: ['high tibial osteotomy', 'osteotomy'],
    dfo: ['distal femoral osteotomy', 'osteotomy'],
    oats: ['osteochondral'],
    maci: ['cartilage', 'chondrocyte'],
    microfracture: ['cartilage'],
    cartilage: ['chondral', 'osteochondral'],
    patella: ['patellar'],
    patellar: ['patella'],
    kneecap: ['patella', 'patellar'],
    plateau: ['tibial plateau'],

    // ── Hip ──────────────────────────────────────────────────────────────
    fai: ['femoroacetabular', 'hip arthroscopy'],
    scope: ['arthroscopy', 'arthroscopic'],
    arthroscopy: ['arthroscopic'],
    arthroscopic: ['arthroscopy'],
    pao: ['periacetabular'],
    gluteus: ['gluteal', 'abductor'],

    // ── Ankle / foot ─────────────────────────────────────────────────────
    achillies: ['achilles'],
    achilies: ['achilles'],
    achille: ['achilles'],
    brostrom: ['lateral ankle ligament', 'lateral ankle'],
    brostrum: ['brostrom', 'lateral ankle ligament'],
    atfl: ['lateral ankle', 'brostrom'],
    sprain: ['ligament'],
    ptt: ['posterior tibial'],
    pttd: ['posterior tibial'],
    bunion: ['hallux valgus', 'hallux'],
    bunionectomy: ['hallux valgus', 'hallux'],
    hallux: ['bunion'],
    fasciitis: ['plantar fascia'],
    'plantar': ['fascia'],
    syndesmosis: ['high ankle'],

    // ── Elbow / wrist / hand ─────────────────────────────────────────────
    ucl: ['ulnar collateral'],
    tommy: ['ucl', 'ulnar collateral'],
    tfcc: ['triangular fibrocartilage'],
    cmc: ['carpometacarpal', 'thumb'],
    dbr: ['distal biceps'],
    'tennis': ['lateral epicondyl'],
    'golfers': ['medial epicondyl'],
    epicondylitis: ['epicondyl'],
    drf: ['distal radius'],
    cubital: ['ulnar nerve'],

    // ── Spine ────────────────────────────────────────────────────────────
    acdf: ['anterior cervical', 'cervical'],
    fusion: ['arthrodesis', 'fusion'],
    arthrodesis: ['fusion'],
    plif: ['lumbar fusion', 'lumbar spinal fusion'],
    tlif: ['lumbar fusion', 'lumbar spinal fusion'],
    alif: ['lumbar fusion', 'lumbar spinal fusion'],
    xlif: ['lumbar fusion', 'lumbar spinal fusion'],
    discectomy: ['microdiscectomy'],
    microdiscectomy: ['discectomy'],
    disc: ['discectomy', 'disk'],
    laminectomy: ['decompression'],
    back: ['lumbar', 'spine'],
    neck: ['cervical', 'spine'],
    radiculopathy: ['cervical', 'lumbar', 'radicul'],

    // ── General procedure words ──────────────────────────────────────────
    orif: ['fracture', 'open reduction'],
    fx: ['fracture'],
    fracture: ['fx'],
    rupture: ['repair', 'tear'],
    tear: ['repair', 'rupture'],
    reconstruction: ['recon'],
    recon: ['reconstruction'],
    rehab: ['rehabilitation', 'protocol'],

    // ── Care type (matches the internal type value in the haystack) ──────
    conservative: ['nonop'],
    'non-operative': ['nonop'],
    nonoperative: ['nonop'],
    'non-op': ['nonop'],
    'non-surgical': ['nonop'],
    nonsurgical: ['nonop'],
    'nonsurg': ['nonop'],
    'post-op': ['postop'],
    postoperative: ['postop'],
    'post-operative': ['postop'],
    'post-surgical': ['postop'],
    postsurgical: ['postop'],

    // ── Institutions people type by nickname ─────────────────────────────
    mgh: ['massachusetts general', 'mass general'],
    mgb: ['mass general brigham', 'massachusetts general', 'brigham'],
    bwh: ['brigham'],
    hss: ['hospital for special surgery'],
    osu: ['ohio state'],
    'ohio': ['ohio state'],
    ucsf: ['university of california, san francisco', 'ucsf'],
    uw: ['university of washington', 'uw health', 'uw medicine'],
    umich: ['michigan'],
    upmc: ['pittsburgh'],
    'jhu': ['johns hopkins'],
    'hopkins': ['johns hopkins'],
    mayo: ['mayo clinic'],
    'kaiser': ['kaiser permanente'],
    'nyu': ['nyu langone', 'new york university']
  };

  window.RP_SEARCH_SYNONYMS = S;

  var boundaryCache = {};
  function literalMatch(haystack, token) {
    // Tokens without a dictionary entry keep the original substring behaviour
    // ("acl" inside "aclr", "menisc" inside "meniscectomy"). Tokens WITH one are
    // usually short acronyms, and a bare substring test makes "tha" match
    // "that" in every protocol, so those match on word boundaries instead.
    if (!S[token]) { return haystack.indexOf(token) !== -1; }
    var re = boundaryCache[token];
    if (!re) {
      var esc = token.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
      re = boundaryCache[token] = new RegExp('(^|[^a-z0-9])' + esc + '($|[^a-z0-9])');
    }
    return re.test(haystack);
  }

  // True when one lowercase query token is found in a lowercase haystack,
  // either literally or through any of its listed phrases.
  window.rpTokenMatches = function (haystack, token) {
    if (literalMatch(haystack, token)) { return true; }
    var alts = S[token];
    if (!alts) { return false; }
    for (var i = 0; i < alts.length; i++) {
      if (haystack.indexOf(alts[i]) !== -1) { return true; }
    }
    return false;
  };

  // Splits a query into lowercase tokens, dropping trailing punctuation
  // ("tka," "rcr.") so the dictionary lookup still hits.
  window.rpSearchTokens = function (query) {
    return (query || '').toLowerCase().split(/\s+/)
      .map(function (t) { return t.replace(/^[^\w]+|[^\w/-]+$/g, ''); })
      .filter(Boolean);
  };
}());
