(function () {
  var btn  = document.getElementById('nav-toggle');
  var menu = document.getElementById('nav-menu');
  if (!btn || !menu) return;

  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    var open = menu.classList.toggle('nav-open');
    btn.textContent = open ? '✕' : '☰';
    btn.setAttribute('aria-expanded', String(open));
  });

  // Close when a nav link is tapped
  menu.querySelectorAll('a').forEach(function (link) {
    link.addEventListener('click', function () {
      menu.classList.remove('nav-open');
      btn.textContent = '☰';
      btn.setAttribute('aria-expanded', 'false');
    });
  });

  // Close when tapping outside the nav
  document.addEventListener('click', function (e) {
    if (!e.target.closest('nav')) {
      menu.classList.remove('nav-open');
      btn.textContent = '☰';
      btn.setAttribute('aria-expanded', 'false');
    }
  });
})();
