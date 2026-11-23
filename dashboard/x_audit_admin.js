/* Admin-Bereich: X-Account Audit & Backtest (Grok Build 4.7 + Claude Opus 5.5)
 * Lädt x_audit_results.json und rendert Score-Card, Timing-Simulation, Opus-Gutachten & Call-Tabelle.
 * Keine externen Abhängigkeiten. Alle Texte werden strikt HTML-escaped.
 */
(function () {
  'use strict';

  var state = {
    data: null,
    selectedHandle: null,
    category: 'ALL',
    direction: 'ALL',
    clusterOnly: true,
    search: '',
    sort: 'date_desc'
  };

  var CAT_BADGES = {
    TRADE_CALL:         { label: 'Trade-Call',  cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
    DIRECTIONAL_THESIS: { label: 'These',       cls: 'bg-sky-500/20 text-sky-300 border-sky-500/40' },
    RISK_WARNING:       { label: 'Warnung',     cls: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
    UNFALSIFIABLE:      { label: 'Vage',        cls: 'bg-slate-700/50 text-slate-300 border-slate-600/50' },
    CHART_ONLY:         { label: 'Chart-Only',  cls: 'bg-purple-500/20 text-purple-300 border-purple-500/40' }
  };

  var TIER_BADGES = {
    TRUSTED:     'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    CONDITIONAL: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
    MIXED:       'bg-amber-500/20 text-amber-300 border-amber-500/40',
    CAUTION:     'bg-orange-500/20 text-orange-300 border-orange-500/40',
    UNTRUSTED:   'bg-rose-500/20 text-rose-300 border-rose-500/40'
  };

  var RED_FLAG_LABELS = {
    HEDGED_BOTH_SIDES:      'Beidseitig abgesichert',
    NO_INVALIDATION:        'Ohne Invalidation',
    HINDSIGHT_SPIN:         'Hindsight-Spin',
    ENGAGEMENT_BAIT:        'Engagement-Bait',
    MOVING_GOALPOSTS:       'Ziele verschoben',
    REPEATED_BROKEN_CLOCK:  'Broken-Clock-Muster'
  };

  function $(id) { return document.getElementById(id); }

  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function safeUrl(u) {
    var s = String(u || '').trim();
    return /^https:\/\/(?:www\.)?(?:x|twitter)\.com\/[A-Za-z0-9_]+\/status\/\d{15,20}$/i.test(s) ? s : null;
  }

  function fmtNum(v, d) {
    if (v === null || v === undefined || isNaN(Number(v))) return '–';
    return Number(v).toFixed(d === undefined ? 1 : d);
  }

  function fmtPct(v, d) {
    if (v === null || v === undefined || isNaN(Number(v))) return '–';
    var n = Number(v);
    return (n > 0 ? '+' : '') + n.toFixed(d === undefined ? 1 : d) + '%';
  }

  function fmtPrice(v) {
    if (v === null || v === undefined || isNaN(Number(v))) return '–';
    var n = Number(v);
    if (n >= 1000) return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 });
    if (n >= 1) return '$' + n.toFixed(2);
    return '$' + n.toFixed(4);
  }

  function fmtDate(iso) {
    if (!iso) return '–';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso).slice(0, 10);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' });
  }

  function pctColor(v) {
    if (v === null || v === undefined || isNaN(Number(v))) return 'text-slate-400';
    var n = Number(v);
    if (n > 0) return 'text-emerald-300';
    if (n < 0) return 'text-rose-300';
    return 'text-slate-300';
  }

  function scoreColor(s) {
    if (s === null || s === undefined || isNaN(Number(s))) return 'text-slate-300';
    var n = Number(s);
    if (n >= 70) return 'text-emerald-300';
    if (n >= 55) return 'text-cyan-300';
    if (n >= 40) return 'text-amber-300';
    return 'text-rose-300';
  }

  function barColor(s) {
    var n = Number(s) || 0;
    if (n >= 70) return 'bg-emerald-500';
    if (n >= 55) return 'bg-cyan-500';
    if (n >= 40) return 'bg-amber-400';
    return 'bg-rose-500';
  }

  function currentAccount() {
    var accs = (state.data && state.data.accounts) || [];
    if (!accs.length) return null;
    for (var i = 0; i < accs.length; i++) {
      if (accs[i].handle === state.selectedHandle) return accs[i];
    }
    return accs[0];
  }

  function kpiTile(label, value, sub, valCls) {
    return '<div class="rounded-xl bg-slate-950/75 border border-slate-800 p-3 text-center">' +
      '<div class="text-[10px] uppercase tracking-wide text-slate-400">' + esc(label) + '</div>' +
      '<div class="text-lg sm:text-xl font-bold mt-0.5 ' + (valCls || 'text-white') + '">' + esc(value) + '</div>' +
      (sub ? '<div class="text-[10px] text-slate-500 mt-0.5 font-mono">' + esc(sub) + '</div>' : '') +
      '</div>';
  }

  function scoreBar(label, weight, val) {
    var v = Math.max(0, Math.min(100, Number(val) || 0));
    return '<div>' +
      '<div class="flex justify-between text-[11px] mb-1">' +
        '<span class="text-slate-300">' + esc(label) + ' <span class="text-slate-500 font-mono">(' + esc(weight) + ')</span></span>' +
        '<span class="font-mono font-bold ' + scoreColor(v) + '">' + fmtNum(v, 1) + '</span>' +
      '</div>' +
      '<div class="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">' +
        '<div class="h-full rounded-full ' + barColor(v) + '" style="width:' + v.toFixed(1) + '%"></div>' +
      '</div>' +
    '</div>';
  }

  function renderHeader(acc) {
    var sel = $('xa-account-select');
    var accs = (state.data && state.data.accounts) || [];
    if (sel) {
      sel.innerHTML = accs.map(function (a) {
        return '<option value="' + esc(a.handle) + '"' + (a.handle === acc.handle ? ' selected' : '') + '>' +
          esc(a.display_name || ('@' + a.handle)) + ' (' + fmtNum((a.scores || {}).trust_score, 0) + '/100)</option>';
      }).join('');
    }

    var badge = $('xa-count-badge');
    if (badge) {
      var cl = ((acc.metrics || {}).clustered || {}).count || 0;
      var raw = ((acc.metrics || {}).raw || {}).count || 0;
      badge.textContent = (acc.display_name || ('@' + acc.handle)) + ' · ' + cl + ' Cluster (' + raw + ' Roh)';
    }

    var navBadge = $('admin-xaudit-nav-badge');
    if (navBadge && acc.scores && acc.scores.trust_score !== undefined) {
      navBadge.textContent = fmtNum(acc.scores.trust_score, 0) + '/100';
    }

    var meta = $('xa-meta-line');
    if (meta) {
      var p = acc.period || {};
      var m = acc.models || {};
      meta.textContent = 'Zeitraum: ' + (p.from || '–') + ' bis ' + (p.to || '–') +
        ' (' + (p.months || 24) + 'M) · Stand: ' + fmtDate(acc.audited_at) +
        ' · ' + (m.auditor || 'Opus 5.5');
    }
  }

  function renderHeroAndKpis(acc) {
    var sc = acc.scores || {};
    var opus = acc.opus_audit || {};
    var cl = (acc.metrics || {}).clustered || {};
    var raw = (acc.metrics || {}).raw || {};
    var cats = acc.category_counts || {};
    var sim = acc.timing_simulation || {};
    var h7 = (cl.horizons || {})['7d'] || {};
    var h30 = (cl.horizons || {})['30d'] || {};
    var h90 = (cl.horizons || {})['90d'] || {};
    var hm = cl.horizon_matched || {};

    var tierCls = TIER_BADGES[opus.verdict_tier] || TIER_BADGES.MIXED;
    var trust = sc.trust_score;

    var hero = $('xa-hero-box');
    if (hero) {
      hero.innerHTML =
        '<div class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">' +
          '<div class="lg:col-span-4 rounded-xl bg-slate-950/80 border border-slate-800 p-4 flex flex-col justify-between gap-2">' +
            '<div class="flex items-center justify-between gap-2">' +
              '<span class="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Trust- &amp; Fundamental-Score</span>' +
              '<span class="px-2 py-0.5 rounded border text-[10px] font-mono font-bold ' + tierCls + '">' + esc(opus.verdict_tier || 'AUDIT') + '</span>' +
            '</div>' +
            '<div class="flex items-baseline gap-2">' +
              '<span class="text-4xl font-black font-mono ' + scoreColor(trust) + '">' + fmtNum(trust, 1) + '</span>' +
              '<span class="text-sm text-slate-500 font-mono">/ 100</span>' +
              (opus.opus_trust_score !== null && opus.opus_trust_score !== undefined
                ? '<span class="ml-auto text-[11px] font-mono text-purple-300 bg-purple-500/15 border border-purple-500/30 px-2 py-0.5 rounded">Opus: ' + esc(opus.opus_trust_score) + '/100</span>'
                : '') +
            '</div>' +
            '<div class="text-xs font-semibold text-white">' + esc(opus.verdict_label || 'Auswertung abgeschlossen') + '</div>' +
            '<div class="text-[11px] text-slate-400 font-mono">Falsifizierbar: ' + fmtNum(sc.falsifiable_ratio_pct, 1) + '% · ' +
              'Ausgeschlossen: ' + esc(cats.CHART_ONLY || 0) + ' Chart-Only · ' + esc(cats.UNFALSIFIABLE || 0) + ' Vage</div>' +
          '</div>' +
          '<div class="lg:col-span-5 rounded-xl bg-slate-950/80 border border-slate-800 p-4 space-y-2.5">' +
            scoreBar('Performance &amp; Alpha (geclustert)', '40%', sc.perf_score) +
            scoreBar('Chance / Risiko (MFE / |MAE|)', '20%', sc.rr_score) +
            scoreBar('Klarheit &amp; Falsifizierbarkeit', '20%', sc.clarity_score) +
            scoreBar('Fundamental- &amp; Kausalitätstiefe', '20%', sc.fundamental_score) +
          '</div>' +
          '<div class="lg:col-span-3 rounded-xl bg-slate-950/80 border border-slate-800 p-4 space-y-1.5 text-[11px] text-slate-300">' +
            '<div class="font-bold text-slate-200 flex items-center gap-1.5"><span>📦</span><span>Datenerfassung (24M)</span></div>' +
            '<div class="flex justify-between"><span>Monats-Chunks:</span><span class="font-mono text-white">' + esc((acc.collection_stats || {}).ok_chunks || 0) + ' / ' + esc((acc.collection_stats || {}).total_chunks || 0) + '</span></div>' +
            '<div class="flex justify-between"><span>Roh-Tweets (Snowflake-OK):</span><span class="font-mono text-white">' + esc((acc.collection_stats || {}).unique_tweets || 0) + '</span></div>' +
            '<div class="flex justify-between"><span>Konkrete Trade-Calls:</span><span class="font-mono text-emerald-300">' + esc(cats.TRADE_CALL || 0) + '</span></div>' +
            '<div class="flex justify-between"><span>Richtungs-Thesen:</span><span class="font-mono text-sky-300">' + esc(cats.DIRECTIONAL_THESIS || 0) + '</span></div>' +
            '<div class="flex justify-between"><span>Risiko-Warnungen:</span><span class="font-mono text-amber-300">' + esc(cats.RISK_WARNING || 0) + '</span></div>' +
            '<div class="flex justify-between"><span>Chart-Only (ignoriert):</span><span class="font-mono text-purple-300">' + esc(cats.CHART_ONLY || 0) + '</span></div>' +
          '</div>' +
        '</div>';
    }

    var lcAlpha = (sim.long_cash || {}).alpha_vs_bh_pct;
    var kpis = $('xa-kpis');
    if (kpis) {
      kpis.innerHTML =
        kpiTile('Cluster-Calls', cl.count || 0, 'Roh: ' + (raw.count || 0), 'text-white') +
        kpiTile('Treffer +7d', h7.win_rate_pct !== null ? fmtNum(h7.win_rate_pct, 1) + '%' : '–', 'n=' + (h7.n || 0) + ' · Med ' + fmtPct(h7.median_pct), (h7.win_rate_pct || 0) >= 50 ? 'text-emerald-300' : 'text-rose-300') +
        kpiTile('Treffer +30d', h30.win_rate_pct !== null ? fmtNum(h30.win_rate_pct, 1) + '%' : '–', 'n=' + (h30.n || 0) + ' · Med ' + fmtPct(h30.median_pct), (h30.win_rate_pct || 0) >= 50 ? 'text-emerald-300' : 'text-rose-300') +
        kpiTile('Treffer +90d', h90.win_rate_pct !== null ? fmtNum(h90.win_rate_pct, 1) + '%' : '–', 'n=' + (h90.n || 0) + ' · Med ' + fmtPct(h90.median_pct), (h90.win_rate_pct || 0) >= 50 ? 'text-emerald-300' : 'text-rose-300') +
        kpiTile('Matched Horizon', hm.win_rate_pct !== null ? fmtNum(hm.win_rate_pct, 1) + '%' : '–', 'p=' + (hm.p_value !== null ? hm.p_value : '–') + ' · n=' + (hm.n || 0), (hm.p_value !== null && hm.p_value < 0.05) ? 'text-emerald-300' : 'text-amber-300') +
        kpiTile('MFE / |MAE|', cl.mfe_mae_ratio !== null ? fmtNum(cl.mfe_mae_ratio, 2) + 'x' : '–', fmtPct(cl.mfe_median_pct) + ' / ' + fmtPct(cl.mae_median_pct), (cl.mfe_mae_ratio || 0) >= 1.2 ? 'text-emerald-300' : 'text-amber-300') +
        kpiTile('Timing Alpha', lcAlpha !== undefined && lcAlpha !== null ? fmtPct(lcAlpha) : '–', 'Long/Cash vs BTC B&H', pctColor(lcAlpha));
    }

    var biasBox = $('xa-disclosures');
    if (biasBox) {
      var list = acc.bias_disclosures || [];
      biasBox.innerHTML = list.map(function (d) {
        return '<div class="text-[11px] text-slate-400 leading-relaxed">&bull; ' + esc(d) + '</div>';
      }).join('');
    }
  }

  function renderTimingSvg(curve) {
    if (!Array.isArray(curve) || curve.length < 2) {
      return '<div class="text-xs text-slate-500 py-6 text-center">Keine ausreichenden Kurvenpunkte für die BTC-Timing-Grafik.</div>';
    }
    var w = 520, h = 150, pad = 12;
    var vals = [];
    curve.forEach(function (pt) {
      if (typeof pt.bh === 'number') vals.push(pt.bh);
      if (typeof pt.lc === 'number') vals.push(pt.lc);
      if (typeof pt.ls === 'number') vals.push(pt.ls);
    });
    var minV = Math.min.apply(null, vals);
    var maxV = Math.max.apply(null, vals);
    if (maxV <= minV) { maxV = minV + 10; }
    var sx = function (i) { return pad + (i / (curve.length - 1)) * (w - 2 * pad); };
    var sy = function (v) { return h - pad - ((v - minV) / (maxV - minV)) * (h - 2 * pad); };
    var pathFor = function (key) {
      return curve.map(function (pt, i) {
        return (i === 0 ? 'M' : 'L') + sx(i).toFixed(1) + ',' + sy(pt[key]).toFixed(1);
      }).join(' ');
    };
    var y100 = sy(100);
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" class="w-full h-36 rounded-lg bg-slate-950/90 border border-slate-800/80">' +
      (y100 >= pad && y100 <= h - pad
        ? '<line x1="' + pad + '" y1="' + y100.toFixed(1) + '" x2="' + (w - pad) + '" y2="' + y100.toFixed(1) + '" stroke="#334155" stroke-dasharray="3,3" stroke-width="1"/>'
        : '') +
      '<path d="' + pathFor('bh') + '" fill="none" stroke="#94a3b8" stroke-width="1.8" stroke-dasharray="4,3"/>' +
      '<path d="' + pathFor('ls') + '" fill="none" stroke="#f59e0b" stroke-width="1.8"/>' +
      '<path d="' + pathFor('lc') + '" fill="none" stroke="#22d3ee" stroke-width="2.4"/>' +
      '</svg>' +
      '<div class="flex items-center justify-between text-[10px] font-mono text-slate-400 mt-1.5 flex-wrap gap-2">' +
        '<span>Start: ' + esc(curve[0].date) + ' (=100)</span>' +
        '<span class="flex items-center gap-3">' +
          '<span><span class="inline-block w-2.5 h-0.5 bg-cyan-400 align-middle mr-1"></span>Long/Cash</span>' +
          '<span><span class="inline-block w-2.5 h-0.5 bg-amber-400 align-middle mr-1"></span>Long/Short</span>' +
          '<span><span class="inline-block w-2.5 h-0.5 bg-slate-400 align-middle mr-1"></span>BTC B&amp;H</span>' +
        '</span>' +
        '<span>Ende: ' + esc(curve[curve.length - 1].date) + '</span>' +
      '</div>';
  }

  function renderComparisonAndSimulation(acc) {
    var m = acc.metrics || {};
    var cl = m.clustered || {};
    var raw = m.raw || {};
    var dirs = m.by_direction || {};
    var lvl = m.level_trades || {};
    var sim = acc.timing_simulation || {};

    var compEl = $('xa-comparison-box');
    if (compEl) {
      var rows = [
        { name: 'Geclustert (Unabhängig)', g: cl },
        { name: 'Roh (Alle Calls)', g: raw },
        { name: 'Nur LONG (Geclustert)', g: dirs.LONG || {} },
        { name: 'Nur SHORT / Warnungen', g: dirs.SHORT || {} }
      ];
      compEl.innerHTML =
        '<div class="text-xs font-bold text-white mb-2 flex items-center justify-between">' +
          '<span>📊 Roh vs. Geclustert &amp; Long vs. Short</span>' +
          '<span class="text-[10px] font-mono text-slate-400">14d Anti-Cluster-Fenster</span>' +
        '</div>' +
        '<div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60">' +
          '<table class="w-full text-left text-[11px]">' +
            '<thead class="bg-slate-900/80 text-[10px] uppercase text-slate-400">' +
              '<tr><th class="px-2.5 py-2">Segment</th><th class="px-2.5 py-2 text-right">n</th><th class="px-2.5 py-2 text-right">+7d</th><th class="px-2.5 py-2 text-right">+30d</th><th class="px-2.5 py-2 text-right">+90d</th><th class="px-2.5 py-2 text-right">p (30d)</th></tr>' +
            '</thead>' +
            '<tbody>' +
            rows.map(function (r) {
              var hs = r.g.horizons || {};
              var a7 = hs['7d'] || {}, a30 = hs['30d'] || {}, a90 = hs['90d'] || {};
              return '<tr class="border-t border-slate-800/80">' +
                '<td class="px-2.5 py-1.5 font-semibold text-slate-200">' + esc(r.name) + '</td>' +
                '<td class="px-2.5 py-1.5 text-right font-mono text-slate-300">' + esc(r.g.count || 0) + '</td>' +
                '<td class="px-2.5 py-1.5 text-right font-mono ' + pctColor(a7.median_pct) + '">' + (a7.win_rate_pct !== null && a7.win_rate_pct !== undefined ? fmtNum(a7.win_rate_pct, 0) + '% (' + fmtPct(a7.median_pct) + ')' : '–') + '</td>' +
                '<td class="px-2.5 py-1.5 text-right font-mono ' + pctColor(a30.median_pct) + '">' + (a30.win_rate_pct !== null && a30.win_rate_pct !== undefined ? fmtNum(a30.win_rate_pct, 0) + '% (' + fmtPct(a30.median_pct) + ')' : '–') + '</td>' +
                '<td class="px-2.5 py-1.5 text-right font-mono ' + pctColor(a90.median_pct) + '">' + (a90.win_rate_pct !== null && a90.win_rate_pct !== undefined ? fmtNum(a90.win_rate_pct, 0) + '% (' + fmtPct(a90.median_pct) + ')' : '–') + '</td>' +
                '<td class="px-2.5 py-1.5 text-right font-mono ' + ((a30.p_value !== null && a30.p_value < 0.05) ? 'text-emerald-300' : 'text-slate-400') + '">' + (a30.p_value !== null && a30.p_value !== undefined ? fmtNum(a30.p_value, 3) : '–') + '</td>' +
              '</tr>';
            }).join('') +
            '</tbody>' +
          '</table>' +
        '</div>' +
        '<div class="mt-2.5 rounded-xl bg-slate-950/60 border border-slate-800/80 px-3 py-2 text-[11px] text-slate-300 flex flex-wrap gap-x-4 gap-y-1">' +
          '<span><b>Konkrete Level-Trades:</b> ' + esc(lvl.total_with_levels || 0) + '</span>' +
          '<span class="text-emerald-300">TP: ' + esc(lvl.tp_hits || 0) + '</span>' +
          '<span class="text-rose-300">SL: ' + esc(lvl.sl_hits || 0) + '</span>' +
          '<span class="text-slate-400">Offen/Unfilled: ' + esc((lvl.open_timeout || 0) + (lvl.not_filled || 0)) + '</span>' +
          '<span>Mean R: <b class="font-mono ' + pctColor(lvl.mean_r) + '">' + (lvl.mean_r !== null && lvl.mean_r !== undefined ? fmtNum(lvl.mean_r, 2) + 'R' : '–') + '</b></span>' +
        '</div>';
    }

    var simEl = $('xa-simulation-box');
    if (simEl) {
      if (!sim.available) {
        simEl.innerHTML = '<div class="text-xs text-slate-400">Keine auswertbaren BTC-Calls für Timing-Simulation vorhanden.</div>';
      } else {
        var bh = sim.btc_buy_hold || {};
        var lc = sim.long_cash || {};
        var ls = sim.long_short || {};
        var ctx = sim.btc_24m_context || {};
        simEl.innerHTML =
          '<div class="text-xs font-bold text-white mb-2 flex items-center justify-between flex-wrap gap-1">' +
            '<span>⏱️ BTC-Timing-Simulation (Zero-Lookahead ab ' + esc(sim.start_date) + ')</span>' +
            '<span class="text-[10px] font-mono text-slate-400">' + esc(sim.btc_calls_used || 0) + ' BTC-Calls · ' + esc(sim.regime_switches || 0) + ' Wechsel</span>' +
          '</div>' +
          '<div class="grid grid-cols-3 gap-2 mb-3">' +
            '<div class="rounded-xl bg-slate-950/75 border border-slate-800 p-2.5">' +
              '<div class="text-[10px] text-slate-400 uppercase">BTC Buy &amp; Hold</div>' +
              '<div class="text-sm font-bold font-mono ' + pctColor(bh.return_pct) + '">' + fmtPct(bh.return_pct) + '</div>' +
              '<div class="text-[10px] text-rose-300/80 font-mono">MaxDD: ' + fmtPct(bh.max_drawdown_pct) + '</div>' +
            '</div>' +
            '<div class="rounded-xl bg-slate-950/75 border border-cyan-500/30 p-2.5">' +
              '<div class="text-[10px] text-cyan-300 uppercase">Folge: Long / Cash</div>' +
              '<div class="text-sm font-bold font-mono ' + pctColor(lc.return_pct) + '">' + fmtPct(lc.return_pct) + '</div>' +
              '<div class="text-[10px] text-slate-400 font-mono">MaxDD: ' + fmtPct(lc.max_drawdown_pct) + ' · Alpha ' + fmtPct(lc.alpha_vs_bh_pct) + '</div>' +
            '</div>' +
            '<div class="rounded-xl bg-slate-950/75 border border-amber-500/30 p-2.5">' +
              '<div class="text-[10px] text-amber-300 uppercase">Folge: Long / Short</div>' +
              '<div class="text-sm font-bold font-mono ' + pctColor(ls.return_pct) + '">' + fmtPct(ls.return_pct) + '</div>' +
              '<div class="text-[10px] text-slate-400 font-mono">MaxDD: ' + fmtPct(ls.max_drawdown_pct) + ' · Alpha ' + fmtPct(ls.alpha_vs_bh_pct) + '</div>' +
            '</div>' +
          '</div>' +
          renderTimingSvg(sim.monthly_curve) +
          (ctx.start_price ? '<div class="text-[10px] font-mono text-slate-500 mt-1.5">24M BTC-Spanne: ' + fmtPrice(ctx.low_price) + ' – ' + fmtPrice(ctx.high_price) + ' (Start ' + fmtPrice(ctx.start_price) + ' &rarr; Ende ' + fmtPrice(ctx.end_price) + ')</div>' : '');
      }
    }
  }

  function renderOpusAudit(acc) {
    var el = $('xa-opus-box');
    if (!el) return;
    var o = acc.opus_audit || {};
    var ba = o.behavioral_audit || {};
    var cal = acc.calibration_meta || {};

    var auditItems = [
      { title: 'Flip-Flop- &amp; Konsistenz-Check', txt: ba.flip_flop_analysis },
      { title: 'Broken-Clock-Analyse', txt: ba.broken_clock_analysis },
      { title: 'Regime-Glück vs. echtes Alpha', txt: ba.regime_luck_vs_alpha },
      { title: 'Fundamental vs. Reine TA', txt: ba.fundamental_vs_ta_verdict },
      { title: 'Risiko- &amp; Drawdown-Ehrlichkeit', txt: ba.risk_honesty }
    ].filter(function (x) { return x.txt; });

    var notable = (o.notable_calls || []).map(function (nc) {
      var u = safeUrl('https://x.com/' + acc.handle + '/status/' + String(nc.tweet_id || ''));
      var tCls = nc.type === 'BEST' ? 'bg-emerald-500/20 text-emerald-300' : (nc.type === 'WORST' ? 'bg-rose-500/20 text-rose-300' : 'bg-amber-500/20 text-amber-300');
      return '<div class="rounded-lg bg-slate-950/70 border border-slate-800 px-3 py-2 text-[11px]">' +
        '<div class="flex items-center gap-2 mb-1">' +
          '<span class="px-1.5 py-0.5 rounded font-mono text-[9px] font-bold ' + tCls + '">' + esc(nc.type || 'NOTE') + '</span>' +
          '<span class="font-mono text-slate-400">' + esc(nc.date || '') + '</span>' +
          (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer" class="ml-auto text-cyan-300 hover:underline font-mono text-[10px]">Tweet öffnen ↗</a>' : '') +
        '</div>' +
        '<div class="text-slate-300">' + esc(nc.note_de || '') + '</div>' +
      '</div>';
    }).join('');

    el.innerHTML =
      '<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-2.5 border-b border-slate-800/80">' +
        '<div class="flex items-center gap-2">' +
          '<span class="text-base">🏛️</span>' +
          '<span class="text-xs font-bold text-white">Claude Opus 5.5 Forensik- &amp; Fundamental-Gutachten</span>' +
          '<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30">effort=' + esc(o.effort || 'high') + '</span>' +
        '</div>' +
        '<div class="text-[10px] font-mono text-slate-400">Blinde Kalibrierung: ' + esc(cal.checked_count || 0) + ' geprüft, ' + esc(cal.override_count || 0) + ' korrigiert</div>' +
      '</div>' +
      '<p class="text-xs text-slate-200 leading-relaxed bg-slate-950/60 border border-slate-800/80 rounded-xl p-3">' + esc(o.executive_summary_de || 'Kein Gutachten verfügbar.') + '</p>' +
      '<div class="grid grid-cols-1 md:grid-cols-2 gap-3">' +
        '<div class="rounded-xl bg-emerald-950/15 border border-emerald-500/25 p-3">' +
          '<div class="text-[11px] font-bold text-emerald-300 mb-1.5">✅ Stärken</div>' +
          '<ul class="space-y-1 text-[11px] text-slate-300 list-disc list-inside">' +
            (o.strengths || []).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') +
          '</ul>' +
        '</div>' +
        '<div class="rounded-xl bg-rose-950/15 border border-rose-500/25 p-3">' +
          '<div class="text-[11px] font-bold text-rose-300 mb-1.5">⚠️ Schwächen &amp; Biases</div>' +
          '<ul class="space-y-1 text-[11px] text-slate-300 list-disc list-inside">' +
            (o.weaknesses_and_biases || []).map(function (w) { return '<li>' + esc(w) + '</li>'; }).join('') +
          '</ul>' +
        '</div>' +
      '</div>' +
      (auditItems.length
        ? '<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">' +
            auditItems.map(function (it) {
              return '<div class="rounded-xl bg-slate-950/60 border border-slate-800 p-2.5">' +
                '<div class="text-[10px] font-bold uppercase tracking-wide text-cyan-300 mb-1">' + it.title + '</div>' +
                '<div class="text-[11px] text-slate-300 leading-relaxed">' + esc(it.txt) + '</div>' +
              '</div>';
            }).join('') +
          '</div>'
        : '') +
      (notable ? '<div class="space-y-1.5"><div class="text-[11px] font-bold text-slate-300">🔍 Auffällige Einzel-Calls</div><div class="grid grid-cols-1 md:grid-cols-3 gap-2">' + notable + '</div></div>' : '') +
      (o.actionable_recommendation_de
        ? '<div class="rounded-xl bg-cyan-950/25 border border-cyan-500/30 px-3 py-2 text-[11px] text-cyan-100"><b>Empfehlung:</b> ' + esc(o.actionable_recommendation_de) + '</div>'
        : '');
  }

  function filteredCalls(acc) {
    var list = (acc.calls || []).slice();
    var q = state.search.trim().toLowerCase();
    list = list.filter(function (c) {
      if (state.category !== 'ALL' && c.category !== state.category) return false;
      if (state.direction !== 'ALL' && c.direction !== state.direction) return false;
      if (state.clusterOnly && !c.is_cluster_head) return false;
      if (q) {
        var hay = (c.asset + ' ' + c.summary_de + ' ' + c.text + ' ' + c.reasoning_type).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });

    var cmp = {
      date_desc: function (a, b) { return (b.created_at_ts || 0) - (a.created_at_ts || 0); },
      date_asc:  function (a, b) { return (a.created_at_ts || 0) - (b.created_at_ts || 0); },
      ret30_desc: function (a, b) { return ((b.returns_pct || {})['30d'] || -999) - ((a.returns_pct || {})['30d'] || -999); },
      ret30_asc:  function (a, b) { return ((a.returns_pct || {})['30d'] || 999) - ((b.returns_pct || {})['30d'] || 999); },
      fund_desc:  function (a, b) { return (b.opus_fundamental_score || b.grok_fundamental_score || 0) - (a.opus_fundamental_score || a.grok_fundamental_score || 0); }
    };
    list.sort(cmp[state.sort] || cmp.date_desc);
    return list;
  }

  function renderCallsTable(acc) {
    var tbody = $('xa-tbody');
    if (!tbody) return;
    var rows = filteredCalls(acc);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="px-3 py-6 text-center text-xs text-slate-500">Keine Calls für die aktuelle Filterung.</td></tr>';
    } else {
      tbody.innerHTML = rows.map(function (c) {
        var catMeta = CAT_BADGES[c.category] || { label: c.category, cls: 'bg-slate-800 text-slate-300 border-slate-700' };
        var dirCls = c.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-rose-500/20 text-rose-300 border-rose-500/40';
        var r7 = (c.returns_pct || {})['7d'];
        var r30 = (c.returns_pct || {})['30d'];
        var r90 = (c.returns_pct || {})['90d'];
        var fund = c.opus_fundamental_score !== null && c.opus_fundamental_score !== undefined ? c.opus_fundamental_score : c.grok_fundamental_score;
        var u = safeUrl(c.url);
        var flags = (c.red_flags || []).map(function (f) {
          return '<span class="inline-block px-1.5 py-0.2 rounded text-[9px] bg-rose-500/15 text-rose-300 border border-rose-500/30" title="' + esc(RED_FLAG_LABELS[f] || f) + '">' + esc(RED_FLAG_LABELS[f] || f) + '</span>';
        }).join(' ');
        var ovBadge = c.opus_category_override ? '<span class="ml-1 px-1 py-0.2 rounded text-[9px] bg-purple-500/20 text-purple-300 border border-purple-500/30" title="Opus hat Kategorie von ' + esc(c.grok_category) + ' korrigiert">Opus-Korr</span>' : '';
        var clBadge = c.is_cluster_head
          ? '<span class="px-1.5 py-0.2 rounded text-[9px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">' + esc(c.cluster_id || 'HEAD') + '</span>'
          : '<span class="text-[9px] font-mono text-slate-500">' + esc(c.cluster_id || '') + '</span>';

        return '<tr class="border-t border-slate-800/80 hover:bg-slate-800/30 align-top">' +
          '<td class="px-2.5 py-2 whitespace-nowrap text-[11px] font-mono text-slate-300">' +
            '<div>' + fmtDate(c.created_at_utc) + '</div>' +
            '<div class="mt-0.5">' + clBadge + '</div>' +
          '</td>' +
          '<td class="px-2.5 py-2 whitespace-nowrap">' +
            '<div class="flex items-center gap-1">' +
              '<span class="font-bold text-xs text-white">' + esc(c.asset) + '</span>' +
              '<span class="px-1.5 py-0.2 rounded border text-[9px] font-mono font-bold ' + dirCls + '">' + esc(c.direction) + '</span>' +
            '</div>' +
            '<div class="mt-1"><span class="px-1.5 py-0.2 rounded border text-[9px] font-semibold ' + catMeta.cls + '">' + esc(catMeta.label) + '</span>' + ovBadge + '</div>' +
          '</td>' +
          '<td class="px-2.5 py-2 text-[11px] text-slate-200 max-w-md">' +
            '<div>' + esc(c.summary_de || c.text) + '</div>' +
            (flags ? '<div class="mt-1 flex flex-wrap gap-1">' + flags + '</div>' : '') +
            '<div class="mt-1 flex items-center gap-3 text-[10px] text-slate-500 font-mono">' +
              '<span>' + esc(c.reasoning_type || '') + '</span>' +
              (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer" class="text-cyan-300 hover:underline">Tweet ↗</a>' : '') +
            '</div>' +
          '</td>' +
          '<td class="px-2.5 py-2 text-right font-mono text-[11px] text-slate-300 whitespace-nowrap">' + fmtPrice(c.t0_price) + '</td>' +
          '<td class="px-2.5 py-2 text-right font-mono text-[11px] whitespace-nowrap ' + pctColor(r7) + '">' + fmtPct(r7) + '</td>' +
          '<td class="px-2.5 py-2 text-right font-mono text-[11px] whitespace-nowrap ' + pctColor(r30) + '">' + fmtPct(r30) + '</td>' +
          '<td class="px-2.5 py-2 text-right font-mono text-[11px] whitespace-nowrap ' + pctColor(r90) + '">' + fmtPct(r90) + '</td>' +
          '<td class="px-2.5 py-2 text-right font-mono text-[10px] whitespace-nowrap">' +
            '<span class="text-emerald-300">' + fmtPct(c.mfe_pct) + '</span> / <span class="text-rose-300">' + fmtPct(c.mae_pct) + '</span>' +
          '</td>' +
          '<td class="px-2.5 py-2 text-right font-mono text-[11px] whitespace-nowrap">' +
            '<span class="font-bold ' + scoreColor(fund) + '">' + (fund !== null && fund !== undefined ? esc(fund) : '–') + '</span>' +
            '<div class="text-[9px] text-slate-500">G:' + esc(c.grok_fundamental_score !== undefined ? c.grok_fundamental_score : '–') + '</div>' +
          '</td>' +
        '</tr>';
      }).join('');
    }
    var shown = $('xa-shown');
    if (shown) shown.textContent = rows.length + ' von ' + (acc.calls || []).length + ' Calls angezeigt';
  }

  function renderExcludedDetails(acc) {
    var co = acc.chart_only_tweets || [];
    var coSum = $('xa-chartonly-summary');
    var coList = $('xa-chartonly-list');
    if (coSum) coSum.textContent = 'CHART_ONLY-Posts (' + co.length + ') – strikt aus Trefferquote ausgeschlossen (Aussage nur im Bild)';
    if (coList) {
      coList.innerHTML = co.length
        ? co.map(function (t) {
            var u = safeUrl(t.url);
            return '<div class="rounded-lg border border-slate-800/80 bg-slate-900/50 px-2.5 py-1.5 text-[11px]">' +
              '<div class="flex items-center justify-between text-[10px] font-mono text-slate-400">' +
                '<span>' + fmtDate(t.created_at_utc) + ' · ' + esc(t.asset || '–') + '</span>' +
                (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer" class="text-cyan-300 hover:underline">Tweet ↗</a>' : '') +
              '</div>' +
              '<div class="text-slate-300 mt-0.5">' + esc(t.summary_de || t.text) + '</div>' +
            '</div>';
          }).join('')
        : '<div class="text-[11px] text-slate-500">Keine CHART_ONLY-Posts vorhanden.</div>';
    }

    var unf = acc.unfalsifiable_tweets || [];
    var unfSum = $('xa-unfalsifiable-summary');
    var unfList = $('xa-unfalsifiable-list');
    if (unfSum) unfSum.textContent = 'UNFALSIFIABLE-Posts (' + unf.length + ') – vage / beidseitig abgesicherte Aussagen';
    if (unfList) {
      unfList.innerHTML = unf.length
        ? unf.map(function (t) {
            var u = safeUrl(t.url);
            return '<div class="rounded-lg border border-slate-800/80 bg-slate-900/50 px-2.5 py-1.5 text-[11px]">' +
              '<div class="flex items-center justify-between text-[10px] font-mono text-slate-400">' +
                '<span>' + fmtDate(t.created_at_utc) + ' · ' + esc(t.asset || '–') + '</span>' +
                (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer" class="text-cyan-300 hover:underline">Tweet ↗</a>' : '') +
              '</div>' +
              '<div class="text-slate-300 mt-0.5">' + esc(t.summary_de || t.text) + '</div>' +
            '</div>';
          }).join('')
        : '<div class="text-[11px] text-slate-500">Keine vagen Aussagen gezählt.</div>';
    }
  }

  function renderAll() {
    var acc = currentAccount();
    if (!acc) {
      var hero = $('xa-hero-box');
      if (hero) hero.innerHTML = '<div class="text-xs text-slate-400 p-4 text-center">Noch keine X-Audit-Daten vorhanden. Starte <code>python3 run_x_audit.py --handle Roman_Trading</code>.</div>';
      return;
    }
    state.selectedHandle = acc.handle;
    renderHeader(acc);
    renderHeroAndKpis(acc);
    renderComparisonAndSimulation(acc);
    renderOpusAudit(acc);
    renderCallsTable(acc);
    renderExcludedDetails(acc);
  }

  function bindControls() {
    var sel = $('xa-account-select');
    if (sel) sel.addEventListener('change', function () { state.selectedHandle = sel.value; renderAll(); });

    var s = $('xa-search');
    if (s) s.addEventListener('input', function () { state.search = s.value; renderCallsTable(currentAccount()); });

    var d = $('xa-dir');
    if (d) d.addEventListener('change', function () { state.direction = d.value; renderCallsTable(currentAccount()); });

    var so = $('xa-sort');
    if (so) so.addEventListener('change', function () { state.sort = so.value; renderCallsTable(currentAccount()); });

    var cl = $('xa-cluster-only');
    if (cl) cl.addEventListener('change', function () { state.clusterOnly = cl.checked; renderCallsTable(currentAccount()); });

    var catBtns = document.querySelectorAll('[data-xa-cat]');
    Array.prototype.forEach.call(catBtns, function (b) {
      b.addEventListener('click', function () {
        state.category = b.getAttribute('data-xa-cat');
        Array.prototype.forEach.call(catBtns, function (x) {
          var on = x.getAttribute('data-xa-cat') === state.category;
          x.classList.toggle('bg-cyan-500', on);
          x.classList.toggle('text-slate-950', on);
          x.classList.toggle('text-slate-300', !on);
        });
        renderCallsTable(currentAccount());
      });
    });
  }

  function init() {
    if (!$('x-audit-section')) return;
    bindControls();
    fetch('x_audit_results.json?nocache=' + Date.now())
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        if (!d || !Array.isArray(d.accounts)) throw new Error('Ungültiges Datenformat');
        state.data = d;
        if (d.accounts.length) state.selectedHandle = d.accounts[0].handle;
        renderAll();
      })
      .catch(function (e) {
        var tbody = $('xa-tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="9" class="px-3 py-6 text-center text-xs text-rose-300">X-Audit-Daten konnten nicht geladen werden: ' + esc(e.message) + '</td></tr>';
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
