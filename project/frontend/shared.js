/* NPEDATA — Shared page utilities */
(function () {

  /* ─── Custom Cursor ─── */
  if (window.innerWidth > 768) {
    var dot  = document.createElement('div'); dot.className  = 'cursor-dot';  document.body.appendChild(dot);
    var ring = document.createElement('div'); ring.className = 'cursor-ring'; document.body.appendChild(ring);
    var mx=0, my=0, rx=0, ry=0;
    document.addEventListener('mousemove', function(e) {
      mx = e.clientX; my = e.clientY;
      dot.style.left = mx + 'px'; dot.style.top = my + 'px';
    });
    function animRing() {
      rx += (mx - rx) * 0.12; ry += (my - ry) * 0.12;
      ring.style.left = rx + 'px'; ring.style.top = ry + 'px';
      requestAnimationFrame(animRing);
    }
    animRing();
    document.querySelectorAll('a, button').forEach(function(el) {
      el.addEventListener('mouseenter', function() { ring.style.transform = 'translate(-50%,-50%) scale(1.8)'; });
      el.addEventListener('mouseleave', function() { ring.style.transform = 'translate(-50%,-50%) scale(1)'; });
    });
  }

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
    el.textContent = 'Unable to load data — please refresh';
  });
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
