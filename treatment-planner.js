/* AI Treatment Planner.

   Builds a copy-pastable prompt from a catalogued protocol (or a free-text
   case) plus non-identifying patient parameters. Everything runs in the
   browser: protocols.js and guidelines.js are already loaded and nothing the
   clinician types is transmitted anywhere.

   Copy rule for this file: no em dashes in anything user-facing, including
   the generated prompt. Periods and commas. */
(function () {
  'use strict';

  var SITE = 'https://rehabprotocols.com';
  var MAX_RESULTS = 12;
  var PREFS_KEY = 'rp_planner_prefs';

  var $ = function (id) { return document.getElementById(id); };

  var els = {
    search: $('tp-search'), results: $('tp-results'), searchStatus: $('tp-search-status'),
    customBtn: $('tp-custom-btn'), backBtn: $('tp-back-btn'), clearBtn: $('tp-clear-btn'),
    source: $('tp-source'), empty: $('tp-empty'), custom: $('tp-custom'),
    srcName: $('tp-src-name'), srcOrg: $('tp-src-org'), srcMeta: $('tp-src-meta'),
    srcPage: $('tp-src-page'), srcDoc: $('tp-src-doc'),
    cpgRow: $('tp-cpg-row'), cpg: $('tp-cpg'), cpgLabel: $('tp-cpg-label'),
    variantRow: $('tp-variant-row'), variant: $('tp-variant'), variantLabel: $('tp-variant-label'), variantHint: $('tp-variant-hint'),
    customType: $('tp-custom-type'), customDesc: $('tp-custom-desc'),
    age: $('tp-age'), procedure: $('tp-procedure'), dateLabel: $('tp-date-label'),
    surgdate: $('tp-surgdate'), weeksOut: $('tp-weeks-out'), comorbid: $('tp-comorbid'),
    vpw: $('tp-vpw'), vlen: $('tp-vlen'), weeks: $('tp-weeks'),
    planOut: $('tp-plan-out'), out: $('tp-out'), charcount: $('tp-charcount'),
    copybtn: $('tp-copy'), resetbtn: $('tp-reset'),
    resetdlg: $('tp-resetdlg'), resetcancel: $('tp-resetcancel'), resetconfirm: $('tp-resetconfirm')
  };

  var lib = (typeof protocols !== 'undefined' && Array.isArray(protocols)) ? protocols : [];
  var cpgs = (typeof guidelines !== 'undefined' && Array.isArray(guidelines)) ? guidelines : [];

  var state = {
    mode: 'library',   // 'library' or 'custom'
    protocol: null,    // the selected protocols.js entry
    dirty: false,      // true once the clinician has typed into the prompt
    results: [],
    active: -1
  };

  // ── Helpers ────────────────────────────────────────────────────────────

  function escHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Catalogue text carries em dashes in protocol names ("ACL Reconstruction
  // — Allograft"). The prompt is user-facing copy, so they become commas.
  function clean(v) {
    return String(v == null ? '' : v)
      .replace(/\s*—\s*/g, ', ')
      .replace(/–/g, '-')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function track(name, params) {
    if (typeof window.gtag === 'function') { window.gtag('event', name, params || {}); }
  }

  function guidelineFor(p) {
    if (!p || !p.cpg) { return null; }
    for (var i = 0; i < cpgs.length; i++) {
      if (cpgs[i].url === p.cpg) { return cpgs[i]; }
    }
    return null;
  }

  // Protocols whose precautions branch on a choice (approach, graft, fixation)
  // carry a `variant` from protocol-variants.csv. The dropdown opens on a
  // placeholder so nothing is assumed on the clinician's behalf.
  function buildVariantOptions(p) {
    var v = p && p.variant;
    els.variant.innerHTML = '';
    if (!v) { return; }
    var ph = document.createElement('option');
    ph.value = '';
    ph.textContent = 'Choose the ' + v.label.toLowerCase() + '...';
    els.variant.appendChild(ph);
    v.options.forEach(function (o) {
      var opt = document.createElement('option');
      opt.value = o;
      opt.textContent = o;
      els.variant.appendChild(opt);
    });
  }

  function variantChoice() {
    var p = state.mode === 'library' ? state.protocol : null;
    if (!p || !p.variant) { return null; }
    return { label: p.variant.label, value: els.variant.value };
  }

  function isPostOp() {
    if (state.mode === 'custom') { return els.customType.value !== 'nonop'; }
    return !state.protocol || state.protocol.type !== 'nonop';
  }

  function hasSource() {
    if (state.mode === 'custom') {
      return !!(els.procedure.value.trim() || els.customDesc.value.trim());
    }
    return !!state.protocol;
  }

  // ── Search ─────────────────────────────────────────────────────────────

  var TYPE_WORDS = { postop: 'post-op postoperative surgical', nonop: 'non-op nonoperative conservative', education: 'education' };

  function haystack(p) {
    if (!p._tpHay) {
      p._tpHay = [p.name, p.category, p.sourceOrganization, p.surgeons, TYPE_WORDS[p.type] || p.type]
        .map(function (f) { return f || ''; }).join(' ').toLowerCase();
    }
    return p._tpHay;
  }

  function search(q) {
    var tokens = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) { return []; }
    var scored = [];
    for (var i = 0; i < lib.length; i++) {
      var p = lib[i];
      var hay = haystack(p);
      var ok = true;
      for (var t = 0; t < tokens.length; t++) {
        if (hay.indexOf(tokens[t]) === -1) { ok = false; break; }
      }
      if (!ok) { continue; }
      var name = (p.name || '').toLowerCase();
      var score = 1;
      if (name.indexOf(tokens[0]) === 0) { score = 3; }
      else if (name.indexOf(tokens[0]) !== -1) { score = 2; }
      scored.push({ p: p, score: score });
    }
    scored.sort(function (a, b) {
      return b.score - a.score || (a.p.name || '').localeCompare(b.p.name || '');
    });
    return scored.slice(0, MAX_RESULTS).map(function (s) { return s.p; });
  }

  function closeResults() {
    els.results.hidden = true;
    els.results.innerHTML = '';
    els.search.setAttribute('aria-expanded', 'false');
    els.search.removeAttribute('aria-activedescendant');
    state.results = [];
    state.active = -1;
  }

  function renderResults() {
    var q = els.search.value.trim();
    if (q.length < 2) {
      closeResults();
      els.searchStatus.textContent = '';
      return;
    }
    state.results = search(q);
    state.active = -1;
    if (!state.results.length) {
      closeResults();
      els.searchStatus.textContent = 'No protocols match. Try fewer words, or describe the case instead.';
      return;
    }
    els.results.innerHTML = state.results.map(function (p, i) {
      return '<li role="option" id="tp-opt-' + i + '" data-i="' + i + '" aria-selected="false">' +
        '<span class="tp-opt-name">' + escHtml(clean(p.name)) + '</span>' +
        '<span class="tp-opt-org">' + escHtml(p.sourceOrganization || '') +
        (p.category ? ' <span class="tp-opt-cat">' + escHtml(p.category) + '</span>' : '') + '</span></li>';
    }).join('');
    els.results.hidden = false;
    els.search.setAttribute('aria-expanded', 'true');
    els.searchStatus.textContent = state.results.length + (state.results.length === MAX_RESULTS ? '+' : '') +
      ' match' + (state.results.length === 1 ? '' : 'es') + '. Use the arrow keys and Enter to pick one.';
  }

  function setActive(i) {
    var items = els.results.children;
    if (!items.length) { return; }
    if (i < 0) { i = items.length - 1; }
    if (i >= items.length) { i = 0; }
    for (var k = 0; k < items.length; k++) {
      items[k].setAttribute('aria-selected', k === i ? 'true' : 'false');
      items[k].classList.toggle('is-active', k === i);
    }
    state.active = i;
    els.search.setAttribute('aria-activedescendant', 'tp-opt-' + i);
    if (items[i].scrollIntoView) { items[i].scrollIntoView({ block: 'nearest' }); }
  }

  // ── Source selection ───────────────────────────────────────────────────

  function setQueryParam(path) {
    try {
      var url = new URL(window.location.href);
      if (path) { url.searchParams.set('p', path); } else { url.searchParams.delete('p'); }
      window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    } catch (e) {
      // History API blocked or unavailable. The page works without the deep link.
    }
  }

  function selectProtocol(p, opts) {
    opts = opts || {};
    state.mode = 'library';
    state.protocol = p;
    els.procedure.value = clean(p.name);
    els.cpg.checked = true;
    buildVariantOptions(p);
    els.search.value = '';
    closeResults();
    els.searchStatus.textContent = '';
    setQueryParam(p.path || '');
    if (!opts.silent) {
      track('planner_select_protocol', { protocol_name: p.name, category: p.category, source_org: p.sourceOrganization });
    }
    render();
  }

  function useCustom() {
    state.mode = 'custom';
    state.protocol = null;
    if (els.procedure.dataset.fromLibrary === 'true') { els.procedure.value = ''; }
    closeResults();
    setQueryParam('');
    render();
    els.customDesc.focus();
  }

  function useLibrary() {
    state.mode = 'library';
    render();
    els.search.focus();
  }

  // The x on the source card. Drops the protocol, returns to the empty state
  // and hands focus to the search box. Patient fields are left alone: the
  // clinician is swapping the protocol, not starting a new patient.
  function clearProtocol() {
    state.protocol = null;
    state.mode = 'library';
    if (els.procedure.dataset.fromLibrary === 'true') { els.procedure.value = ''; }
    setQueryParam('');
    render();
    els.search.focus();
  }

  function renderSource() {
    var p = state.protocol;
    var custom = state.mode === 'custom';
    els.custom.hidden = !custom;
    els.backBtn.hidden = !custom;
    els.source.hidden = custom || !p;
    els.empty.hidden = custom || !!p;
    els.procedure.dataset.fromLibrary = (!custom && p) ? 'true' : 'false';

    if (custom || !p) { return; }

    els.srcName.textContent = clean(p.name);
    els.srcOrg.textContent = p.sourceOrganization || '';
    var bits = [];
    if (p.type === 'postop') { bits.push('Post-op'); }
    else if (p.type === 'nonop') { bits.push('Non-op'); }
    if (p.category) { bits.push(p.category); }
    if (p.publicationDate && p.publicationDate !== 'Not listed') { bits.push(p.publicationDate); }
    els.srcMeta.textContent = bits.join(' · ');
    if (p.path) {
      els.srcPage.href = p.path;
      els.srcPage.hidden = false;
    } else {
      els.srcPage.hidden = true;
    }
    els.srcDoc.href = p.url;

    var v = p.variant;
    els.variantRow.hidden = !v;
    if (v) {
      els.variantLabel.textContent = v.label;
      els.variantHint.textContent = els.variant.value
        ? 'The prompt tells the assistant to apply only this ' + v.label.toLowerCase() + '\'s precautions.'
        : 'This protocol\'s precautions differ by ' + v.label.toLowerCase() + '. Pick the one that applies.';
    }

    var g = guidelineFor(p);
    els.cpgRow.hidden = !g;
    if (g) {
      els.cpgLabel.textContent = 'Include the ' + clean(g.condition) + ' clinical practice guideline (' +
        clean(g.issuingOrg) + (g.publicationDate ? ', ' + g.publicationDate : '') + ')';
    }
  }

  // ── Derived values ─────────────────────────────────────────────────────

  function weeksSince() {
    if (!els.surgdate.value) { return null; }
    var s = new Date(els.surgdate.value + 'T00:00:00');
    if (isNaN(s.getTime())) { return null; }
    var t = new Date();
    t.setHours(0, 0, 0, 0);
    return Math.floor(Math.floor((t - s) / 86400000) / 7);
  }

  function planNumbers() {
    var weeks = Math.min(52, Math.max(1, Number(els.weeks.value) || 1));
    var vpw = Math.min(7, Math.max(1, Number(els.vpw.value) || 1));
    return { weeks: weeks, vpw: vpw, visits: weeks * vpw };
  }

  // ── Prompt ─────────────────────────────────────────────────────────────

  // A line with no value drops out entirely rather than printing a bare label.
  // 311 rows have no author and 253 no publication date.
  function line(label, value) {
    var v = clean(value);
    return v ? label + ': ' + v + '\n' : '';
  }

  function buildPrompt() {
    if (!hasSource()) { return ''; }

    var p = state.mode === 'library' ? state.protocol : null;
    var postop = isPostOp();
    var wks = weeksSince();
    var n = planNumbers();
    var start = (wks !== null && wks >= 0) ? wks : null;
    var end = start === null ? null : start + n.weeks;
    var g = (p && els.cpg.checked) ? guidelineFor(p) : null;

    var s = '';
    s += 'You are assisting a licensed physical therapist with treatment planning. Your\n';
    s += 'output is a clinical draft for a qualified clinician to review, edit and\n';
    s += 'approve. It is not medical advice and it is not a final plan of care.\n\n';

    if (p) {
      s += '## Source protocol\n\n';
      s += line('Protocol', p.name);
      s += line('Organization', p.sourceOrganization);
      s += line('Author or authors', p.surgeons);
      s += line('Publication date', p.publicationDate);
      s += line('Weight bearing status', p.wbStatus);
      s += line('Key restrictions', p.keyRestrictions);
      s += line('Timeline and phases', p.timelinePhases);
      s += line("Cataloguer's notes on the source", p.notes);
      s += line('Source document', p.url);
      if (p.path) { s += line('Library page', SITE + p.path); }
      s += '\nThe fields above are a summary, not the full protocol. If you are able to\n';
      s += 'browse, open the source document and work from it directly. If you cannot,\n';
      s += 'work from the summary and say so plainly in your answer.\n\n';
    } else {
      s += '## Case\n\n';
      s += line('Procedure or pathology', els.procedure.value);
      s += line('Management', postop ? 'Post-operative' : 'Non-operative');
      var desc = els.customDesc.value.trim();
      if (desc) { s += "Clinician's description:\n" + desc + '\n'; }
      s += '\nNo catalogued protocol is attached to this case. Work from published, widely\n';
      s += 'accepted rehabilitation guidance for this procedure or pathology. Name the\n';
      s += 'source you are relying on for each restriction and timeline, and be explicit\n';
      s += 'about anything that is your own clinical reasoning.\n\n';
    }

    if (g) {
      s += '## Clinical practice guideline\n\n';
      s += line('Guideline', g.condition);
      s += line('Issuing organization', g.issuingOrg + (g.publicationDate ? ' (' + g.publicationDate + ')' : ''));
      s += line('Key recommendations', g.keyRecommendations);
      s += line('Source', g.url);
      s += '\nWhere the guideline and the protocol conflict, follow the protocol\'s\n';
      s += 'restrictions and note the conflict.\n\n';
    }

    s += '## Patient\n\n';
    s += line('Age range', els.age.value);
    if (p) { s += line('Procedure', els.procedure.value); }
    var vc = variantChoice();
    if (vc) { s += line(vc.label, vc.value || 'not specified'); }
    s += line(postop ? 'Date of surgery' : 'Date of injury or onset', els.surgdate.value);
    if (start !== null) {
      s += line(postop ? 'Weeks post-op as of today' : 'Weeks since onset as of today', String(start));
    }
    s += line('Relevant comorbidities and context', els.comorbid.value);
    s += line('Visit frequency', n.vpw + ' per week');
    s += line('Visit length', els.vlen.value);
    s += 'Plan length: ' + n.weeks + ' weeks, which is ' + n.visits + ' visits';
    if (start !== null) {
      s += postop
        ? ', covering post-op week ' + start + ' through post-op week ' + end
        : ', covering week ' + start + ' through week ' + end + ' since onset';
    }
    s += '.\n\n';

    s += '## What to produce\n\n';
    s += 'First, an initial evaluation covering:\n\n';
    s += '- Subjective history to gather\n';
    s += '- Precautions and contraindications for this patient at this ' + (postop ? 'post-op week' : 'stage') + '\n';
    s += '- Outcome measures to administer, with a baseline target for each\n';
    s += '- Objective measures and special tests, with what a normal and an abnormal\n';
    s += '  finding would mean here\n';
    s += '- Short term and long term goals, measurable and time bound\n';
    s += '- An initial home exercise program with sets, reps, hold and frequency\n\n';
    s += 'Then every subsequent visit across the plan, numbered, each one labelled with\n';
    s += 'the ' + (postop ? 'post-op week' : 'week since onset') + ' it falls in. For each visit give the focus, the\n';
    s += 'interventions with dosage, the home program changes, and the criteria the\n';
    s += 'patient must meet before progressing.\n\n';

    if (p) {
      s += '## How to handle the protocol\n\n';
      s += "Work from the protocol's stated restrictions and criteria. They take priority\n";
      s += 'over general practice.\n\n';
      s += 'Where the protocol is silent on something this patient needs, say so\n';
      s += "explicitly, label it as your own clinical reasoning rather than the protocol's\n";
      s += 'instruction, and keep it conservative. Do not present an invented number as if\n';
      s += 'the protocol specified it.\n\n';
      s += 'Tie progression to criteria met rather than to the calendar alone, and flag any\n';
      s += 'visit where the plan approaches or crosses one of the stated restrictions.\n';
      if (vc) {
        var lbl = vc.label.toLowerCase();
        if (vc.value) {
          s += '\nThis protocol covers more than one ' + lbl + '. This patient\'s is ' + vc.value + '.\n';
          s += 'Apply only the precautions the protocol states for that one and leave the\n';
          s += 'others out of the plan.\n';
        } else {
          s += '\nThis protocol covers more than one ' + lbl + ' and the clinician has not said\n';
          s += 'which applies. Do not assume one. State which precautions belong to each ' + lbl + '\n';
          s += 'and ask before building the plan around any of them.\n';
        }
      }
    } else {
      s += '## How to handle restrictions\n\n';
      s += "Treat the clinician's stated restrictions as fixed. Where published guidance\n";
      s += 'and your own reasoning fill a gap, label which is which, keep it conservative,\n';
      s += 'and do not present an invented number as if a source specified it.\n\n';
      s += 'Tie progression to criteria met rather than to the calendar alone, and flag any\n';
      s += 'visit where the plan approaches a commonly stated restriction for this case.\n';
    }
    return s;
  }

  // ── Persistence (plan-of-care fields only) ─────────────────────────────

  function loadPrefs() {
    // Storage can be blocked outright and the accessor itself throws there.
    try {
      var raw = localStorage.getItem(PREFS_KEY);
      if (!raw) { return; }
      var p = JSON.parse(raw);
      var vpw = Number(p.vpw);
      var weeks = Number(p.weeks);
      if (vpw >= 1 && vpw <= 7) { els.vpw.value = String(vpw); }
      if (weeks >= 1 && weeks <= 52) { els.weeks.value = String(weeks); }
      var lengths = Array.prototype.map.call(els.vlen.options, function (o) { return o.value; });
      if (lengths.indexOf(p.vlen) !== -1) { els.vlen.value = p.vlen; }
    } catch (e) {
      // Blocked, unavailable, or corrupt. The defaults in the markup stand.
    }
  }

  function savePrefs() {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({
        vpw: Number(els.vpw.value), vlen: els.vlen.value, weeks: Number(els.weeks.value)
      }));
    } catch (e) {
      // The form still works, it just will not remember.
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────

  function syncMeta() {
    var text = els.out.value;
    els.charcount.textContent = text ? text.length.toLocaleString() + ' characters' : '';
    document.body.dataset.tpDirty = state.dirty ? 'true' : 'false';
    els.resetbtn.disabled = !state.dirty;
    els.resetbtn.title = state.dirty ? 'Rebuild the prompt from the form' : 'No edits to reset';
    els.copybtn.disabled = !text;
    els.copybtn.dataset.copied = 'false';
    els.copybtn.textContent = 'Copy prompt';
  }

  function render() {
    renderSource();

    var postop = isPostOp();
    els.dateLabel.textContent = postop ? 'Date of surgery' : 'Date of injury or onset';

    var wks = weeksSince();
    if (wks === null) {
      els.weeksOut.className = 'tp-derived warn';
      els.weeksOut.textContent = postop
        ? 'Add the surgery date to compute weeks post-op.'
        : 'Add the onset date to compute weeks since onset.';
    } else if (wks < 0) {
      els.weeksOut.className = 'tp-derived warn';
      els.weeksOut.textContent = 'That date is in the future. Check the year.';
    } else {
      els.weeksOut.className = 'tp-derived';
      els.weeksOut.innerHTML = (postop ? 'Weeks post-op today: ' : 'Weeks since onset today: ') + '<b>' + wks + '</b>';
    }

    var n = planNumbers();
    var range = (wks === null || wks < 0)
      ? 'not yet known'
      : (postop ? 'post-op week ' : 'week ') + wks + ' through ' + (wks + n.weeks);
    els.planOut.innerHTML = 'Plan covers <b>' + n.visits + '</b> visit' + (n.visits === 1 ? '' : 's') +
      ', ' + range;

    // Only the form owns the textarea while it is clean. Once it is dirty the
    // derived readouts still update, but the prompt itself is the clinician's.
    if (!state.dirty) { els.out.value = buildPrompt(); }
    syncMeta();
  }

  // ── Events ─────────────────────────────────────────────────────────────

  els.search.addEventListener('input', renderResults);
  els.search.addEventListener('focus', function () { if (els.search.value.trim().length >= 2) { renderResults(); } });
  els.search.addEventListener('keydown', function (e) {
    if (els.results.hidden) {
      if (e.key === 'ArrowDown' && els.search.value.trim().length >= 2) { renderResults(); setActive(0); e.preventDefault(); }
      return;
    }
    if (e.key === 'ArrowDown') { setActive(state.active + 1); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { setActive(state.active - 1); e.preventDefault(); }
    else if (e.key === 'Enter') {
      if (state.active >= 0 && state.results[state.active]) { selectProtocol(state.results[state.active]); }
      else if (state.results.length === 1) { selectProtocol(state.results[0]); }
      e.preventDefault();
    }
    else if (e.key === 'Escape') { closeResults(); }
  });
  els.results.addEventListener('mousedown', function (e) {
    // mousedown, not click, so the pick lands before the input's blur closes the list.
    var li = e.target.closest('li[data-i]');
    if (!li) { return; }
    e.preventDefault();
    selectProtocol(state.results[Number(li.dataset.i)]);
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.tp-combo')) { closeResults(); }
  });

  els.customBtn.addEventListener('click', useCustom);
  els.backBtn.addEventListener('click', useLibrary);
  els.clearBtn.addEventListener('click', clearProtocol);
  els.cpg.addEventListener('change', render);
  els.variant.addEventListener('change', render);

  var REMEMBERED = ['vpw', 'vlen', 'weeks'];
  ['customType', 'customDesc', 'age', 'procedure', 'surgdate', 'comorbid', 'vpw', 'vlen', 'weeks'].forEach(function (k) {
    function onChange() {
      if (k === 'procedure') { els.procedure.dataset.fromLibrary = 'false'; }
      if (REMEMBERED.indexOf(k) !== -1) { savePrefs(); }
      render();
    }
    els[k].addEventListener('input', onChange);
    els[k].addEventListener('change', onChange);
  });

  // Typing in the prompt takes ownership of it. Editing all the way back to the
  // generated text hands it back, so the Edited flag cannot get stuck on.
  els.out.addEventListener('input', function () {
    state.dirty = els.out.value !== buildPrompt();
    syncMeta();
  });

  function doReset() {
    state.dirty = false;
    render();
    els.out.focus();
  }
  els.resetbtn.addEventListener('click', function () {
    if (!state.dirty) { return; }
    if (typeof els.resetdlg.showModal === 'function') { els.resetdlg.showModal(); }
    else if (window.confirm('Discard your edits and rebuild the prompt from the form?')) { doReset(); }
  });
  els.resetcancel.addEventListener('click', function () { els.resetdlg.close(); });
  els.resetconfirm.addEventListener('click', function () { els.resetdlg.close(); doReset(); });

  els.copybtn.addEventListener('click', function () {
    var text = els.out.value;
    if (!text) { return; }
    var p = state.protocol;
    track('planner_copy_prompt', {
      mode: state.mode,
      protocol_name: p ? p.name : '(custom case)',
      category: p ? p.category : '',
      edited: state.dirty ? 'yes' : 'no',
      guideline: (p && els.cpg.checked && guidelineFor(p)) ? 'yes' : 'no'
    });
    function fallback() {
      try {
        els.out.focus();
        els.out.select();
        var ok = document.execCommand && document.execCommand('copy');
        els.copybtn.textContent = ok ? 'Copied' : 'Press Ctrl+C to copy';
        els.copybtn.dataset.copied = ok ? 'true' : 'false';
      } catch (e) {
        els.copybtn.textContent = 'Press Ctrl+C to copy';
      }
    }
    // clipboard.writeText rejects on permission denial and in insecure contexts.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        els.copybtn.dataset.copied = 'true';
        els.copybtn.textContent = 'Copied';
      }).catch(fallback);
    } else {
      fallback();
    }
  });

  // Unsaved edits get a browser warning, not a saved draft. The draft holds
  // patient context, which is exactly what this page keeps out of storage.
  window.addEventListener('beforeunload', function (e) {
    if (!state.dirty) { return; }
    e.preventDefault();
    e.returnValue = '';
  });

  // ── Clinical-use notice (shared rp_disclaimer_ack cookie, non-blocking) ──

  var dlBox = $('disclaimer-checkbox');
  var dlBtn = $('disclaimer-btn');
  var dlSheet = $('disclaimer-modal');

  function hasDisclaimerAck() {
    try {
      return document.cookie.split(';').some(function (c) { return c.trim().indexOf('rp_disclaimer_ack=1') === 0; });
    } catch (e) { return false; }
  }
  if (dlBox && dlBtn && dlSheet) {
    dlBox.addEventListener('change', function () { dlBtn.disabled = !this.checked; });
    dlBtn.addEventListener('click', function () {
      try {
        var d = new Date();
        d.setFullYear(d.getFullYear() + 1);
        document.cookie = 'rp_disclaimer_ack=1; path=/; SameSite=Lax; expires=' + d.toUTCString();
      } catch (e) {
        // Cookies blocked. Dismiss anyway rather than trapping the clinician.
      }
      track('acknowledge_disclaimer');
      dlSheet.style.display = 'none';
    });
    if (!hasDisclaimerAck()) { dlSheet.style.display = 'block'; }
  }

  // ── Init ───────────────────────────────────────────────────────────────

  els.search.placeholder = 'Search ' + lib.length.toLocaleString() + ' protocols by procedure or organization';
  loadPrefs();

  // Deep link from a protocol modal or page: ?p=<path>. Keyed on path, the
  // slug ledger's URL contract, never on the array index, which shifts on
  // every ingest.
  var wanted = null;
  try { wanted = new URLSearchParams(window.location.search).get('p'); } catch (e) { wanted = null; }
  var found = null;
  if (wanted) {
    for (var i = 0; i < lib.length; i++) {
      if (lib[i].path === wanted) { found = lib[i]; break; }
    }
  }
  // preventScroll: focusing a field below the fold on load would jump the page
  // past the header before the clinician has seen what the tool is.
  if (found) {
    selectProtocol(found, { silent: true });
    try { els.age.focus({ preventScroll: true }); } catch (e) { /* older engines */ }
  } else {
    if (wanted) { setQueryParam(''); }
    render();
    try { els.search.focus({ preventScroll: true }); } catch (e) { /* older engines */ }
  }
})();
