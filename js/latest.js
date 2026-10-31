/* Fills [data-latest="path"] text and [data-latest-href="path"] links from latest.json, where path is dotted
 * ("version", "files.zip", "pi.image"). latest.json is written by the P25X repo's scripts/release_kelly.py --publish. */
(function () {
  'use strict';
  const get = (o, path) => path.split('.').reduce((v, k) => (v == null ? v : v[k]), o);
  const set = (L) => {
    document.querySelectorAll('[data-latest]').forEach((el) => {
      const v = get(L, el.getAttribute('data-latest'));
      if (v != null) el.textContent = v;
    });
    document.querySelectorAll('[data-latest-href]').forEach((el) => {
      const v = get(L, el.getAttribute('data-latest-href'));
      if (v) el.href = v;
    });
  };
  fetch('latest.json', { cache: 'no-cache' }).then((r) => r.json()).then(set).catch(() => {
    document.querySelectorAll('[data-latest]').forEach((el) => { el.textContent = '(not available right now)'; });
  });
})();
