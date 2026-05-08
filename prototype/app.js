/* ----------------------------------------------------------------------
   Bill Diff — Staffer Tool Prototype (vanilla JS, no framework)

   Loads canonical diff JSON (schema v1.0) and renders two views:
     - cards:  per-change side-by-side cards
     - inline: tracked-changes inline blocks with word-level marks

   No network beyond fetching the local sample JSONs. No analytics.
   ---------------------------------------------------------------------- */

const SAMPLES = [
  {
    id: 'hr4366-xml',
    title: 'H.R. 4366 (118th)',
    pair: 'Reported in House → Engrossed in House',
    source: 'XML',
    file: 'sample-diffs/hr4366-reported-vs-engrossed-xml.json',
  },
  {
    id: 'hr4366-pdf',
    title: 'H.R. 4366 (118th)',
    pair: 'Reported → Engrossed (PDF pipeline)',
    source: 'PDF',
    file: 'sample-diffs/hr4366-reported-vs-engrossed-pdf.json',
  },
  {
    id: 'synthetic',
    title: 'Demo bill (HR DEMO-2026)',
    pair: 'Committee Print → Floor Manager\'s Mark',
    source: 'PDF',
    file: 'sample-diffs/synthetic-edge-cases.json',
  },
];

const state = {
  currentSampleId: null,
  currentDiff: null,
  view: 'cards',
  filter: 'all',
};

// --- DOM refs ---------------------------------------------------------------

const $ = (id) => document.getElementById(id);
const libraryList = $('library-list');
const content = $('content');
const billTitle = $('bill-title');
const billVersions = $('bill-versions');

// --- Library ---------------------------------------------------------------

function renderLibrary() {
  libraryList.innerHTML = '';
  for (const s of SAMPLES) {
    const li = document.createElement('li');
    li.className = 'library-item' + (s.id === state.currentSampleId ? ' is-active' : '');
    li.setAttribute('role', 'option');
    li.setAttribute('aria-selected', s.id === state.currentSampleId ? 'true' : 'false');
    li.tabIndex = 0;
    li.innerHTML = `
      <div class="library-item__title">${escapeHtml(s.title)}</div>
      <div class="library-item__pair">${escapeHtml(s.pair)}</div>
      <span class="library-item__source">${escapeHtml(s.source)}</span>
    `;
    li.addEventListener('click', () => loadSample(s.id));
    li.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); loadSample(s.id); }
    });
    libraryList.appendChild(li);
  }
}

async function loadSample(id) {
  const sample = SAMPLES.find((s) => s.id === id);
  if (!sample) return;
  state.currentSampleId = id;
  renderLibrary();
  content.innerHTML = '<div class="content__loading">Loading…</div>';
  try {
    const res = await fetch(sample.file);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.currentDiff = await res.json();
    renderTopBar();
    renderContent();
  } catch (err) {
    content.innerHTML = `<div class="empty-state">Failed to load sample: ${escapeHtml(String(err))}</div>`;
  }
}

// --- Top bar ---------------------------------------------------------------

function renderTopBar() {
  const d = state.currentDiff;
  if (!d) return;
  const billId = `${(d.bill.type || '').toUpperCase()} ${d.bill.number}`.trim();
  const congress = d.bill.congress ? ` (${d.bill.congress}th Cong.)` : '';
  billTitle.textContent = `${billId}${congress}`;
  const v1 = d.versions.v1.label || 'v1';
  const v2 = d.versions.v2.label || 'v2';
  const src = (d.versions.v1.source || '').toUpperCase();
  billVersions.textContent = `${v1}  →  ${v2}   ·   ${src} pipeline`;
}

// --- Content ---------------------------------------------------------------

function renderContent() {
  const d = state.currentDiff;
  if (!d) return;

  const filtered = applyFilter(d.changes);

  let html = renderSummaryBar(d.summary);

  if (filtered.length === 0) {
    html += '<div class="empty-state">No changes match the current filter.</div>';
    content.innerHTML = html;
    return;
  }

  if (state.view === 'cards') {
    html += renderCards(filtered);
  } else {
    html += renderInline(filtered);
  }

  content.innerHTML = html;
}

function renderSummaryBar(summary) {
  const order = ['added', 'removed', 'modified', 'moved'];
  const pills = order
    .filter((k) => (summary || {})[k])
    .map(
      (k) => `
        <span class="summary-pill summary-pill--${k}">
          <span class="summary-pill__count">${summary[k]}</span>
          <span>${k}</span>
        </span>`
    )
    .join('');
  return `<div class="summary-bar">${pills}</div>`;
}

function applyFilter(changes) {
  if (state.filter === 'all') return changes;
  if (state.filter === 'financial') {
    return changes.filter((c) => (c.amounts || []).length > 0);
  }
  // structural: added/removed/moved (anything other than a pure prose modification)
  return changes.filter((c) => c.change_type !== 'modified');
}

// --- Cards view ------------------------------------------------------------

function renderCards(changes) {
  return `<div class="cards">${changes.map(renderCard).join('')}</div>`;
}

function renderCard(c) {
  const degradedClass = c.anchor_resolution === 'degraded' ? ' card--degraded' : '';
  const headingClass = c.anchor_resolution === 'degraded' ? ' card__heading--degraded' : '';
  const sectionNum = c.section_number ? `<span class="card__section-number">§${escapeHtml(c.section_number)}</span>` : '';

  return `
    <article class="card card--${c.change_type}${degradedClass}" id="${c.id}">
      <header class="card__head">
        <span class="card__type card__type--${c.change_type}">${c.change_type.toUpperCase()}</span>
        ${sectionNum}
        <span class="card__heading${headingClass}">${renderHeading(c)}</span>
      </header>
      ${renderCitation(c)}
      ${renderMove(c)}
      ${renderBody(c)}
      ${renderAmounts(c)}
    </article>
  `;
}

function renderHeading(c) {
  if (c.anchor_resolution === 'degraded') {
    return 'anchor unresolved · see PDF for context';
  }
  const path = c.path.v2 || c.path.v1 || [];
  if (path.length === 0) return '<em>(unknown location)</em>';
  return path.map(escapeHtml).join(' &gt; ');
}

function renderCitation(c) {
  if (!c.location) return '';
  const v1 = c.location.v1 ? formatRange(c.location.v1) : '— (new in v2)';
  const v2 = c.location.v2 ? formatRange(c.location.v2) : '— (removed in v2)';
  return `<div class="card__citation"><span class="v1">${escapeHtml(v1)}</span><span class="v2">${escapeHtml(v2)}</span></div>`;
}

function formatRange(r) {
  const start = r.start_line == null ? `p.${r.start_page}` : `p.${r.start_page} L${r.start_line}`;
  const end = r.end_line == null ? `p.${r.end_page}` : `p.${r.end_page} L${r.end_line}`;
  return start === end ? start : `${start} – ${end}`;
}

function renderMove(c) {
  if (!c.move) return '';
  if (c.move.kind === 'renumbered') {
    const tail = c.move.body_unchanged ? ' · body text unchanged' : '';
    return `<div class="card__move">Renumbered: <code>${escapeHtml(c.move.old_label)}</code> → <code>${escapeHtml(c.move.new_label)}</code>${tail}</div>`;
  }
  // relocated
  const v1 = (c.path.v1 || []).map(escapeHtml).join(' &gt; ');
  const v2 = (c.path.v2 || []).map(escapeHtml).join(' &gt; ');
  return `<div class="card__move">Moved: ${v1} → ${v2}</div>`;
}

function renderBody(c) {
  const oldT = c.text.old;
  const newT = c.text.new;
  if (oldT == null && newT == null) return '';
  if (oldT == null) {
    return `<div class="card__body card__body--single">
      <div class="body-col body-col--new"><div class="body-col__label">v2 (added)</div>${escapeHtml(newT)}</div>
    </div>`;
  }
  if (newT == null) {
    return `<div class="card__body card__body--single">
      <div class="body-col body-col--old"><div class="body-col__label">v1 (removed)</div>${escapeHtml(oldT)}</div>
    </div>`;
  }
  return `<div class="card__body">
    <div class="body-col body-col--old"><div class="body-col__label">v1</div>${escapeHtml(oldT)}</div>
    <div class="body-col body-col--new"><div class="body-col__label">v2</div>${escapeHtml(newT)}</div>
  </div>`;
}

function renderAmounts(c) {
  if (!c.amounts || c.amounts.length === 0) return '';
  const rows = c.amounts.map((a) => {
    const delta = a.new - a.old;
    const sign = delta > 0 ? '+' : '';
    const pct = a.old !== 0 ? ` (${sign}${((delta / a.old) * 100).toFixed(1)}%)` : '';
    return `<div class="amount-row">
      <span class="amount-row__old">${formatDollars(a.old)}</span>
      <span class="amount-row__arrow">→</span>
      <span class="amount-row__new">${formatDollars(a.new)}</span>
      <span class="amount-row__delta">${sign}${formatDollars(delta)}${pct}</span>
    </div>`;
  }).join('');
  return `<div class="card__amounts"><div class="card__amounts-title">Financial</div>${rows}</div>`;
}

function formatDollars(n) {
  return '$' + n.toLocaleString('en-US');
}

// --- Inline tracked-changes view ------------------------------------------

function renderInline(changes) {
  return `<div class="inline-view">${changes.map(renderInlineBlock).join('')}</div>`;
}

function renderInlineBlock(c) {
  const head = renderInlineHead(c);
  let body;
  if (c.change_type === 'added') {
    body = `<ins class="diff-add">${escapeHtml(c.text.new || '')}</ins>`;
  } else if (c.change_type === 'removed') {
    body = `<del class="diff-del">${escapeHtml(c.text.old || '')}</del>`;
  } else if (c.change_type === 'moved' && c.move && c.move.body_unchanged) {
    body = escapeHtml(c.text.new || c.text.old || '');
  } else {
    body = renderWordDiff(c.text.old || '', c.text.new || '');
  }
  return `<div class="inline-block inline-block--${c.change_type}" id="inline-${c.id}">
    <div class="inline-block__head">${head}</div>
    <div class="inline-block__body">${body}</div>
  </div>`;
}

function renderInlineHead(c) {
  const path = (c.path.v2 || c.path.v1 || []).map(escapeHtml).join(' &gt; ');
  const location = c.location && (c.location.v2 || c.location.v1);
  const loc = location ? ` · ${escapeHtml(formatRange(location))}` : '';
  const move = c.move
    ? c.move.kind === 'renumbered'
      ? ` · renumbered ${escapeHtml(c.move.old_label)} → ${escapeHtml(c.move.new_label)}`
      : ' · relocated'
    : '';
  const tag = c.change_type.toUpperCase();
  return `<strong>${tag}</strong> · ${path || '<em>(unknown)</em>'}${loc}${move}`;
}

// Word-level LCS diff. Splits on whitespace boundaries while keeping the
// runs intact. Output is a sequence of <ins> / <del> / equal spans.
function renderWordDiff(oldText, newText) {
  const a = tokenize(oldText);
  const b = tokenize(newText);
  const ops = lcsDiff(a, b);
  let out = '';
  let buf = { type: null, text: '' };
  const flush = () => {
    if (!buf.text) return;
    if (buf.type === 'eq') out += escapeHtml(buf.text);
    else if (buf.type === 'add') out += `<ins class="diff-add">${escapeHtml(buf.text)}</ins>`;
    else if (buf.type === 'del') out += `<del class="diff-del">${escapeHtml(buf.text)}</del>`;
    buf = { type: null, text: '' };
  };
  for (const op of ops) {
    if (op.type !== buf.type) { flush(); buf.type = op.type; }
    buf.text += op.text;
  }
  flush();
  return out;
}

function tokenize(text) {
  // Keep word/whitespace splits as separate tokens so output preserves spacing.
  return text.match(/\s+|[^\s]+/g) || [];
}

function lcsDiff(a, b) {
  // Compute LCS table, then walk back to emit ops.
  const m = a.length, n = b.length;
  const dp = new Array(m + 1);
  for (let i = 0; i <= m; i++) dp[i] = new Int32Array(n + 1);
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops = [];
  let i = 0, j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) { ops.push({ type: 'eq', text: a[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ type: 'del', text: a[i] }); i++; }
    else { ops.push({ type: 'add', text: b[j] }); j++; }
  }
  while (i < m) { ops.push({ type: 'del', text: a[i++] }); }
  while (j < n) { ops.push({ type: 'add', text: b[j++] }); }
  return ops;
}

// --- Modals ----------------------------------------------------------------

function setupModals() {
  $('add-bill-btn').addEventListener('click', () => $('add-bill-modal').hidden = false);
  $('export-btn').addEventListener('click', () => {
    if (state.currentDiff) {
      const id = `${(state.currentDiff.bill.type || '').toLowerCase()}${state.currentDiff.bill.number}`;
      $('export-bill').textContent = id;
    }
    $('export-modal').hidden = false;
  });
  document.querySelectorAll('[data-close]').forEach((el) => {
    el.addEventListener('click', () => {
      const modal = el.closest('.modal');
      if (modal) modal.hidden = true;
    });
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal:not([hidden])').forEach((m) => m.hidden = true);
    }
  });
}

// --- View toggle + filter --------------------------------------------------

function setupControls() {
  document.querySelectorAll('.view-toggle__btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.view-toggle__btn').forEach((b) => {
        b.classList.toggle('is-active', b === btn);
        b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
      });
      state.view = btn.dataset.view;
      renderContent();
    });
  });
  document.querySelectorAll('input[name="filter"]').forEach((input) => {
    input.addEventListener('change', () => {
      state.filter = input.value;
      renderContent();
    });
  });
}

// --- Utils -----------------------------------------------------------------

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// --- Init ------------------------------------------------------------------

renderLibrary();
setupControls();
setupModals();
loadSample(SAMPLES[0].id);
