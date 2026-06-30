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

  /* ─── Chart.js dark defaults ─── */
  if (typeof Chart !== 'undefined') {
    Chart.defaults.color = 'rgba(245,240,232,0.55)';
    Chart.defaults.borderColor = 'rgba(245,240,232,0.07)';
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
