"""Unified HTML renderer for both XML and PDF bill diffs.

Consumes a DiffView produced by an adapter (formatters.adapters.xml_dict_to_view
or .pdf_diff_to_view). Replaces formatters/html.py and formatters/pdf_html.py
once the migration shims (steps 9 and 10) are in place.

The renderer makes canonical visual choices documented in the plan
plans/.../staged-sutherland.md — it does not branch on which pipeline produced
the view. Pipeline-specific data (citations, degraded styling, section numbers)
is rendered when present and omitted when absent.
"""

from __future__ import annotations

from html import escape

from formatters.view_model import DiffView

# Card / callout / sidebar / financial-summary builders are filled in across
# steps 6-8. The skeleton in this module ties them together; for now,
# format_diff_html emits the chrome plus an empty changes section.

__all__ = ["format_diff_html"]


_SUMMARY_ORDER = ("modified", "added", "removed", "moved")


def _versions_html(view: DiffView) -> str:
    """Render the versions line.

    Canonical form: "v1: {label} → v2: {label} · {congress}th Congress".
    The "vN: " prefix is dropped when both version numbers are None — PDF
    inputs don't carry a version index, and "v1: Reported" is misleading
    when no such index exists.
    """
    if view.v1_version_number is not None or view.v2_version_number is not None:
        v1 = (
            f"v{view.v1_version_number}: {escape(view.v1_label)}"
            if view.v1_version_number is not None
            else escape(view.v1_label)
        )
        v2 = (
            f"v{view.v2_version_number}: {escape(view.v2_label)}"
            if view.v2_version_number is not None
            else escape(view.v2_label)
        )
    else:
        v1 = escape(view.v1_label)
        v2 = escape(view.v2_label)
    return f"{v1} &rarr; {v2} · {escape(str(view.congress))}th Congress"


def _summary_bar_html(summary: dict[str, int]) -> str:
    """Render the summary bar in canonical order, skipping zero buckets."""
    items: list[str] = []
    for key in _SUMMARY_ORDER:
        count = summary.get(key, 0)
        if count > 0:
            items.append(
                f'<span class="summary-item">'
                f'<span class="badge badge-{key}">{key}</span> '
                f"<strong>{count}</strong>"
                f"</span>"
            )
    return "".join(items)


def _bill_label(view: DiffView) -> str:
    """Pre-escaped "{BILL_TYPE} {N}" string."""
    return f"{escape(str(view.bill_type).upper())} {escape(str(view.bill_number))}"


def _sidebar_html(view: DiffView) -> str:
    """Sidebar shell. The <li> entries are filled in step 7; for now an empty <ul>."""
    return (
        '<nav class="sidebar">\n'
        '<input type="text" id="sidebar-filter" placeholder="Filter sections...">\n'
        "<ul></ul>\n"
        "</nav>"
    )


def _cards_section_html(view: DiffView) -> str:
    """Cards section. Card builder lands in step 6; for now, empty == no-changes message."""
    if not view.changes:
        return '<p class="no-changes">No changes found between these versions.</p>'
    # Placeholder until step 6 fills in the card builder.
    return ""


def _financial_summary_html(view: DiffView) -> str:
    """Financial summary table. Lands in step 8."""
    return ""


def format_diff_html(view: DiffView) -> str:
    """Assemble a complete standalone HTML report from a DiffView."""
    bill_label = _bill_label(view)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{bill_label} — Diff</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="layout">
{_sidebar_html(view)}
<div class="main">
<div class="report-header">
<h1>{bill_label} &mdash; Comparison</h1>
<div class="versions">{_versions_html(view)}</div>
<div class="summary-bar">{_summary_bar_html(view.summary)}</div>
</div>
{_financial_summary_html(view)}
<h2>Changes</h2>
{_cards_section_html(view)}
</div>
</div>
<div class="nav-buttons">
<button id="btn-prev">&larr; Prev</button>
<button id="btn-next">Next &rarr;</button>
</div>
<script>
{_JS}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CSS — union of formatters/html.py and formatters/pdf_html.py.
#
# Where selectors collide, the more polished version wins. Notable choices:
# - .change-card.unanchored / .degraded styling kept from PDF (XML never used
#   them; harmless when classes aren't applied).
# - .citation styling kept from PDF for the same reason.
# - .financial-callout layout takes PDF's flex rows (canonical choice #12).
# - tr.unchanged .change-amount color kept from PDF.
# ---------------------------------------------------------------------------

_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, 'Times New Roman', serif; color: #222; line-height: 1.6; }
.layout { display: flex; min-height: 100vh; }

/* Sidebar */
.sidebar { width: 300px; position: fixed; top: 0; left: 0; height: 100vh;
  overflow-y: auto; background: #f7f7f7; border-right: 1px solid #ddd; padding: 12px; }
.sidebar input { width: 100%; padding: 6px 8px; margin-bottom: 8px;
  border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
.sidebar ul { list-style: none; }
.sidebar li { margin-bottom: 2px; }
.sidebar a { display: block; padding: 4px 6px; text-decoration: none;
  color: #333; font-size: 13px; border-radius: 3px; }
.sidebar a:hover { background: #e8e8e8; }
.sidebar .nav-item.unanchored a { color: #6c757d; font-style: italic; }

/* Main content */
.main { margin-left: 300px; padding: 24px 32px; max-width: 900px; flex: 1; }

/* Header */
.report-header h1 { font-size: 22px; margin-bottom: 4px; }
.report-header .versions { color: #666; font-size: 15px; margin-bottom: 16px; }
.summary-bar { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.summary-item { font-size: 14px; }
.summary-item strong { margin-right: 4px; }

/* Badges */
.badge { display: inline-block; padding: 1px 6px; border-radius: 3px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge-modified { background: #fff3cd; color: #856404; }
.badge-added { background: #d4edda; color: #155724; }
.badge-removed { background: #f8d7da; color: #721c24; }
.badge-moved { background: #cce5ff; color: #004085; }

/* Financial table */
.financial-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }
.financial-table th { background: #f0f0f0; text-align: left; padding: 8px; border-bottom: 2px solid #ccc; }
.financial-table td { padding: 6px 8px; border-bottom: 1px solid #eee; }
.financial-table .amount { text-align: right; font-variant-numeric: tabular-nums; }
.financial-table a { color: #0056b3; text-decoration: none; }
.financial-table a:hover { text-decoration: underline; }
tr.increase .change-amount { color: #155724; }
tr.decrease .change-amount { color: #721c24; }
tr.unchanged .change-amount { color: #666; }

/* Change cards */
.change-card { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 16px;
  padding: 16px; background: #fff; }
.change-card.added { border-left: 4px solid #28a745; }
.change-card.removed { border-left: 4px solid #dc3545; }
.change-card.modified { border-left: 4px solid #ffc107; }
.change-card.moved { border-left: 4px solid #007bff; }
.change-card.unanchored { border-left: 4px solid #6c757d; background: #fafafa; }
.change-card.unanchored .change-header h3 {
  color: #6c757d; font-style: italic; font-weight: 400; }
.change-card.unanchored .change-header h3::before { content: "⚠ "; }

.change-header { margin-bottom: 6px; }
.change-header h3 { font-size: 16px; display: inline; margin-left: 8px; font-weight: 600; }
.section-number { display: block; font-size: 13px; color: #666; margin-top: 2px; }

/* Citation block (page/line) */
.citation { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px;
  color: #555; margin: 4px 0 12px; }
.citation .v1, .citation .v2 { display: inline-block; padding: 1px 6px;
  background: #f0f0f0; border-radius: 3px; margin-right: 6px; }
.citation .v1::before { content: "v1: "; color: #888; }
.citation .v2::before { content: "v2: "; color: #888; }

/* Bodies */
.change-body { font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
.added-text { background: #e6ffe6; padding: 10px; border-radius: 4px; }
.removed-text { background: #ffe6e6; padding: 10px; border-radius: 4px;
  text-decoration: line-through; color: #666; }
.old-text { background: #ffe6e6; padding: 8px; border-radius: 4px; margin-bottom: 8px; }
.new-text { background: #e6ffe6; padding: 8px; border-radius: 4px; }
.move-info { font-size: 13px; color: #004085; margin-bottom: 8px;
  padding: 6px 10px; background: #e7f1ff; border-radius: 3px; }
.move-info code { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; }
.amendment-note { font-size: 12px; color: #856404; background: #fff3cd; padding: 4px 8px;
  border-radius: 3px; margin-top: 4px; }

/* Inline diff */
del { background: #fecdd3; text-decoration: line-through; color: #9a3412; padding: 0 1px; }
ins { background: #bbf7d0; text-decoration: none; color: #166534; padding: 0 1px; }

/* Financial callout (canonical: PDF's flex rows) */
.financial-callout { margin-top: 12px; padding: 10px 14px; background: #f0f7ff;
  border: 1px solid #b6d4fe; border-radius: 4px; font-size: 13px;
  font-variant-numeric: tabular-nums; }
.financial-callout .row { display: flex; gap: 10px; margin-bottom: 2px; }
.financial-callout .label { color: #555; min-width: 110px; }
.financial-callout .delta.decrease { color: #721c24; font-weight: 600; }
.financial-callout .delta.increase { color: #155724; font-weight: 600; }
.financial-callout .delta.unchanged { color: #555; }

/* Navigation buttons */
.nav-buttons { position: fixed; bottom: 20px; right: 20px; display: flex; gap: 8px; z-index: 10; }
.nav-buttons button { padding: 8px 14px; border: 1px solid #ccc; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.nav-buttons button:hover { background: #f0f0f0; }

/* Print */
@media print {
  .sidebar, .nav-buttons, #sidebar-filter { display: none; }
  .main { margin-left: 0; }
  .change-card { break-inside: avoid; }
}
"""


_JS = """\
document.addEventListener('DOMContentLoaded', function() {
  // Sidebar filter
  var filter = document.getElementById('sidebar-filter');
  if (filter) {
    filter.addEventListener('input', function() {
      var q = this.value.toLowerCase();
      document.querySelectorAll('.sidebar li').forEach(function(li) {
        li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }

  // Prev/next navigation
  var cards = document.querySelectorAll('.change-card');
  var current = -1;
  function goTo(idx) {
    if (idx >= 0 && idx < cards.length) {
      current = idx;
      cards[idx].scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }
  var prev = document.getElementById('btn-prev');
  var next = document.getElementById('btn-next');
  if (prev) prev.addEventListener('click', function() { goTo(current - 1); });
  if (next) next.addEventListener('click', function() { goTo(current + 1); });

  // Financial table sort (groups rowspan rows together by data-group)
  document.querySelectorAll('.financial-table th').forEach(function(th, colIdx) {
    th.style.cursor = 'pointer';
    th.addEventListener('click', function() {
      var table = th.closest('table');
      var tbody = table.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));
      var groups = [];
      var groupMap = {};
      rows.forEach(function(row) {
        var g = row.dataset.group;
        if (!(g in groupMap)) {
          groupMap[g] = groups.length;
          groups.push([]);
        }
        groups[groupMap[g]].push(row);
      });
      var asc = th.dataset.sort !== 'asc';
      th.dataset.sort = asc ? 'asc' : 'desc';
      groups.sort(function(a, b) {
        var aVal = a[0].cells[colIdx] ? a[0].cells[colIdx].textContent.replace(/[^\\d.-]/g, '') : '';
        var bVal = b[0].cells[colIdx] ? b[0].cells[colIdx].textContent.replace(/[^\\d.-]/g, '') : '';
        var aNum = parseFloat(aVal), bNum = parseFloat(bVal);
        if (!isNaN(aNum) && !isNaN(bNum)) return asc ? aNum - bNum : bNum - aNum;
        return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      });
      groups.forEach(function(group) {
        group.forEach(function(row) { tbody.appendChild(row); });
      });
    });
  });
});
"""
