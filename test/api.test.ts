import { describe, expect, it } from 'vitest';
import { handleApi } from '../worker/index';
import { deps, get, makeEnv, post } from './helpers';

const SVG = '<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>';
const SID = '20261014-120000-ab12';
const call = async (req: Request, env = makeEnv(), d = deps()) => { const r = await handleApi(req, env, d); return { r: r!, body: r && (r.headers.get('content-type') ?? '').includes('json') ? await r.json() as any : null }; };

describe('routing and access', () => {
  it('ignores non-API paths (they go to the static assets)', async () => {
    expect(await handleApi(get('/index.html'), makeEnv(), deps())).toBeNull();
  });
  it('refuses API calls when Access is not configured', async () => {
    const { r } = await call(get('/api/health'), makeEnv({ ALLOW_UNAUTHENTICATED: undefined }));
    expect(r.status).toBe(503);
  });
  it('refuses cross-site posts even with a valid login', async () => {
    const { r } = await call(post(`/api/sessions/${SID}/save`, { kind: 'run', config: {} }, { 'sec-fetch-site': 'cross-site' }));
    expect(r.status).toBe(403);
  });
  it('404s unknown API paths', async () => {
    expect((await call(get('/api/nope'))).r.status).toBe(404);
  });
});

describe('saving to R2', () => {
  it('stores a run as a config + svg pair under the session', async () => {
    const env = makeEnv();
    const { r, body } = await call(post(`/api/sessions/${SID}/save`, { kind: 'run', seed: 7, config: { seed: 7, agents: 5 }, svg: SVG }), env);
    expect(r.status).toBe(200);
    expect(body.keys).toEqual([`sessions/${SID}/runs/2026-10-14T12-00-00-000Z-s7.config.json`, `sessions/${SID}/runs/2026-10-14T12-00-00-000Z-s7.svg`]);
    expect(JSON.parse(env.BUCKET.objs.get(body.keys[0])!.body)).toEqual({ seed: 7, agents: 5 });
    expect(env.BUCKET.objs.get(body.keys[1])!.httpMetadata?.contentType).toBe('image/svg+xml');
  });
  it('stores a config-only export in exports/', async () => {
    const env = makeEnv();
    const { body } = await call(post(`/api/sessions/${SID}/save`, { kind: 'export', seed: 3, config: { a: 1 } }), env);
    expect(body.keys).toHaveLength(1);
    expect(body.keys[0]).toMatch(new RegExp(`^sessions/${SID}/exports/.*-s3\\.config\\.json$`));
  });
  it.each([
    ['bad kind', { kind: 'x', config: {} }],
    ['missing config', { kind: 'run' }],
    ['svg that is not svg', { kind: 'run', config: {}, svg: '<script>alert(1)</script>' }],
    ['non-string svg', { kind: 'run', config: {}, svg: 5 }],
  ])('rejects %s with 400', async (_n, b) => {
    expect((await call(post(`/api/sessions/${SID}/save`, b))).r.status).toBe(400);
  });
  it('rejects bad session ids and non-JSON bodies', async () => {
    for (const id of ['short', '..%2F..%2Fx', 'a b c d e f g h']) expect((await call(post(`/api/sessions/${id}/save`, { kind: 'run', config: {} }))).r.status).toBe(400);
    const req = new Request(`https://agent-art.test/api/sessions/${SID}/save`, { method: 'POST', headers: { 'content-type': 'text/plain' }, body: '{}' });
    expect((await call(req)).r.status).toBe(400);
  });
  it('sanitizes the seed in the key', async () => {
    const { body } = await call(post(`/api/sessions/${SID}/save`, { kind: 'run', seed: '../../evil', config: {} }));
    expect(body.keys[0]).toMatch(/-sx\.config\.json$/);
  });
});

describe('listing and reading', () => {
  it('lists sessions newest first and the objects of one session', async () => {
    const env = makeEnv();
    for (const id of ['20261013-090000-aaaa', SID, '20261012-080000-bbbb'])
      await call(post(`/api/sessions/${id}/save`, { kind: 'run', config: {}, svg: SVG }), env);
    await env.BUCKET.put('cache/signals/x.json', '{}');
    expect((await call(get('/api/sessions'), env)).body.sessions).toEqual([SID, '20261013-090000-aaaa', '20261012-080000-bbbb']);
    const objs = (await call(get(`/api/sessions/${SID}`), env)).body.objects;
    expect(objs.map((o: any) => o.key.split('.').slice(-1)[0]).sort()).toEqual(['json', 'svg']);
  });
  it('serves saved objects with a locked-down content policy, and nothing else', async () => {
    const env = makeEnv();
    const { body } = await call(post(`/api/sessions/${SID}/save`, { kind: 'run', config: {}, svg: SVG }), env);
    const svgKey = body.keys[1];
    const { r } = await call(get(`/api/object?key=${encodeURIComponent(svgKey)}`), env);
    expect(r.status).toBe(200);
    expect(r.headers.get('content-type')).toBe('image/svg+xml');
    expect(r.headers.get('content-security-policy')).toContain("default-src 'none'");
    expect(await r.text()).toBe(SVG);
    for (const k of ['cache/signals/x.json', `sessions/${SID}/../other/runs/x.svg`, `sessions/${SID}/runs/a/b.svg`, '', `sessions/${SID}/secrets/x.svg`])
      expect((await call(get(`/api/object?key=${encodeURIComponent(k)}`), env)).r.status).toBe(400);
    expect((await call(get(`/api/object?key=${encodeURIComponent(`sessions/${SID}/runs/missing.svg`)}`), env)).r.status).toBe(404);
  });
});

describe('/api/signal', () => {
  const YAHOO = { chart: { result: [{ timestamp: [1767312000, 1767398400, 1767484800, 1767571200], indicators: { quote: [{ close: [100, 110, null, 99], volume: [10, 20, null, 40] }] } }] } };
  const mock = (payload: unknown, status = 200) => { const calls: string[] = []; return { calls, fetch: (async (u: any) => { calls.push(String(u)); return new Response(JSON.stringify(payload), { status }); }) as typeof fetch }; };
  const spec = (o = {}) => ({ provider: 'yahoo', symbol: 'spy', field: 'return', start: '2026-01-01', end: '2026-01-31', ...o });

  it('fetches Yahoo, drops empty days, computes % returns, and labels the series', async () => {
    const m = mock(YAHOO);
    const { body } = await call(post('/api/signal', { spec: spec() }), makeEnv(), deps(m.fetch));
    expect(body.label).toBe('SPY-return');
    expect(body.times).toHaveLength(3);
    expect(body.values[0]).toBe(0);
    expect(body.values[1]).toBeCloseTo(10); expect(body.values[2]).toBeCloseTo(-10);
    expect(m.calls[0]).toContain('/chart/SPY?');
  });
  it('supports volume/close and custom labels', async () => {
    const v = (await call(post('/api/signal', { spec: spec({ field: 'volume', label: 'vol!' }) }), makeEnv(), deps(mock(YAHOO).fetch))).body;
    expect(v.values).toEqual([10, 20, 40]); expect(v.label).toBe('vol!');
  });
  it('caches in R2 and refetches on refresh', async () => {
    const env = makeEnv(), m = mock(YAHOO);
    const a = (await call(post('/api/signal', { spec: spec() }), env, deps(m.fetch))).body;
    const b = (await call(post('/api/signal', { spec: spec({ label: 'other' }) }), env, deps(m.fetch))).body;   // label is not part of the key
    expect([a.cached, b.cached, m.calls.length]).toEqual([false, true, 1]);
    expect(b.label).toBe('other');
    const c = (await call(post('/api/signal', { spec: spec(), refresh: true }), env, deps(m.fetch))).body;
    expect([c.cached, m.calls.length]).toEqual([false, 2]);
  });
  it('fetches Open-Meteo and skips null hours', async () => {
    const m = mock({ hourly: { time: ['t1', 't2', 't3'], temperature_2m: [1, null, 3] } });
    const { body } = await call(post('/api/signal', { spec: { provider: 'open_meteo', lat: 40.7, lon: -74, start: '2026-09-01', end: '2026-09-02' } }), makeEnv(), deps(m.fetch));
    expect(body).toMatchObject({ label: 'temperature_2m', values: [1, 3], times: ['t1', 't3'] });
    expect(m.calls[0]).toContain('latitude=40.7');
  });
  it.each([
    ['bad symbol', spec({ symbol: 'A/../B' })], ['bad field', spec({ field: 'x' })], ['bad date', spec({ start: 'yesterday' })],
    ['reversed range', spec({ start: '2026-02-01', end: '2026-01-01' })], ['unknown provider', { provider: 'csv' }], ['no spec', null],
    ['bad lat', { provider: 'open_meteo', lat: 99, lon: 0, start: '2026-01-01', end: '2026-01-02' }],
  ])('rejects %s with 400 without calling upstream', async (_n, s) => {
    const m = mock(YAHOO);
    expect((await call(post('/api/signal', { spec: s }), makeEnv(), deps(m.fetch))).r.status).toBe(400);
    expect(m.calls).toHaveLength(0);
  });
  it('reports upstream failures as 502 and does not cache them', async () => {
    const env = makeEnv();
    const { r, body } = await call(post('/api/signal', { spec: spec() }), env, deps(mock({}, 429).fetch));
    expect(r.status).toBe(502); expect(body.error).toContain('429');
    expect(env.BUCKET.puts).toBe(0);
  });
});
