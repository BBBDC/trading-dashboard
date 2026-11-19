/* Admin-Bereich: Backtest-Ergebnisse
 * Lädt backtest_results.json (reine Aggregate) und rendert Kennzahlen + Tabelle.
 * Keine externen Abhängigkeiten. Alle Texte werden HTML-escaped.
 */
(function () {
  'use strict';

  var TIER_META = {
    PILOT_LIVE:   { label: 'PILOT_LIVE',   cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', rank: 0 },
    SHADOW_PAPER: { label: 'SHADOW_PAPER', cls: 'bg-amber-500/20 text-amber-300 border-amber-500/40',       rank: 1 },
    INFORMATIV:   { label: 'INFORMATIV',   cls: 'bg-slate-700/40 text-slate-300 border-slate-600/50',       rank: 2 }
  };
  var VERDICT_CLS = {
    ROBUST_EDGE: 'bg-emerald-500', NEUTRAL_UNCERTAIN: 'bg-amber-400',
    TOXIC_BLEED: 'bg-rose-500', NO_TRADES: 'bg-slate-700'
  };
  var VERDICT_TXT = {
    ROBUST_EDGE: 'Robuste Edge', NEUTRAL_UNCERTAIN: 'Unsicher',
    TOXIC_BLEED: 'Verlustbringend', NO_TRADES: 'Keine Trades'
  };

  var state = { data: null, tier: 'ALL', cat: 'ALL', search: '', sort: 'tier', lowOnly: false };

  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function num(v, d) {
    if (v === null || v === undefined || isNaN(Number(v))) return '–';
    return Number(v).toFixed(d === undefined ? 2 : d);
  }
  function signed(v, d) {
    if (v === null || v === undefined || isNaN(Number(v))) return '–';
    var n = Number(v);
    return (n > 0 ? '+' : '') + n.toFixed(d === undefined ? 2 : d);
  }
  function $(id) { return document.getElementById(id); }

  function fmtDate(iso) {
    if (!iso) return '–';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '–';
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' });
  }

  function tierBadge(a) {
    var m = TIER_META[a.tier] || TIER_META.INFORMATIV;
    var derived = a.source === 'matrix'
      ? '<span class="ml-1 text-[9px] text-slate-500" title="Tier aus Matrix-Daten nach den Onboarding-Regeln abgeleitet">abgeleitet</span>'
      : '';
    return '<span class="px-2 py-0.5 rounded border text-[10px] font-mono font-bold ' + m.cls + '" title="Quelle: ' +
      esc(a.source || 'unbekannt') + '">' + esc(m.label) + '</span>' + derived;
  }

  function strip(a) {
    var tfs = (state.data && state.data.tf_order) || [];
    var cells = (a.tf_strip || []).map(function (v, i) {
      var tf = tfs[i] || '';
      return '<span class="inline-block w-3.5 h-3.5 rounded-sm ' + (VERDICT_CLS[v] || 'bg-slate-700') +
        '" title="' + esc(tf + ': ' + (VERDICT_TXT[v] || v)) + '"></span>';
    });
    return '<span class="inline-flex gap-0.5">' + cells.join('') + '</span>';
  }

  function lowDataBadge(a) {
    if (!a.low_data) return '';
    var th = (state.data && state.data.thresholds) || { min_trades: 30, min_oos_trades: 10 };
    var b = a.best;
    var detail = b ? ('Bestes Setup: ' + b.trades + ' Trades, ' + b.oos_trades + ' OOS-Trades (Minimum ' +
      th.min_trades + ' / ' + th.min_oos_trades + ')') : 'Keine auswertbaren Trades';
    return '<span class="ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-orange-500/15 text-orange-300 border border-orange-500/40" title="' +
      esc(detail) + '">⚠ geringe Datenbasis</span>';
  }

  function filtered() {
    var list = (state.data && state.data.assets) ? state.data.assets.slice() : [];
    var q = state.search.trim().toLowerCase();
    list = list.filter(function (a) {
      if (state.tier !== 'ALL' && a.tier !== state.tier) return false;
      if (state.cat !== 'ALL' && (a.category || '') !== state.cat) return false;
      if (state.lowOnly && !a.low_data) return false;
      if (q) {
        var hay = (a.symbol + ' ' + a.name + ' ' + a.category).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
    var cmp = {
      tier: function (x, y) {
        var rx = (TIER_META[x.tier] || { rank: 3 }).rank, ry = (TIER_META[y.tier] || { rank: 3 }).rank;
        return rx - ry || (y.robust_count - x.robust_count) || (y.total_r - x.total_r);
      },
      total_r: function (x, y) { return y.total_r - x.total_r; },
      robust: function (x, y) { return y.robust_count - x.robust_count; },
      oos: function (x, y) { return ((y.best && y.best.oos_r) || -999) - ((x.best && x.best.oos_r) || -999); },
      name: function (x, y) { return String(x.name).localeCompare(String(y.name), 'de'); },
      date: function (x, y) { return String(y.evaluated_at || '').localeCompare(String(x.evaluated_at || '')); }
    };
    list.sort(cmp[state.sort] || cmp.tier);
    return list;
  }

  function kpi(label, value, cls) {
    return '<div class="rounded-xl bg-slate-950/70 border border-slate-800 p-3 text-center">' +
      '<div class="text-[10px] uppercase tracking-wide text-slate-400">' + esc(label) + '</div>' +
      '<div class="text-xl font-bold ' + (cls || 'text-white') + '">' + esc(value) + '</div></div>';
  }

  function renderKpis() {
    var t = state.data.totals || {};
    var untestCount = t.untestable !== undefined ? t.untestable : ((state.data.untestable || []).length);
    $('bt-kpis').innerHTML =
      kpi('Getestete Assets', t.assets, 'text-white') +
      kpi('PILOT_LIVE', t.pilot_live, 'text-emerald-300') +
      kpi('SHADOW_PAPER', t.shadow_paper, 'text-amber-300') +
      kpi('INFORMATIV', t.informativ, 'text-slate-300') +
      kpi('Neu (7 Tage)', t.new, 'text-sky-300') +
      kpi('Geringe Datenbasis', t.low_data, 'text-orange-300') +
      kpi('Nicht testbar', untestCount, 'text-slate-400');
    var badge = $('bt-count-badge');
    if (badge) badge.textContent = (t.assets || 0) + ' Assets';
    var gen = $('bt-generated');
    if (gen) gen.textContent = 'Stand: ' + fmtDate(state.data.generated_at);
  }

  function renderCategories() {
    var sel = $('bt-cat');
    if (!sel) return;
    var seen = {};
    var cats = [];
    (state.data.assets || []).forEach(function (a) {
      var c = a.category || '';
      if (c && !seen[c]) {
        seen[c] = true;
        cats.push(c);
      }
    });
    cats.sort(function (a, b) { return a.localeCompare(b, 'de'); });
    sel.innerHTML = '<option value="ALL">Alle Kategorien</option>' +
      cats.map(function (c) { return '<option value="' + esc(c) + '">' + esc(c) + '</option>'; }).join('');
    if (seen[state.cat]) sel.value = state.cat;
    else { state.cat = 'ALL'; sel.value = 'ALL'; }
  }

  function renderUntestable() {
    var box = $('bt-untestable-box');
    var sum = $('bt-untestable-summary');
    var listEl = $('bt-untestable-list');
    if (!box || !listEl) return;
    var items = state.data.untestable || [];
    if (!items.length) {
      box.classList.add('hidden');
      return;
    }
    box.classList.remove('hidden');
    if (sum) {
      sum.textContent = 'Nicht testbare Assets (' + items.length + ') – keine Kursdaten / kein handelbares Instrument';
    }
    listEl.innerHTML = items.map(function (u) {
      return '<div class="rounded-lg border border-slate-800/80 bg-slate-900/50 px-2.5 py-1.5">' +
        '<span class="font-mono font-semibold text-slate-200">' + esc(u.raw_symbol) + '</span>' +
        '<span class="text-slate-400"> – ' + esc(u.reason || 'Keine Datenquelle') + '</span></div>';
    }).join('');
  }

  function renderTable() {
    var rows = filtered();
    var html = rows.map(function (a) {
      var b = a.best;
      var best = b
        ? esc(b.timeframe) + ' · ' + esc(b.mode)
        : '<span class="text-slate-500">–</span>';
      var neu = a.is_new
        ? '<span class="ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/40">NEU</span>' : '';
      var rCls = (b && b.expectancy_r > 0) ? 'text-emerald-300' : 'text-rose-300';
      var oCls = (b && b.oos_r > 0) ? 'text-emerald-300' : 'text-rose-300';
      return '<tr class="border-t border-slate-800/80 hover:bg-slate-800/30">' +
        '<td class="px-3 py-2"><div class="font-semibold text-white text-xs">' + esc(a.name) + neu + '</div>' +
          '<div class="text-[10px] font-mono text-slate-500">' + esc(a.symbol) + (a.category ? ' · ' + esc(a.category) : '') + '</div></td>' +
        '<td class="px-3 py-2 whitespace-nowrap">' + tierBadge(a) + lowDataBadge(a) + '</td>' +
        '<td class="px-3 py-2 text-xs text-slate-300 whitespace-nowrap">' + best + '</td>' +
        '<td class="px-3 py-2 text-xs font-mono text-right text-slate-200">' + (b ? esc(b.trades) : '–') + '</td>' +
        '<td class="px-3 py-2 text-xs font-mono text-right text-slate-200">' + (b ? num(b.profit_factor) : '–') + '</td>' +
        '<td class="px-3 py-2 text-xs font-mono text-right ' + rCls + '">' + (b ? signed(b.expectancy_r, 3) : '–') + '</td>' +
        '<td class="px-3 py-2 text-xs font-mono text-right ' + oCls + '">' + (b ? signed(b.oos_r, 1) + ' <span class="text-slate-500">(' + esc(b.oos_trades) + ')</span>' : '–') + '</td>' +
        '<td class="px-3 py-2 text-xs font-mono text-right text-slate-200">' + esc(a.robust_count) + '/' + esc(a.combos) + '</td>' +
        '<td class="px-3 py-2 text-xs font-mono text-right ' + (a.total_r >= 0 ? 'text-emerald-300' : 'text-rose-300') + '">' + signed(a.total_r, 1) + '</td>' +
        '<td class="px-3 py-2">' + strip(a) + '</td>' +
        '<td class="px-3 py-2 text-[11px] text-slate-400 whitespace-nowrap">' + fmtDate(a.evaluated_at) + '</td>' +
        '</tr>';
    }).join('');
    $('bt-tbody').innerHTML = html ||
      '<tr><td colspan="11" class="px-3 py-6 text-center text-xs text-slate-500">Keine Treffer für die aktuelle Filterung.</td></tr>';
    var c = $('bt-shown');
    if (c) c.textContent = rows.length + ' von ' + ((state.data.assets || []).length) + ' angezeigt';
  }

  function bindControls() {
    var s = $('bt-search');
    if (s) s.addEventListener('input', function () { state.search = s.value; renderTable(); });
    var catSel = $('bt-cat');
    if (catSel) catSel.addEventListener('change', function () { state.cat = catSel.value; renderTable(); });
    var so = $('bt-sort');
    if (so) so.addEventListener('change', function () { state.sort = so.value; renderTable(); });
    var lo = $('bt-low');
    if (lo) lo.addEventListener('change', function () { state.lowOnly = lo.checked; renderTable(); });
    var btns = document.querySelectorAll('[data-bt-tier]');
    Array.prototype.forEach.call(btns, function (b) {
      b.addEventListener('click', function () {
        state.tier = b.getAttribute('data-bt-tier');
        Array.prototype.forEach.call(btns, function (x) {
          var on = x.getAttribute('data-bt-tier') === state.tier;
          x.classList.toggle('bg-amber-500', on);
          x.classList.toggle('text-slate-950', on);
          x.classList.toggle('text-slate-300', !on);
        });
        renderTable();
      });
    });
  }

  function showError(msg) {
    var t = $('bt-tbody');
    if (t) t.innerHTML = '<tr><td colspan="11" class="px-3 py-6 text-center text-xs text-rose-300">' + esc(msg) + '</td></tr>';
  }

  function init() {
    if (!$('bt-tbody')) return;
    bindControls();
    fetch('backtest_results.json?nocache=' + Date.now())
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        if (!d || !Array.isArray(d.assets)) throw new Error('Ungültiges Datenformat');
        state.data = d;
        renderKpis();
        renderCategories();
        renderTable();
        renderUntestable();
      })
      .catch(function (e) { showError('Backtest-Daten konnten nicht geladen werden: ' + e.message); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
