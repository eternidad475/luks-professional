// POST /api/csp-report
// CSP violation report sink for the Content-Security-Policy-Report-Only policy.
// PRIVACY: logs ONLY the violated directive and the scheme+host of the blocked/document
// URI — never the full URL, never query strings, never request bodies, never any patient
// data. This exists so the Report-Only policy can be evaluated before enforcing.

function hostOnly(u) {
  // Reduce any URL to "scheme://host" — drop path, query and fragment (which could carry
  // routing/query data). Non-URL tokens like 'inline'/'eval' pass through unchanged.
  try {
    if (!u) return null;
    const s = String(u);
    if (s === 'inline' || s === 'eval' || s === 'self' || s === 'data') return s;
    const m = /^([a-z][a-z0-9+.-]*:)\/\/([^/?#]+)/i.exec(s);
    if (m) return m[1] + '//' + m[2];
    const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(s);
    return scheme ? scheme[1] + ':' : null;
  } catch (e) { return null; }
}

module.exports = async (req, res) => {
  // Accept only POST; anything else is a no-op 204 (never leak details).
  if (req.method !== 'POST') { res.status(204).end(); return; }
  try {
    let body = req.body;
    if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { body = null; } }
    const r = (body && (body['csp-report'] || body.cspReport || body)) || {};
    const directive = String(r['violated-directive'] || r['effective-directive'] || '').slice(0, 80);
    const blocked = hostOnly(r['blocked-uri']);
    const docHost = hostOnly(r['document-uri']);
    // One compact, sanitized line. No path, no query, no PHI.
    console.warn('[csp-report]', JSON.stringify({ directive, blocked, doc: docHost }));
  } catch (e) {
    // Never throw / never echo the body.
  }
  res.status(204).end();
};
