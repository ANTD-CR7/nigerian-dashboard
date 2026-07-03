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
