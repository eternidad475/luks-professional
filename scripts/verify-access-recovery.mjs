import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const html = await readFile(new URL('../caseflow_studio_v96.html', import.meta.url), 'utf8');
const gate = html.match(/<script id="cf-phase1-beta-gate-v2">([\s\S]*?)<\/script>/)?.[1];
assert.ok(gate, 'Actual production gate script must exist');
function region(start, end) {
  const i = gate.indexOf(start), j = gate.indexOf(end, i + start.length);
  assert.ok(i >= 0 && j > i, `Source region: ${start}`);
  return gate.slice(i, j);
}
const source = region('  var curBilling=null;', '  function isAdmin()')
  + region('  function showGate(view)', '  var _exportHooked=')
  + region('  async function evaluateSession(session)', '\n  function start()');
const session = id => ({ user: { id } });
const allowed = { data: { role: 'developer' }, error: null };
const denied = { data: { role: 'user', beta_access: false }, error: null };
const empty = { data: [], error: null };
const error = (status, code = 'restricted', message = 'request failed') => ({ status, error: { code, message } });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
function harness(responses = {}, authResult = { data: { session: session('owner') } }) {
  const calls = [], nodes = new Map(), deadlines = new Map();
  let timerId = 0;
  let unlocks = 0, authCalls = 0, writes = 0, reloads = 0;
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, { style: {}, textContent: '', disabled: false, classList: { add() {}, remove() {} } });
    return nodes.get(id);
  };
  const ctx = vm.createContext({
    console, Date, AbortController,
    setTimeout(fn, ms) { const id = ++timerId; deadlines.set(id, { fn, ms }); return id; },
    clearTimeout(id) { deadlines.delete(id); },
    window: {}, curProfile: null, curSession: null, subActive: false,
    PRIVILEGED: ['developer', 'co_developer', 'admin'], _signinLogged: false,
    wrap: node('wrap'), logoutBtn: null, badge: null, el: node,
    unlockApp: () => { unlocks++; },
    localStorage: { setItem() { writes++; }, removeItem() { writes++; }, clear() { writes++; } },
    location: { reload() { reloads++; } },
    sb: {
      auth: { getSession: async () => { authCalls++; return typeof authResult === 'function' ? authResult() : authResult; } },
      from(table) {
        const call = { table, uid: null, columns: null }; calls.push(call);
        const builder = {
          select(columns) { call.columns = columns; return this; },
          eq(_name, uid) { call.uid = uid; return this; }, in() { return this; },
          order() { return this; }, is() { return this; },
          single() { return this; }, limit() { return this; },
          abortSignal(signal) { call.signal = signal; return this; },
          then(resolve, reject) { return finish().then(resolve, reject); }
        };
        async function finish() {
          const entry = responses[table];
          if (typeof entry === 'function') return entry(call);
          if (Array.isArray(entry)) return entry.shift();
          return entry ?? (table === 'profiles' ? denied : empty);
        }
        return builder;
      }
    }
  });
  vm.runInContext(source, ctx);
  return { ctx, calls, nodes, node, evaluate: s => ctx.evaluateSession(s), retry: () => ctx.retryAccess(),
    deadlines,
    get unlocks() { return unlocks; }, get authCalls() { return authCalls; },
    get writes() { return writes; }, get reloads() { return reloads; },
    get view() { return ['Auth','Invite','Unavailable'].find(v => node(`cfG2${v}View`).style.display === 'block'); }
  };
}
let passed = 0;
async function test(name, fn) { await fn(); passed++; console.log(`PASS ${name}`); }
await test('quota 402 stops queries and does not unlock or request invitation', async () => {
  const h = harness({ profiles: error(402) }); await h.evaluate(session('owner'));
  assert.equal(h.view, 'Unavailable'); assert.equal(h.unlocks, 0); assert.equal(h.calls.length, 1);
  assert.match(h.node('cfG2UnavailableMsg').textContent, /利用制限/);
});
await test('quota text without HTTP status is recognized', async () => {
  const h = harness({ profiles: error(0, '', 'exceed_storage_size_quota') }); await h.evaluate(session('owner'));
  assert.equal(h.ctx.accessFailure, 'quota');
});
await test('transport exception preserves fail-closed unavailable state', async () => {
  const h = harness({ profiles: () => { throw new Error('network unavailable'); } }); await h.evaluate(session('owner'));
  assert.equal(h.view, 'Unavailable'); assert.equal(h.unlocks, 0); assert.equal(h.calls.length, 1);
});
await test('shared deadline aborts hanging access and is cleared', async () => {
  const h = harness({ profiles: call => new Promise(resolve => {
    call.signal.addEventListener('abort', () => resolve(error(0, 'AbortError', 'request aborted')), { once: true });
  }) });
  const pending = h.evaluate(session('owner')); await Promise.resolve();
  assert.equal(h.deadlines.size, 1); const deadline = [...h.deadlines.values()][0];
  assert.equal(deadline.ms, 20000); deadline.fn(); await pending;
  assert.equal(h.view, 'Unavailable'); assert.equal(h.unlocks, 0); assert.equal(h.deadlines.size, 0);
});
await test('valid denied profile retains invitation flow', async () => {
  const h = harness({ profiles: denied }); await h.evaluate(session('owner'));
  assert.equal(h.view, 'Invite'); assert.equal(h.unlocks, 0);
});
await test('valid permitted profile unlocks', async () => {
  const h = harness({ profiles: allowed }); await h.evaluate(session('owner')); assert.equal(h.unlocks, 1);
});
await test('legacy missing profile columns use narrow fallback', async () => {
  for (const code of ['42703', 'PGRST204']) {
    const h = harness({ profiles: [error(400, code), allowed] }); await h.evaluate(session('owner'));
    assert.equal(h.unlocks, 1); assert.equal(h.calls.filter(c => c.table === 'profiles').length, 2);
    assert.ok(!h.calls[1].columns.includes('display_name'));
  }
});
await test('unrelated profile error does not trigger schema fallback', async () => {
  const h = harness({ profiles: error(403, '42501', 'schema cache denied') }); await h.evaluate(session('owner'));
  assert.equal(h.calls.length, 1); assert.equal(h.view, 'Unavailable');
});
await test('missing optional subscription tables remain compatible', async () => {
  const h = harness({ profiles: allowed, subscriptions: error(404, '42P01'), billing_subscriptions: error(404, 'PGRST205') });
  await h.evaluate(session('owner')); assert.equal(h.unlocks, 1);
});
await test('subscription and billing failures cannot become membership denial', async () => {
  for (const table of ['subscriptions', 'billing_subscriptions']) {
    const h = harness({ profiles: allowed, [table]: error(500) }); await h.evaluate(session('owner'));
    assert.equal(h.view, 'Unavailable'); assert.equal(h.unlocks, 0);
  }
});
await test('workspace quota error prevents unlock', async () => {
  const h = harness({ profiles: allowed, workspaces: error(402) }); await h.evaluate(session('owner'));
  assert.equal(h.view, 'Unavailable'); assert.equal(h.unlocks, 0);
});
await test('no session requires login without remote access', async () => {
  const h = harness(); await h.evaluate(null); assert.equal(h.view, 'Auth'); assert.equal(h.calls.length, 0);
});
await test('late access success cannot undo sign-out', async () => {
  const d = deferred(), h = harness({ profiles: () => d.promise }); const old = h.evaluate(session('old'));
  await h.evaluate(null); d.resolve(allowed); await old;
  assert.equal(h.view, 'Auth'); assert.equal(h.unlocks, 0); assert.equal(h.ctx.curProfile, null);
});
await test('late old session cannot unlock over new denied session', async () => {
  const d = deferred(), h = harness({ profiles: call => call.uid === 'old' ? d.promise : denied });
  const old = h.evaluate(session('old')); await h.evaluate(session('new')); d.resolve(allowed); await old;
  assert.equal(h.view, 'Invite'); assert.equal(h.unlocks, 0); assert.equal(h.ctx.curSession.user.id, 'new');
});
await test('retry is single-flight and does not reload or mutate storage', async () => {
  const d = deferred(), h = harness({ profiles: error(402) }, () => d.promise);
  const pending = h.retry(); await h.retry(); assert.equal(h.authCalls, 1); assert.equal(h.node('cfG2Retry').disabled, true);
  d.resolve({ data: { session: session('owner') } }); await pending;
  assert.equal(h.node('cfG2Retry').disabled, false); assert.equal(h.reloads, 0); assert.equal(h.writes, 0);
  assert.equal(h.view, 'Unavailable');
});
await test('late retry session response cannot undo sign-out', async () => {
  const d = deferred(), h = harness({ profiles: allowed }, () => d.promise);
  const pending = h.retry(); await h.evaluate(null);
  d.resolve({ data: { session: session('owner') } }); await pending;
  assert.equal(h.view, 'Auth'); assert.equal(h.unlocks, 0); assert.equal(h.ctx.curSession, null);
});
await test('all inline classic scripts parse', () => {
  let count = 0;
  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
    const attrs = match[1]; if (/\bsrc\s*=/.test(attrs) || /\btype\s*=\s*["'](?:module|application\/ld\+json|application\/json)/i.test(attrs)) continue;
    if (!match[2].trim()) continue;
    new vm.Script(match[2], { filename: `inline-script-${++count}` });
  }
  assert.ok(count > 20); console.log(`  ${count} inline scripts parsed`);
});
console.log(`${passed} access recovery checks passed (synthetic data only)`);
