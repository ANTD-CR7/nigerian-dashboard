/* NPEDATA — Shared page utilities */
(function () {

  /* ─── Navbar Scroll ─── */
  var nav = document.querySelector('.navbar');
  if (nav) {
    function checkScroll() { nav.classList.toggle('scrolled', window.scrollY > 40); }
    window.addEventListener('scroll', checkScroll, { passive: true });
    checkScroll();
  }

  /* ─── Mobile Menu ─── */
  var burger = document.getElementById('nav-burger');
  var mobileMenu = document.getElementById('mobile-menu');
  if (burger && mobileMenu) {
    burger.addEventListener('click', function(e) {
      e.stopPropagation();
      mobileMenu.classList.toggle('open');
    });
    document.addEventListener('click', function(e) {
      if (!e.target.closest('.navbar') && !e.target.closest('#mobile-menu')) {
        mobileMenu.classList.remove('open');
      }
    });
    mobileMenu.querySelectorAll('a').forEach(function(link) {
      link.addEventListener('click', function() { mobileMenu.classList.remove('open'); });
    });
  }

  /* ─── Reveal Animations ─── */
  if ('IntersectionObserver' in window) {
    var revealObs = new IntersectionObserver(function(entries) {
      entries.forEach(function(e, i) {
        if (e.isIntersecting) {
          setTimeout(function() { e.target.classList.add('visible'); }, i * 80);
        }
      });
    }, { threshold: 0.1 });
    document.querySelectorAll('.reveal').forEach(function(el) { revealObs.observe(el); });
  } else {
    document.querySelectorAll('.reveal').forEach(function(el) { el.classList.add('visible'); });
  }

  /* ─── Chart.js dark defaults + terminal plugins ─── */
  if (typeof Chart !== 'undefined') {
    Chart.defaults.color = 'rgba(245,240,232,0.55)';
    Chart.defaults.borderColor = 'rgba(245,240,232,0.07)';

    /* Terminal crosshair: dashed cross at the hovered point, plus a gold
       date pill on the x-axis and a value pill on the y-axis (readout). */
    Chart.register({
      id: 'npCrosshair',
      afterDatasetsDraw: function (chart) {
        var act = chart.getActiveElements && chart.getActiveElements();
        if (!act || !act.length) return;
        var el = act[0].element;
        if (!el || !isFinite(el.x)) return;
        var a = chart.chartArea, ctx = chart.ctx;
        var fmt = chart.$endLabelFormat || function (v) {
          return Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
        };
        ctx.save();
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(244,160,23,0.5)';
        ctx.beginPath(); ctx.moveTo(el.x, a.top); ctx.lineTo(el.x, a.bottom); ctx.stroke();
        if (isFinite(el.y)) {
          ctx.beginPath(); ctx.moveTo(a.left, el.y); ctx.lineTo(a.right, el.y); ctx.stroke();
        }
        ctx.setLineDash([]);

        var idx = act[0].index;
        /* x-axis date pill */
        var xlab = (chart.data.labels && chart.data.labels[idx] != null) ? String(chart.data.labels[idx]) : '';
        if (xlab) {
          ctx.font = '600 10px "IBM Plex Mono", monospace';
          ctx.textBaseline = 'middle';
          ctx.textAlign = 'center';
          var w = ctx.measureText(xlab).width + 12, h = 16;
          var x = Math.max(a.left, Math.min(el.x - w / 2, a.right - w));
          npRoundRect(ctx, x, a.bottom + 3, w, h, 3);
          ctx.fillStyle = '#F4A017'; ctx.fill();
          ctx.fillStyle = '#07080d'; ctx.fillText(xlab, x + w / 2, a.bottom + 3 + h / 2 + 0.5);
        }
        /* y-axis value pill (primary active series) */
        var dsi = act[0].datasetIndex;
        var raw = chart.data.datasets[dsi] && chart.data.datasets[dsi].data[idx];
        var yval = (raw && typeof raw === 'object') ? raw.y : raw;
        if (yval != null && isFinite(el.y)) {
          var t = fmt(yval, chart.data.datasets[dsi]);
          ctx.font = '600 10px "IBM Plex Mono", monospace';
          ctx.textBaseline = 'middle';
          ctx.textAlign = 'left';
          var w2 = ctx.measureText(t).width + 10, h2 = 16;
          var yy = Math.max(a.top, Math.min(el.y - h2 / 2, a.bottom - h2));
          var xx = a.left - w2 - 2; if (xx < 1) xx = 1;
          npRoundRect(ctx, xx, yy, w2, h2, 3);
          ctx.fillStyle = '#F4A017'; ctx.fill();
          ctx.fillStyle = '#07080d'; ctx.fillText(t, xx + 5, yy + h2 / 2 + 0.5);
        }
        ctx.restore();
      }
    });

    /* End-of-line value tags — draws "● 1,360" at each line's last point.
       Active only when a chart has chart.$endLabelFormat (set via
       attachEndLabels). Skips bar datasets; de-collides overlapping tags. */
    Chart.register({
      id: 'npEndLabels',
      afterDatasetsDraw: function (chart) {
        var fmt = chart.$endLabelFormat;
        if (!fmt) return;
        var ctx = chart.ctx, a = chart.chartArea, items = [];
        chart.data.datasets.forEach(function (ds, di) {
          var meta = chart.getDatasetMeta(di);
          if (meta.hidden) return;
          if ((ds.type || chart.config.type) === 'bar') return;
          var pts = meta.data, idx = -1;
          for (var i = pts.length - 1; i >= 0; i--) {
            if (ds.data[i] != null && pts[i] && isFinite(pts[i].x) && isFinite(pts[i].y)) { idx = i; break; }
          }
          if (idx < 0) return;
          var p = pts[idx];
          if (p.x < a.left - 1 || p.x > a.right + 1.5) return;
          var raw = ds.data[idx];
          var num = (raw && typeof raw === 'object') ? raw.y : raw;
          if (num == null || !isFinite(num)) return;
          items.push({ y: p.y, py: p.y, px: p.x, text: fmt(num, ds), color: ds.borderColor || '#F5F0E8' });
        });
        if (!items.length) return;
        var bh = 16;
        items.sort(function (m, n) { return m.y - n.y; });
        for (var i = 1; i < items.length; i++) {
          if (items[i].y < items[i - 1].y + bh) items[i].y = items[i - 1].y + bh;
        }
        var over = items[items.length - 1].y - (a.bottom - bh / 2);
        if (over > 0) for (var k = 0; k < items.length; k++) items[k].y -= over;
        ctx.save();
        ctx.font = '600 11px "IBM Plex Mono", monospace';
        ctx.textBaseline = 'middle';
        items.forEach(function (it) {
          var bw = ctx.measureText(it.text).width + 12;
          var bx = it.px + 8, by = it.y - bh / 2;
          ctx.beginPath(); ctx.arc(it.px, it.py, 3, 0, Math.PI * 2); ctx.fillStyle = it.color; ctx.fill();
          ctx.beginPath(); ctx.moveTo(it.px, it.py); ctx.lineTo(bx, it.y);
          ctx.strokeStyle = it.color; ctx.lineWidth = 1; ctx.stroke();
          npRoundRect(ctx, bx, by, bw, bh, 3); ctx.fillStyle = it.color; ctx.fill();
          ctx.fillStyle = '#07080d'; ctx.textAlign = 'left';
          ctx.fillText(it.text, bx + 6, it.y + 0.5);
        });
        ctx.restore();
      }
    });
  }

  /* ─── API Docs copy button ─── */
  document.querySelectorAll('.btn-copy').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var text = btn.dataset.copy || btn.previousElementSibling?.textContent || '';
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() {
          var orig = btn.textContent;
          btn.textContent = 'Copied!';
          btn.style.color = 'var(--green)';
          setTimeout(function() { btn.textContent = orig; btn.style.color = ''; }, 2000);
        });
      }
    });
  });

})();

/* ─── Rounded-rect path helper (used by the terminal chart plugins) ─── */
function npRoundRect(ctx, x, y, w, h, r) {
  if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); return; }
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* ─── End-of-line value tags ───
   Enables the npEndLabels plugin for one chart and reserves right padding
   so the tags fit. formatFn(value, dataset) -> label string.
   Safe to call on every load()/redraw. */
function attachEndLabels(canvasId, formatFn, opts) {
  opts = opts || {};
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var chart = (typeof Chart !== 'undefined' && Chart.getChart) ? Chart.getChart(canvas) : null;
  if (!chart) return;
  chart.$endLabelFormat = formatFn || function (v) {
    return Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
  };
  var pad = opts.pad != null ? opts.pad : 66;
  /* mutate the raw config (not the chart.options resolver proxy) */
  var co = chart.config.options || (chart.config.options = {});
  co.layout = co.layout || {};
  var p = co.layout.padding;
  if (p == null || typeof p === 'number') {
    co.layout.padding = { left: (typeof p === 'number' ? p : 0), right: pad, top: 0, bottom: 0 };
  } else {
    p.right = Math.max(p.right || 0, pad);
  }
  chart.update('none');
}

/* ─── Shared data-load error fallback ─── */
function showLoadError(err) {
  console.error('Load failed:', err);
  document.querySelectorAll('[id^="loading"]').forEach(function(el) {
    el.style.display = 'block';
    el.innerHTML = '<div class="error-state"><span>⚠</span><p>Data temporarily unavailable. <button onclick="location.reload()">Retry</button></p></div>';
  });
}

/* ─── Last-updated timestamp ─── */
var SHARED_SB  = 'https://fjsytcmcxapfbrwvawmu.supabase.co/rest/v1';
var SHARED_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw';
function attachLastUpdated(elId, indicatorId, sourceLabel) {
  var el = document.getElementById(elId);
  if (!el) return;
  fetch(SHARED_SB + '/observations?indicator_id=eq.' + indicatorId + '&select=obs_date&order=obs_date.desc&limit=1', {
    headers: { apikey: SHARED_KEY, Authorization: 'Bearer ' + SHARED_KEY }
  })
    .then(function(r) { return r.json(); })
    .then(function(rows) {
      if (!rows || !rows.length) return;
      var d = new Date(rows[0].obs_date + 'T00:00:00Z');
      var month = d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' });
      var year = d.getUTCFullYear();
      el.textContent = 'Data current to: ' + month + ' ' + year + ' · Source: ' + sourceLabel;
    })
    .catch(function() {});
}

/* ─── Chart takeaway: fill the headline stat above a chart ───
   Populates #<prefix>-value, #<prefix>-change and #<prefix>-meta.
   opts: {
     value:        Number   – current/latest value (required)
     prev:         Number    – previous value, for the change badge (optional)
     prevLabel:    String    – e.g. 'vs prev quarter' (optional)
     dateLabel:    String    – preformatted latest date, e.g. 'Q4 2024' (optional)
     source:       String    – e.g. 'NBS' (optional)
     format:       Function  – value -> string (optional; default thousands+2dp)
     betterWhenUp: Boolean   – true: up is good/green; false: up is bad/red; omit: neutral
   } */
function renderTakeaway(prefix, opts) {
  opts = opts || {};
  var fmt = opts.format || function (v) {
    return Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
  };
  var valEl = document.getElementById(prefix + '-value');
  var chgEl = document.getElementById(prefix + '-change');
  var metaEl = document.getElementById(prefix + '-meta');

  if (valEl && opts.value != null) valEl.textContent = fmt(opts.value);

  if (chgEl) {
    if (opts.prev != null && opts.value != null) {
      var delta = opts.value - opts.prev;
      var flat = Math.abs(delta) < 1e-9;
      var up = delta > 0;
      var arrow = flat ? '→' : (up ? '▲' : '▼');
      var sign = flat ? '' : (up ? '+' : '−');
      chgEl.textContent = arrow + ' ' + sign + fmt(Math.abs(delta)) +
        (opts.prevLabel ? ' ' + opts.prevLabel : '');
      chgEl.className = 'takeaway-change';
      if (flat || opts.betterWhenUp == null) chgEl.classList.add('flat');
      else if (opts.betterWhenUp === true) chgEl.classList.add(up ? 'good' : 'bad');
      else chgEl.classList.add(up ? 'bad' : 'good');
    } else {
      chgEl.textContent = '';
      chgEl.className = 'takeaway-change';
    }
  }

  if (metaEl) {
    var bits = [];
    if (opts.dateLabel) bits.push('Latest ' + opts.dateLabel);
    if (opts.source) bits.push(opts.source);
    metaEl.textContent = bits.join(' · ');
  }
}

/* ─── Terminal-style range selector (1Y / 3Y / 5Y / 10Y / All) ───
   canvasId : id of the chart <canvas>
   isoDates : array of ISO date strings parallel to the chart's x labels
   Adds preset chips above the chart that constrain the x-axis window
   client-side (no refetch). Presets that would show <4 points or exceed
   the data span are hidden automatically. Safe to call on every load(). */
function attachRangeSelector(canvasId, isoDates, opts) {
  opts = opts || {};
  var canvas = document.getElementById(canvasId);
  if (!canvas || !isoDates || isoDates.length < 6) return;
  var chart = (typeof Chart !== 'undefined' && Chart.getChart) ? Chart.getChart(canvas) : null;
  if (!chart || !chart.options.scales || !chart.options.scales.x) return;

  var n = isoDates.length;
  var last = new Date(isoDates[n - 1]);
  var first = new Date(isoDates[0]);
  var spanYears = (last - first) / (365.25 * 864e5);

  function idxForYears(years) {
    var cut = new Date(last);
    cut.setFullYear(cut.getFullYear() - years);
    for (var i = 0; i < n; i++) { if (new Date(isoDates[i]) >= cut) return i; }
    return 0;
  }

  var presets = (opts.presets || [
    { label: '1Y', years: 1 }, { label: '3Y', years: 3 },
    { label: '5Y', years: 5 }, { label: '10Y', years: 10 }
  ]).filter(function (p) {
    if (p.years >= spanYears) return false;
    return (n - idxForYears(p.years)) >= 4;
  });
  presets.push({ label: 'All', years: null });
  if (presets.length < 2) return;

  var wrap = canvas.closest('.chart-wrap, .chart-wrap-lg, .chart-wrap-sm') || canvas.parentElement;
  var host = wrap.parentElement;
  var existing = host.querySelector('.range-selector[data-for="' + canvasId + '"]');
  if (existing) existing.remove();

  var bar = document.createElement('div');
  bar.className = 'range-selector';
  bar.setAttribute('data-for', canvasId);
  host.insertBefore(bar, wrap);

  function apply(p, btn) {
    Array.prototype.forEach.call(bar.children, function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    chart.options.scales.x.min = p.years == null ? undefined : idxForYears(p.years);
    chart.options.scales.x.max = p.years == null ? undefined : (n - 1);
    chart.update('none');
  }
  presets.forEach(function (p) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'range-chip';
    btn.textContent = p.label;
    btn.addEventListener('click', function () { apply(p, btn); });
    bar.appendChild(btn);
  });
  bar.lastChild.classList.add('active'); /* default: All */
}

/* ─── Click-to-sort table columns ─── */
function attachSortableTable(table) {
  if (!table) return;
  table.querySelectorAll('thead th').forEach(function(th, col) {
    var asc = true;
    th.title = 'Click to sort';
    th.addEventListener('click', function() {
      var tbody = th.closest('table').querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b) {
        var aVal = a.cells[col].textContent.replace(/[^0-9.-]/g, '');
        var bVal = b.cells[col].textContent.replace(/[^0-9.-]/g, '');
        var aNum = parseFloat(aVal), bNum = parseFloat(bVal);
        if (!isNaN(aNum) && !isNaN(bNum) && aVal !== '' && bVal !== '') return asc ? aNum - bNum : bNum - aNum;
        var aText = a.cells[col].textContent, bText = b.cells[col].textContent;
        return asc ? aText.localeCompare(bText) : bText.localeCompare(aText);
      });
      rows.forEach(function(r) { tbody.appendChild(r); });
      table.querySelectorAll('thead th').forEach(function(h) {
        h.textContent = h.textContent.replace(' ↑', '').replace(' ↓', '');
        h.classList.remove('sorted-col');
      });
      th.textContent += asc ? ' ↑' : ' ↓';
      th.classList.add('sorted-col');
      asc = !asc;
    });
  });
}

/* ─── Sparkline: inject a tiny inline-SVG trend line into an element ───
   drawSparkline(elId, [{value},…], color) — uses the last ~24 points. */
function drawSparkline(elId, series, color) {
  var el = document.getElementById(elId);
  if (!el || !series || series.length < 2) return;
  var vals = series.slice(-24).map(function (d) { return typeof d === 'object' ? d.value : d; })
                   .filter(function (v) { return v != null && isFinite(v); });
  if (vals.length < 2) return;
  var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals), range = (max - min) || 1;
  var w = 100, h = 40, pad = 3;
  var xy = vals.map(function (v, i) {
    var x = (i / (vals.length - 1)) * w;
    var y = h - pad - ((v - min) / range) * (h - pad * 2);
    return x.toFixed(1) + ',' + y.toFixed(1);
  });
  var path = 'M' + xy.join(' L');
  var lastY = h - pad - ((vals[vals.length - 1] - min) / range) * (h - pad * 2);
  var gid = 'sk-' + elId;
  el.style.background = 'none';
  el.innerHTML =
    '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" width="100%" height="100%" aria-hidden="true">' +
    '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0" stop-color="' + color + '" stop-opacity="0.28"/>' +
    '<stop offset="1" stop-color="' + color + '" stop-opacity="0"/></linearGradient></defs>' +
    '<path d="' + path + ' L' + w + ',' + h + ' L0,' + h + ' Z" fill="url(#' + gid + ')"/>' +
    '<path d="' + path + '" fill="none" stroke="' + color + '" stroke-width="1.6" ' +
    'vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>' +
    '<circle cx="' + w + '" cy="' + lastY.toFixed(1) + '" r="2" fill="' + color + '" vector-effect="non-scaling-stroke"/>' +
    '</svg>';
}

/* ═══════════════════════════════════════════════════════════════════
   Universal analytics core — shared by Compare, the per-indicator
   profile and the homepage panel so every surface can analyse ALL 122
   indicators with one correct implementation.
   ═══════════════════════════════════════════════════════════════════ */

/* Fetch the full indicator catalogue (id, name, unit, source) + category. */
function npeCatalogue() {
  return fetch(SHARED_SB + '/indicators?select=id,name,unit,source&limit=300',
      { headers: { apikey: SHARED_KEY, Authorization: 'Bearer ' + SHARED_KEY } })
    .then(function (r) { return r.json(); })
    .then(function (rows) {
      return rows.map(function (x) { x.category = npeCategory(x.id); return x; })
        .sort(function (a, b) {
          return a.category.localeCompare(b.category) || a.name.localeCompare(b.name);
        });
    });
}

function npeCategory(id) {
  if (id === 'gdp_growth' || id === 'gdp_usd' || id === 'gdp_gdPatCurrentMarketPrices' || id === 'gdp_netTaxesOnProducts') return 'Economy — GDP & Output';
  if (/^gdp_/.test(id)) return 'GDP by Sector';
  if (/^inflation/.test(id)) return 'Inflation';
  if (id === 'mpr') return 'Economy — Rates';
  if (/^(usd|gbp|eur|cny|chf|zar|aed|sar|sdr|cfa|waua)_(buying|central|selling)$/.test(id)) return 'Currency Rates (CBN)';
  if (id === 'exchange_rate' || /_rate$/.test(id)) return 'Currency Rates (CBN)';
  if (/^nfem_/.test(id)) return 'NFEM Market';
  if (/^(fx_reserves|reserves_)/.test(id)) return 'FX Reserves';
  if (/^cbn_annual_/.test(id)) return 'CBN Annual Financials';
  if (/^cbn_/.test(id)) return 'CBN Balance Sheet';
  if (/^currency_circulation/.test(id)) return 'Money Supply';
  return 'Other';
}

/* Some CBN series are stored in scaled Naira but labelled just "NGN": the
   monthly balance sheet is in NGN thousands, the annual series in NGN millions,
   currency-in-circulation in NGN millions. These overrides return the multiplier
   back to base Naira so values display honestly (and adaptively K/M/B/T). */
function npeScale(id) {
  if (/^cbn_annual/.test(id)) return { mul: 1e6 };                                   // NGN millions → Naira
  if (/^(cbn_total|cbn_gold|cbn_govt|cbn_bankers|cbn_currency_issued)/.test(id)) return { mul: 1e3 }; // NGN thousands → Naira
  if (id === 'currency_circulation_full' || id === 'currency_circulation') return { mul: 1e6 };
  return null;
}

function npeAbbrev(v) {
  var a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(2) + 'T';
  if (a >= 1e9) return (v / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (v / 1e6).toFixed(2) + 'M';
  if (a >= 1e3) return (v / 1e3).toFixed(1) + 'K';
  return String(Math.round(v * 100) / 100);
}

/* Scale/unit-aware value formatter for any indicator. */
function npeFormat(v, id, unit) {
  if (v == null || !isFinite(v)) return '—';
  unit = unit || '';
  var sc = npeScale(id);
  if (sc) return '₦' + npeAbbrev(v * sc.mul);
  if (/percent|%/i.test(unit)) return v.toFixed(2) + '%';
  if (/per (usd|gbp|eur|[a-z]{3})|naira per/i.test(unit)) return '₦' + v.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (/usd billion/i.test(unit)) return '$' + v.toFixed(2) + 'B';
  if (/^usd$/i.test(unit)) return '$' + npeAbbrev(v);
  if (/count/i.test(unit)) return Math.round(v).toLocaleString('en-US');
  if (/ngn billions|naira billions/i.test(unit)) return '₦' + (Math.abs(v) >= 1000 ? (v / 1000).toFixed(2) + 'T' : v.toFixed(1) + 'B');
  if (/ngn millions|naira millions/i.test(unit)) return '₦' + (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2) + 'T' : (Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(2) + 'B' : v.toFixed(1) + 'M'));
  if (/ngn thousands|naira thousands/i.test(unit)) return '₦' + (v / 1e9).toFixed(2) + 'T';
  if (/ngn|naira/i.test(unit)) return '₦' + (Math.abs(v) < 1e6 ? v.toLocaleString('en-US', { maximumFractionDigits: 2 }) : npeAbbrev(v));
  return npeAbbrev(v);
}

/* Full analytical profile of a series: stats, OLS trend, YoY, trend-vs-time. */
function npeStats(series) {
  var pts = series.filter(function (d) { return d.value != null && isFinite(d.value); });
  var n = pts.length;
  if (!n) return null;
  var vals = pts.map(function (d) { return d.value; });
  var mean = vals.reduce(function (a, b) { return a + b; }, 0) / n;
  var varSum = vals.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0);
  var std = Math.sqrt(varSum / n);
  var minI = 0, maxI = 0;
  vals.forEach(function (v, i) { if (v < vals[minI]) minI = i; if (v > vals[maxI]) maxI = i; });
  var xm = (n - 1) / 2, num = 0, den = 0;
  vals.forEach(function (v, i) { num += (i - xm) * (v - mean); den += (i - xm) * (i - xm); });
  var slope = den ? num / den : 0, intercept = mean - slope * xm;
  var trendCorr = (den && varSum) ? num / Math.sqrt(den * varSum) : 0;
  var latest = pts[n - 1], prev = n > 1 ? pts[n - 2] : null;
  var pyKey = (parseInt(latest.obs_date.slice(0, 4)) - 1) + latest.obs_date.slice(4);
  var py = pts.find(function (d) { return d.obs_date === pyKey; });
  return {
    n: n, pts: pts, vals: vals, mean: mean, std: std, slope: slope, intercept: intercept, trendCorr: trendCorr,
    latest: latest, prev: prev,
    min: { value: vals[minI], date: pts[minI].obs_date }, max: { value: vals[maxI], date: pts[maxI].obs_date },
    prevChange: prev ? latest.value - prev.value : null,
    yoy: py ? { value: latest.value - py.value, pct: py.value ? (latest.value - py.value) / Math.abs(py.value) * 100 : null, date: py.obs_date } : null,
    trendLine: vals.map(function (_, i) { return slope * i + intercept; })
  };
}

function npeMedianGapDays(series) {
  if (!series || series.length < 2) return null;
  var g = [];
  for (var i = 1; i < series.length; i++) {
    g.push((new Date(series[i].obs_date + 'T00:00:00Z') - new Date(series[i - 1].obs_date + 'T00:00:00Z')) / 864e5);
  }
  g.sort(function (a, b) { return a - b; });
  return g[Math.floor(g.length / 2)];
}
function npeFreq(gap) {
  if (gap == null) return '—';
  if (gap <= 3) return 'daily';
  if (gap <= 45) return 'monthly';
  if (gap <= 135) return 'quarterly';
  return 'annual';
}

/* ─── Inferential statistics: two-tailed p-value + R² for a Pearson r ───
   Uses the Student-t distribution via the regularised incomplete beta
   function (Numerical Recipes betacf/gammln/betai). */
function npeGammaln(x) {
  var cof = [76.18009172947146, -86.50532032941677, 24.01409824083091,
    -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
  var y = x, tmp = x + 5.5; tmp -= (x + 0.5) * Math.log(tmp);
  var ser = 1.000000000190015;
  for (var j = 0; j < 6; j++) { y++; ser += cof[j] / y; }
  return -tmp + Math.log(2.5066282746310005 * ser / x);
}
function npeBetacf(x, a, b) {
  var MAXIT = 200, EPS = 3e-7, FPMIN = 1e-30;
  var qab = a + b, qap = a + 1, qam = a - 1;
  var c = 1, d = 1 - qab * x / qap;
  if (Math.abs(d) < FPMIN) d = FPMIN; d = 1 / d; var h = d;
  for (var m = 1; m <= MAXIT; m++) {
    var m2 = 2 * m;
    var aa = m * (b - m) * x / ((qam + m2) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d; h *= d * c;
    aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d; var del = d * c; h *= del;
    if (Math.abs(del - 1) < EPS) break;
  }
  return h;
}
function npeIbeta(x, a, b) {
  if (x <= 0) return 0; if (x >= 1) return 1;
  var bt = Math.exp(npeGammaln(a + b) - npeGammaln(a) - npeGammaln(b) + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2) ? bt * npeBetacf(x, a, b) / a : 1 - bt * npeBetacf(1 - x, b, a) / b;
}
/* Two-tailed p-value that a correlation r (n observations) differs from 0. */
function npeCorrP(r, n) {
  if (n < 3 || Math.abs(r) >= 1) return (Math.abs(r) >= 1 && n >= 3) ? 0 : null;
  var df = n - 2, t2 = r * r * df / (1 - r * r);
  return npeIbeta(df / (df + t2), df / 2, 0.5);
}
/* Significance summary for a correlation/trend: R², p-value, plain label. */
function npeSig(r, n) {
  var p = npeCorrP(r, n);
  var label = p == null ? 'n too small'
    : (p < 0.001 ? 'p < 0.001' : (p < 0.01 ? 'p < 0.01' : (p < 0.05 ? 'p < 0.05' : 'p = ' + p.toFixed(3))));
  return { r2: r * r, p: p, label: label, significant: p != null && p < 0.05 };
}

/* Fill a <select> with catalogue options grouped by category. */
function npeFillSelect(sel, cat, selectedId) {
  if (!sel) return;
  var groups = {};
  cat.forEach(function (x) { (groups[x.category] = groups[x.category] || []).push(x); });
  var html = '';
  Object.keys(groups).forEach(function (g) {
    html += '<optgroup label="' + g + '">';
    groups[g].forEach(function (x) {
      html += '<option value="' + x.id + '"' + (x.id === selectedId ? ' selected' : '') + '>' + x.name + '</option>';
    });
    html += '</optgroup>';
  });
  sel.innerHTML = html;
}

/* ─── Reader / Analyst detail dial ───
   One global toggle (persisted in localStorage). Reader keeps the plain-
   language story; Analyst reveals every element marked .analyst-only.
   attachAnalystStats() renders a researcher-grade stat panel for a plotted
   series, reusing npeStats/npeFormat so every page shares one correct
   implementation. */
function npeShortDate(d) {
  return new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' });
}

function attachAnalystStats(canvasId, series, indId, unit, label) {
  var canvas = document.getElementById(canvasId);
  if (!canvas || !series || series.length < 2) return;
  var card = canvas.closest('.chart-card');
  if (!card) return;
  var st = npeStats(series);
  if (!st) return;
  var F = function (v) { return npeFormat(v, indId, unit); };
  var freq = npeFreq(npeMedianGapDays(st.pts));
  var sig = npeSig(st.trendCorr, st.n);
  var cv = (st.mean && st.min.value >= 0) ? Math.abs(st.std / st.mean) * 100 : null;
  var dir = st.slope > 1e-9 ? 'Rising' : (st.slope < -1e-9 ? 'Falling' : 'Flat');
  var yr = function (d) { return d ? d.slice(0, 4) : ''; };
  var old = card.querySelector('.analyst-panel[data-for="' + canvasId + '"]');
  if (old) old.remove();
  var el = document.createElement('div');
  el.className = 'analyst-only analyst-panel';
  el.setAttribute('data-for', canvasId);
  el.innerHTML =
    '<div class="ap-head">Analyst detail' + (label ? ' — ' + label : '') + '</div>' +
    '<div class="profile-stats">' + [
      ['Range', F(st.min.value) + ' – ' + F(st.max.value), 'min ' + yr(st.min.date) + ' · max ' + yr(st.max.date)],
      ['Mean', F(st.mean), 'over ' + st.n + ' observations'],
      ['Volatility (σ)', F(st.std), cv != null ? cv.toFixed(0) + '% of mean' : 'standard deviation'],
      ['Trend (OLS)', dir, 'R²=' + (st.trendCorr * st.trendCorr).toFixed(2) + ' · ' + sig.label],
      ['Coverage', st.n + ' · ' + freq, npeShortDate(st.pts[0].obs_date) + ' → ' + npeShortDate(st.latest.obs_date)]
    ].map(function (t) {
      return '<div class="prof-tile"><div class="pt-label">' + t[0] + '</div><div class="pt-value">' + t[1] + '</div><div class="pt-sub">' + t[2] + '</div></div>';
    }).join('') + '</div>' +
    '<div class="ap-note">Computed client-side from the plotted series · methods and limitations documented on the <a href="about.html">About page</a>.</div>';
  var note = card.querySelector('.source-note');
  if (note) card.insertBefore(el, note); else card.appendChild(el);
}

(function () {
  if (!document.body) return;
  var saved = 'reader';
  try { saved = localStorage.getItem('npe-view') || 'reader'; } catch (e) {}
  if (saved === 'analyst') document.body.classList.add('analyst');

  var toastTimer = null;
  function toast(msg) {
    var t = document.querySelector('.npe-toast');
    if (!t) { t = document.createElement('div'); t.className = 'npe-toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.textContent = msg;
    requestAnimationFrame(function () { t.classList.add('show'); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, 3200);
  }
  window.npeToast = toast;
  function setView(v, announce) {
    document.body.classList.toggle('analyst', v === 'analyst');
    try { localStorage.setItem('npe-view', v); } catch (e) {}
    document.querySelectorAll('.view-toggle button').forEach(function (b) {
      b.classList.toggle('active', b.dataset.view === v);
      b.setAttribute('aria-pressed', b.dataset.view === v ? 'true' : 'false');
    });
    if (!announce) return;
    if (v === 'analyst') {
      var p = document.querySelector('.analyst-panel');
      if (p) {
        toast('Analyst view on — statistical detail revealed under each chart');
        setTimeout(function () { p.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 200);
      } else {
        toast('Analyst view on — open any indicator page to see the statistical detail');
      }
    } else {
      toast('Reader view — plain-language story');
    }
  }
  function buildToggle() {
    var wrap = document.createElement('div');
    wrap.className = 'view-toggle';
    wrap.setAttribute('role', 'group');
    wrap.setAttribute('aria-label', 'Detail level');
    [['reader', 'Reader', 'Plain-language view'], ['analyst', 'Analyst', 'Reveal statistics, trend significance and methodology']].forEach(function (o) {
      var b = document.createElement('button');
      b.type = 'button'; b.dataset.view = o[0]; b.textContent = o[1]; b.title = o[2];
      b.classList.toggle('active', saved === o[0]);
      b.setAttribute('aria-pressed', saved === o[0] ? 'true' : 'false');
      b.addEventListener('click', function () { setView(o[0], true); });
      wrap.appendChild(b);
    });
    return wrap;
  }
  var cta = document.querySelector('.nav-cta');
  if (cta) cta.insertBefore(buildToggle(), cta.firstChild);
  var mob = document.getElementById('mobile-menu');
  if (mob) {
    var g = document.createElement('div'); g.className = 'mob-group'; g.textContent = 'Detail level';
    mob.appendChild(g); mob.appendChild(buildToggle());
  }
})();

/* ═══════════════════════════════════════════════════════════════════
   Research Toolkit — share-view links, PNG export with attribution,
   and a "cite this data" generator. One implementation for every page.
   ═══════════════════════════════════════════════════════════════════ */
var NPE_SOURCE_ORGS = { CBN: 'Central Bank of Nigeria', NBS: 'National Bureau of Statistics', WB: 'World Bank', 'World Bank': 'World Bank' };

function npeCopy(text, doneMsg) {
  function done() { if (window.npeToast) npeToast(doneMsg); }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, function () { npePromptCopy(text); });
  } else { npePromptCopy(text); }
}
function npePromptCopy(text) { window.prompt('Copy with Ctrl+C:', text); }

/* attachChartTools(canvasId, {indicator, name, source})
   Adds ⤴ Share view · ⬇ PNG · ” Cite buttons beside the chart's controls. */
function attachChartTools(canvasId, opts) {
  opts = opts || {};
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var card = canvas.closest('.chart-card');
  if (!card || card.querySelector('.chart-tools[data-for="' + canvasId + '"]')) return;

  var bar = document.createElement('span');
  bar.className = 'chart-tools';
  bar.setAttribute('data-for', canvasId);

  function mkBtn(text, title, fn) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'btn-chart-tool'; b.textContent = text; b.title = title;
    b.addEventListener('click', fn);
    bar.appendChild(b);
  }

  mkBtn('⤴ Share view', 'Copy a link that reproduces this exact view', function () {
    var url = new URL(window.location.href.split('#')[0].split('?')[0]);
    var s = document.getElementById('flt-start'), e = document.getElementById('flt-end');
    if (s && s.value) url.searchParams.set('from', s.value);
    if (e && e.value) url.searchParams.set('to', e.value);
    if (document.body.classList.contains('analyst')) url.searchParams.set('view', 'analyst');
    npeCopy(url.toString(), 'Link copied — it reproduces this exact view');
  });

  mkBtn('⬇ PNG', 'Download this chart as an image with attribution', function () {
    var chart = Chart.getChart(canvas);
    if (!chart) return;
    var pad = 38, w = canvas.width, h = canvas.height;
    var out = document.createElement('canvas');
    out.width = w; out.height = h + pad;
    var ctx = out.getContext('2d');
    ctx.fillStyle = '#0d0f18'; ctx.fillRect(0, 0, w, h + pad);
    ctx.drawImage(canvas, 0, 0);
    ctx.strokeStyle = 'rgba(245,240,232,0.12)';
    ctx.beginPath(); ctx.moveTo(12, h + 6); ctx.lineTo(w - 12, h + 6); ctx.stroke();
    ctx.font = '12px "IBM Plex Mono", monospace'; ctx.fillStyle = 'rgba(245,240,232,0.6)';
    ctx.fillText('NPEDATA · ' + (opts.name || canvasId) + ' · Source: ' + (opts.source || 'CBN/NBS/World Bank') + ' · ' + window.location.host, 12, h + 24);
    var a = document.createElement('a');
    a.download = (opts.indicator || canvasId) + '_npedata.png';
    a.href = out.toDataURL('image/png');
    a.click();
    if (window.npeToast) npeToast('Chart image downloaded with attribution');
  });

  mkBtn('” Cite', 'Copy an APA-style citation for this data', function () {
    var now = new Date();
    var retrieved = now.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
    var org = NPE_SOURCE_ORGS[opts.source] || opts.source || 'Central Bank of Nigeria / National Bureau of Statistics';
    var cite = org + '. (' + now.getFullYear() + '). ' + (opts.name || 'Nigerian economic data') +
      ' [Data set]. NPEDATA — Nigerian Public Economic Data Aggregation and Analytics Platform. ' +
      'Retrieved ' + retrieved + ', from ' + window.location.href.split('?')[0];
    npeCopy(cite, 'APA citation copied to clipboard');
  });

  var anchor = card.querySelector('.btn-download') || card.querySelector('.btn-chart-reset');
  if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(bar, anchor.nextSibling);
  else card.appendChild(bar);
}

/* Restore a shared view: ?from=&to= set the date filter, ?view=analyst flips the dial. */
(function () {
  var q = new URLSearchParams(window.location.search);
  if (q.get('view') === 'analyst') {
    try { localStorage.setItem('npe-view', 'analyst'); } catch (e) {}
    document.body.classList.add('analyst');
  }
  var from = q.get('from'), to = q.get('to');
  if (!from || !to) return;
  window.addEventListener('load', function () {
    setTimeout(function () {
      var s = document.getElementById('flt-start'), e = document.getElementById('flt-end'), b = document.getElementById('apply-filter');
      if (s && e && b) {
        s.value = from; e.value = to; b.click();
        if (window.npeToast) npeToast('Shared view restored: ' + from + ' → ' + to);
      }
    }, 700);
  });
})();

/* ═══ Event context layer — one registry, consistent on every chart ═══ */
var NPE_EVENTS = [
  { date: '2020-04', label: 'COVID-19', color: '#e05252' },
  { date: '2023-01', label: 'Naira redesign', color: '#B39DDB' },
  { date: '2023-06', label: 'FX reform', color: '#008751' }
];
/* Returns Chart.js annotation objects for every registry event that falls
   inside the plotted dates (ISO strings, ascending). */
function npeEventAnnotations(isoDates) {
  var out = {};
  if (!isoDates || !isoDates.length) return out;
  NPE_EVENTS.forEach(function (ev, k) {
    var idx = -1;
    for (var i = 0; i < isoDates.length; i++) {
      if (isoDates[i].slice(0, 7) >= ev.date) { idx = i; break; }
    }
    if (idx === -1) return;                                       // event after the plotted window
    if (idx === 0 && isoDates[0].slice(0, 7) > ev.date) return;   // event before the plotted window
    out['npeEvent' + k] = {
      type: 'line', xMin: idx, xMax: idx,
      borderColor: ev.color + '66', borderWidth: 1.5, borderDash: [6, 4],
      label: { display: true, content: ev.label, position: 'end', backgroundColor: ev.color, color: '#fff', font: { size: 11, weight: '600' }, padding: { x: 6, y: 3 }, borderRadius: 2 }
    };
  });
  return out;
}
/* Adds a "⚑ Events" chip into the chart's range-selector bar (if present)
   that toggles the registry annotations on/off. */
function attachEventToggle(canvasId) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var chart = Chart.getChart(canvas);
  if (!chart || !chart.options.plugins || !chart.options.plugins.annotation) return;
  var host = canvas.closest('.chart-card');
  var bar = host && host.querySelector('.range-selector');
  if (!bar || bar.querySelector('.evt-chip')) return;
  var btn = document.createElement('button');
  btn.type = 'button'; btn.className = 'range-chip evt-chip active';
  btn.textContent = '⚑ Events'; btn.title = 'Toggle event markers (COVID-19, FX reform, Naira redesign)';
  btn.addEventListener('click', function () {
    var anns = chart.options.plugins.annotation.annotations || {};
    var on = btn.classList.toggle('active');
    Object.keys(anns).forEach(function (k) {
      if (k.indexOf('npeEvent') === 0) { anns[k].display = on; if (anns[k].label) anns[k].label.display = on; }
    });
    chart.update('none');
  });
  bar.appendChild(btn);
}

/* ─── Command palette (Ctrl/Cmd+K or "/") + scroll UX ─── */
(function () {
  if (!document.body) return;

  var DEST = [
    { label: 'Dashboard', url: 'index.html', cat: 'Main', kw: 'home overview kpis start' },
    { label: 'GDP Growth', url: 'gdp.html', cat: 'Economy', kw: 'gross domestic product output nominal usd' },
    { label: 'Inflation', url: 'inflation.html', cat: 'Economy', kw: 'cpi prices headline food core cost of living' },
    { label: 'Interest Rate', url: 'interest_rate.html', cat: 'Economy', kw: 'mpr monetary policy rate cbn hike' },
    { label: 'Exchange Rate', url: 'exchange_rate.html', cat: 'Currency', kw: 'ngn usd naira dollar fx official' },
    { label: 'Multi-Currency', url: 'multicurrency.html', cat: 'Currency', kw: 'gbp eur cny chf buying selling central spread' },
    { label: 'NFEM Rates', url: 'nfem.html', cat: 'Currency', kw: 'interbank market daily closing weighted' },
    { label: 'Currency Converter', url: 'currency_converter.html', cat: 'Currency', kw: 'convert calculator naira' },
    { label: 'FX Reserves', url: 'reserves.html', cat: 'CBN Data', kw: 'foreign exchange gross liquid blocked buffer' },
    { label: 'Currency in Circulation', url: 'currency_circulation.html', cat: 'CBN Data', kw: 'cash naira redesign money supply' },
    { label: 'Assets & Liabilities', url: 'assets_liabilities.html', cat: 'CBN Data', kw: 'balance sheet gold deposits' },
    { label: 'Financial Statement', url: 'financial_statement.html', cat: 'CBN Data', kw: 'surplus deficit annual income' },
    { label: 'Analytics Overview', url: 'analytics.html', cat: 'Analytics', kw: 'correlation pearson regression' },
    { label: 'Compare Indicators', url: 'compare.html', cat: 'Analytics', kw: 'two side by side correlation' },
    { label: 'API Documentation', url: 'api_docs.html', cat: 'Developer', kw: 'rest endpoints swagger hateoas open json' },
    { label: 'Data Sources', url: 'data_sources.html', cat: 'About', kw: 'cbn nbs world bank provenance' },
    { label: 'About', url: 'about.html', cat: 'About', kw: 'project fyp caleb university' },
    { label: 'System Status', url: 'status.html', cat: 'About', kw: 'health freshness uptime coverage' }
  ];

  var overlay = document.createElement('div');
  overlay.className = 'cmdk-overlay';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', 'Search NPEDATA');
  overlay.innerHTML =
    '<div class="cmdk-box">' +
      '<div class="cmdk-input-row"><span class="cmdk-icon">⌕</span>' +
      '<input class="cmdk-input" type="text" placeholder="Search indicators, pages, the API…" aria-label="Search" autocomplete="off" spellcheck="false">' +
      '<kbd class="cmdk-esc">esc</kbd></div>' +
      '<div class="cmdk-list" role="listbox"></div>' +
      '<div class="cmdk-foot"><span><kbd>↑</kbd><kbd>↓</kbd> navigate</span><span><kbd>↵</kbd> open</span><span class="cmdk-brand">NPEDATA</span></div>' +
    '</div>';
  document.body.appendChild(overlay);

  var input = overlay.querySelector('.cmdk-input');
  var list = overlay.querySelector('.cmdk-list');
  var sel = 0, filtered = DEST.slice(), lastFocus = null;

  function render() {
    list.innerHTML = '';
    if (!filtered.length) { list.innerHTML = '<div class="cmdk-empty">No matches</div>'; return; }
    filtered.forEach(function (d, i) {
      var row = document.createElement('a');
      row.className = 'cmdk-item' + (i === sel ? ' active' : '');
      row.href = d.url;
      row.setAttribute('role', 'option');
      row.innerHTML = '<span class="cmdk-label">' + d.label + '</span><span class="cmdk-cat">' + d.cat + '</span>';
      row.addEventListener('mousemove', function () { if (sel !== i) { sel = i; paint(); } });
      row.addEventListener('click', function (e) { e.preventDefault(); window.location.href = d.url; });
      list.appendChild(row);
    });
  }
  function paint() {
    var items = list.querySelectorAll('.cmdk-item');
    for (var i = 0; i < items.length; i++) items[i].classList.toggle('active', i === sel);
    if (items[sel]) items[sel].scrollIntoView({ block: 'nearest' });
  }
  function filter(q) {
    q = (q || '').trim().toLowerCase();
    filtered = !q ? DEST.slice() : DEST.filter(function (d) {
      return (d.label + ' ' + d.cat + ' ' + d.kw).toLowerCase().indexOf(q) !== -1;
    });
    sel = 0; render();
  }
  function isOpen() { return overlay.classList.contains('open'); }
  function open() {
    lastFocus = document.activeElement;
    overlay.classList.add('open');
    input.value = ''; filter('');
    document.body.style.overflow = 'hidden';
    setTimeout(function () { input.focus(); }, 10);
  }
  function close() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  input.addEventListener('input', function () { filter(input.value); });
  overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
  overlay.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, filtered.length - 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); paint(); }
    else if (e.key === 'Enter') { e.preventDefault(); if (filtered[sel]) window.location.href = filtered[sel].url; }
  });
  document.addEventListener('keydown', function (e) {
    var k = (e.key || '').toLowerCase();
    if ((e.metaKey || e.ctrlKey) && k === 'k') { e.preventDefault(); isOpen() ? close() : open(); }
    else if (k === '/' && !isOpen()) {
      var t = (e.target.tagName || '').toUpperCase();
      if (t !== 'INPUT' && t !== 'TEXTAREA' && t !== 'SELECT' && !e.target.isContentEditable) { e.preventDefault(); open(); }
    }
  });

  var cta = document.querySelector('.nav-cta');
  if (cta) {
    var trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'nav-search';
    trigger.setAttribute('aria-label', 'Search (Ctrl+K)');
    trigger.innerHTML = '<span class="ns-icon">⌕</span><span class="ns-text">Search</span><kbd class="ns-kbd">⌘K</kbd>';
    trigger.addEventListener('click', open);
    cta.insertBefore(trigger, cta.firstChild);
  }

  /* Scroll progress bar + back-to-top */
  var bar = document.createElement('div'); bar.className = 'scroll-progress'; document.body.appendChild(bar);
  var toTop = document.createElement('button');
  toTop.className = 'back-to-top'; toTop.type = 'button';
  toTop.setAttribute('aria-label', 'Back to top'); toTop.innerHTML = '↑';
  toTop.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
  document.body.appendChild(toTop);
  function onScroll() {
    var h = document.documentElement, top = h.scrollTop || document.body.scrollTop;
    var height = h.scrollHeight - h.clientHeight;
    bar.style.width = (height > 0 ? (top / height) * 100 : 0) + '%';
    toTop.classList.toggle('show', top > 600);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();
