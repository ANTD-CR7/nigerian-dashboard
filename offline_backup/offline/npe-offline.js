/* ─────────────────────────────────────────────────────────────────────────
   NPEDATA OFFLINE SHIM
   Intercepts every network request the site makes and answers it from the
   local snapshot (offline/snapshot.js), so the whole dashboard works with
   no internet at all. Load order in <head>:  snapshot.js  →  this file  →
   (local) chart libs  →  page scripts.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  var SNAP = window.__NPE_SNAPSHOT || { indicators: [], observations: [] };

  // index observations by indicator_id, ascending by date
  var byInd = {};
  SNAP.observations.forEach(function (o) {
    (byInd[o.indicator_id] = byInd[o.indicator_id] || []).push(o);
  });
  Object.keys(byInd).forEach(function (k) {
    byInd[k].sort(function (a, b) { return a.obs_date < b.obs_date ? -1 : a.obs_date > b.obs_date ? 1 : 0; });
  });
  console.log('[NPEDATA offline] snapshot ready:', SNAP.indicators.length, 'indicators,', SNAP.observations.length, 'observations');

  function resp(data, extraHeaders, isText) {
    var body = isText ? data : JSON.stringify(data);
    var headers = { 'Content-Type': isText ? 'text/csv' : 'application/json' };
    if (extraHeaders) Object.keys(extraHeaders).forEach(function (k) { headers[k] = extraHeaders[k]; });
    return Promise.resolve(new Response(body, { status: 200, statusText: 'OK', headers: headers }));
  }

  function getHeader(opts, name) {
    if (!opts || !opts.headers) return null;
    var h = opts.headers;
    if (typeof h.get === 'function') return h.get(name);
    return h[name] || h[name.toLowerCase()] || null;
  }

  // ── Supabase / PostgREST emulation ──────────────────────────────────────
  function handleSupabase(u, opts) {
    var qIdx = u.indexOf('?');
    var path = qIdx < 0 ? u : u.slice(0, qIdx);
    var qs = qIdx < 0 ? '' : u.slice(qIdx + 1);
    var filters = [], select = null, order = null, limit = null, count = false;
    qs.split('&').forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf('='); var k = decodeURIComponent(kv.slice(0, i)); var v = decodeURIComponent(kv.slice(i + 1));
      if (k === 'select') { select = v; if (v === 'count') count = true; }
      else if (k === 'order') order = v;
      else if (k === 'limit') limit = parseInt(v, 10);
      else { var d = v.indexOf('.'); filters.push({ col: k, op: v.slice(0, d), val: v.slice(d + 1) }); }
    });

    if (path.indexOf('/indicators') !== -1) {
      var inds = SNAP.indicators.slice();
      if (limit != null) inds = inds.slice(0, limit);
      return resp(inds);
    }

    // observations
    var ind = null;
    filters.forEach(function (f) { if (f.col === 'indicator_id' && f.op === 'eq') ind = f.val; });
    var rows = ind != null ? (byInd[ind] || []).slice() : SNAP.observations.slice();
    filters.forEach(function (f) {
      if (f.col === 'indicator_id' && f.op === 'eq') return;
      rows = rows.filter(function (r) {
        var c = String(r[f.col]);
        if (f.op === 'eq') return c === f.val;
        if (f.op === 'gte') return c >= f.val;
        if (f.op === 'lte') return c <= f.val;
        if (f.op === 'gt') return c > f.val;
        if (f.op === 'lt') return c < f.val;
        return true;
      });
    });
    if (order) {
      var keys = order.split(',').map(function (o) { var p = o.split('.'); return { col: p[0], desc: p[1] === 'desc' }; });
      rows.sort(function (a, b) {
        for (var i = 0; i < keys.length; i++) { var k = keys[i], av = a[k.col], bv = b[k.col];
          if (av < bv) return k.desc ? 1 : -1; if (av > bv) return k.desc ? -1 : 1; }
        return 0;
      });
    }
    if (count) return resp([{ count: rows.length }], { 'Content-Range': '*/' + rows.length });
    if (limit != null) rows = rows.slice(0, limit);
    var range = getHeader(opts, 'Range');
    if (range) {
      var m = /(\d+)-(\d+)/.exec(range);
      if (m) { var a = +m[1], b = +m[2], total = rows.length; rows = rows.slice(a, b + 1);
        return resp(rows, { 'Content-Range': a + '-' + (a + rows.length - 1) + '/' + total }); }
    }
    return resp(rows);
  }

  // ── Render FastAPI emulation (for the API-docs & Playground demos) ───────
  var HEADLINE = { gdp_growth: 'GDP Growth', inflation: 'Inflation', exchange_rate: 'Exchange Rate NGN/USD', mpr: 'Monetary Policy Rate', fx_reserves: 'FX Reserves' };
  var EP2IND = { gdp: 'gdp_growth', inflation: 'inflation', 'exchange-rate': 'exchange_rate', 'interest-rate': 'mpr', 'fx-reserves': 'fx_reserves', 'currency-circulation': 'currency_circulation', nfem: 'nfem_rate' };
  var BASEAPI = 'https://npedata-api.onrender.com';

  function links(o) { return o; }
  function latest(id) { var a = byInd[id] || []; return a.length ? a[a.length - 1] : null; }

  function handleApi(u, opts) {
    var method = (opts && opts.method || 'GET').toUpperCase();
    var path = u.replace(BASEAPI, '').split('?')[0].replace(/\/$/, '') || '/';

    if (method === 'POST' && path.indexOf('/validate/csv') !== -1) return validateCsv(opts);

    if (path === '/' || path === '') {
      return resp({ name: 'NPEDATA Open API (offline snapshot)', version: 'v1',
        _links: { summary: { href: BASEAPI + '/api/v1/summary' }, coverage: { href: BASEAPI + '/api/v1/coverage' },
          inflation: { href: BASEAPI + '/api/v1/inflation' }, gdp: { href: BASEAPI + '/api/v1/gdp' },
          docs: { href: BASEAPI + '/docs' } } });
    }
    if (path === '/api/v1/summary') {
      var out = {};
      Object.keys(HEADLINE).forEach(function (id) { var l = latest(id); if (l) out[id] = { obs_date: l.obs_date, value: l.value, source: l.source }; });
      out._links = { self: { href: BASEAPI + '/api/v1/summary' }, index: { href: BASEAPI + '/' } };
      return resp(out);
    }
    if (path === '/api/v1/coverage') {
      var cov = SNAP.indicators.slice(0, 40).map(function (x) { var a = byInd[x.id] || [];
        return { indicator_id: x.id, name: x.name, count: a.length, first: a[0] && a[0].obs_date, last: a.length && a[a.length - 1].obs_date, source: x.source }; });
      return resp({ coverage: cov, _links: { self: { href: BASEAPI + '/api/v1/coverage' }, index: { href: BASEAPI + '/' } } });
    }
    // /api/v1/analytics/<id>
    var mA = path.match(/\/api\/v1\/analytics\/(.+)$/);
    if (mA) {
      var id = mA[1], a = byInd[id] || [];
      var vals = a.map(function (r) { return +r.value; });
      var lat = a.length ? a[a.length - 1] : null, prev = a.length > 1 ? a[a.length - 2] : null;
      return resp({ indicator: id, latest: lat, change: (lat && prev) ? (+lat.value - +prev.value) : null,
        n: a.length, min: Math.min.apply(null, vals), max: Math.max.apply(null, vals),
        _links: { self: { href: u }, series: { href: BASEAPI + '/api/v1/' + id }, index: { href: BASEAPI + '/' } } });
    }
    // /api/v1/<endpoint>  → series
    var mE = path.match(/\/api\/v1\/([a-z-]+)$/);
    if (mE) {
      var ind = EP2IND[mE[1]] || mE[1];
      var series = (byInd[ind] || []).map(function (r) { return { obs_date: r.obs_date, value: r.value, source: r.source }; });
      return resp({ indicator: ind, count: series.length, data: series,
        _links: { self: { href: u }, analytics: { href: BASEAPI + '/api/v1/analytics/' + ind }, summary: { href: BASEAPI + '/api/v1/summary' }, index: { href: BASEAPI + '/' } } });
    }
    // fallback
    return resp({ note: 'Offline snapshot — this endpoint is not mocked. Data pages work fully offline; this API demo endpoint needs the live server.', path: path, _links: { index: { href: BASEAPI + '/' } } });
  }

  function validateCsv(opts) {
    // read the multipart/form body or raw text
    var body = opts && opts.body;
    var text = '';
    function run(t) {
      var lines = t.replace(/\r/g, '').split('\n').filter(function (l) { return l.length; });
      var header = (lines.shift() || '').toLowerCase();
      var seen = {}, today = new Date().toISOString().slice(0, 10), verdicts = [], valid = 0;
      lines.forEach(function (line, i) {
        var parts = line.split(','); var d = (parts[0] || '').trim(), v = (parts[1] || '').trim(), reasons = [];
        if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) reasons.push('obs_date must be an ISO date (YYYY-MM-DD)');
        var num = parseFloat(v);
        if (v === '' || isNaN(num) || !isFinite(num)) reasons.push('value must be numeric and finite');
        if (/^\d{4}-\d{2}-\d{2}$/.test(d)) { if (d > today) reasons.push('obs_date is in the future'); if (seen[d]) reasons.push('duplicate obs_date within this file'); seen[d] = 1; }
        if (!reasons.length) valid++;
        verdicts.push({ row: i + 2, status: reasons.length ? 'rejected' : 'valid', reasons: reasons, normalized: reasons.length ? null : { obs_date: d, value: num } });
      });
      return resp({ received: lines.length, valid: valid, rejected: lines.length - valid, written_to_database: false, verdicts: verdicts });
    }
    if (body && typeof body.text === 'function') return body.text().then(run);           // Blob/File
    if (typeof body === 'string') return run(body);
    if (body instanceof FormData) { var f = body.get('file'); if (f && f.text) return f.text().then(run); return run(''); }
    return run('');
  }

  // ── install ─────────────────────────────────────────────────────────────
  window.fetch = function (url, opts) {
    var u = (typeof url === 'string') ? url : (url && url.url) || '';
    try {
      if (u.indexOf('supabase.co') !== -1) return handleSupabase(u, opts);
      if (u.indexOf('onrender.com') !== -1) return handleApi(u, opts);
    } catch (e) { console.warn('[NPEDATA offline] shim error, passing through:', e); }
    return realFetch ? realFetch(url, opts) : Promise.reject(new Error('offline: ' + u));
  };
})();
