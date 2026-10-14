import { checkAccess } from './access';
import type { Deps, Env } from './env';
import { BadRequest } from './errors';
import { defaultLabel, fetchSeries, normalizeSpec } from './signals';
import { listObjects, listSessions, saveBundle, validObjectKey, validSessionId } from './store';

const defaults: Deps = { fetch: (...a) => fetch(...a), now: () => new Date() };
const MAX_BODY = 45_000_000;

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json', 'cache-control': 'private, no-store' } });

async function sha256(s: string): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 32);
}

async function readJson(req: Request): Promise<any> {
  if (!(req.headers.get('content-type') ?? '').startsWith('application/json')) throw new BadRequest('expected application/json');
  if (Number(req.headers.get('content-length') ?? 0) > MAX_BODY) throw new BadRequest('request too large');
  try { return await req.json(); } catch { throw new BadRequest('invalid JSON'); }
}

/** Returns a Response for /api/* requests, or null for anything else (which goes to the static assets). */
export async function handleApi(req: Request, env: Env, deps: Deps = defaults): Promise<Response | null> {
  const url = new URL(req.url);
  if (!url.pathname.startsWith('/api/')) return null;

  const denied = await checkAccess(req, env, deps);
  if (denied) return denied;

  // state-changing requests must come from this site, not from another site using the login cookie
  if (req.method !== 'GET' && !['same-origin', 'none', null].includes(req.headers.get('sec-fetch-site'))) return json({ error: 'cross-site request refused' }, 403);

  try {
    const path = url.pathname.slice('/api'.length);

    if (path === '/health' && req.method === 'GET') return json({ ok: true });

    if (path === '/signal' && req.method === 'POST') {
      const body = await readJson(req);
      const spec = normalizeSpec(body.spec);
      const label = typeof body.spec.label === 'string' && body.spec.label ? body.spec.label : defaultLabel(spec);
      const key = `cache/signals/${await sha256(JSON.stringify(spec, Object.keys(spec).sort()))}.json`;
      if (!body.refresh) {
        const hit = await env.BUCKET.get(key);
        if (hit) return json({ label, ...(await hit.json<object>()), cached: true });
      }
      let data;
      try { data = await fetchSeries(spec, deps); }
      catch (e) { if (e instanceof BadRequest) throw e; return json({ error: (e as Error).message }, 502); }
      await env.BUCKET.put(key, JSON.stringify(data), { httpMetadata: { contentType: 'application/json' } });
      return json({ label, ...data, cached: false });
    }

    if (path === '/sessions' && req.method === 'GET') return json({ sessions: await listSessions(env) });

    const m = /^\/sessions\/([^/]+)(\/save)?$/.exec(path);
    if (m) {
      if (!validSessionId(m[1])) return json({ error: 'invalid session id' }, 400);
      if (m[2] && req.method === 'POST') return json({ keys: await saveBundle(env, m[1], await readJson(req), deps.now()) });
      if (!m[2] && req.method === 'GET') return json({ objects: await listObjects(env, m[1]) });
    }

    if (path === '/object' && req.method === 'GET') {
      const key = url.searchParams.get('key') ?? '';
      if (!validObjectKey(key)) return json({ error: 'invalid key' }, 400);
      const obj = await env.BUCKET.get(key);
      if (!obj) return json({ error: 'not found' }, 404);
      const type = obj.httpMetadata?.contentType ?? 'application/octet-stream';
      return new Response(obj.body, {
        headers: {
          'content-type': type,
          'cache-control': 'private, no-store',
          'x-content-type-options': 'nosniff',
          // an SVG opened directly must not be able to run script
          'content-security-policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        },
      });
    }

    return json({ error: 'not found' }, 404);
  } catch (e) {
    if (e instanceof BadRequest) return json({ error: (e as Error).message }, 400);
    return json({ error: `server error: ${(e as Error).message}` }, 500);
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    return (await handleApi(req, env)) ?? env.ASSETS.fetch(req);
  },
};
