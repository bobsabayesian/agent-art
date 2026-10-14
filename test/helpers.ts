import type { Deps, Env } from '../worker/env';

/** Minimal in-memory R2. */
export class FakeR2 {
  objs = new Map<string, { body: string; httpMetadata?: { contentType?: string }; uploaded: Date }>();
  puts = 0;
  async put(key: string, value: string, opts?: { httpMetadata?: { contentType?: string } }) {
    this.puts++;
    this.objs.set(key, { body: String(value), httpMetadata: opts?.httpMetadata, uploaded: new Date('2026-10-14T12:00:00Z') });
  }
  async get(key: string) {
    const o = this.objs.get(key);
    if (!o) return null;
    return { body: new Response(o.body).body, httpMetadata: o.httpMetadata, json: async () => JSON.parse(o.body), text: async () => o.body };
  }
  async list(opts: { prefix?: string; delimiter?: string; cursor?: string } = {}) {
    const prefix = opts.prefix ?? '';
    const keys = [...this.objs.keys()].filter((k) => k.startsWith(prefix)).sort();
    if (opts.delimiter) {
      const dirs = new Set<string>();
      for (const k of keys) { const i = k.indexOf(opts.delimiter, prefix.length); if (i >= 0) dirs.add(k.slice(0, i + 1)); }
      return { objects: [], delimitedPrefixes: [...dirs], truncated: false, cursor: undefined };
    }
    return { objects: keys.map((key) => ({ key, size: this.objs.get(key)!.body.length, uploaded: this.objs.get(key)!.uploaded })), delimitedPrefixes: [], truncated: false, cursor: undefined };
  }
}

export const NOW = new Date('2026-10-14T12:00:00Z');

export function makeEnv(over: Partial<Env> = {}): Env & { BUCKET: FakeR2 & R2Bucket } {
  return {
    ASSETS: { fetch: async () => new Response('asset') } as unknown as Fetcher,
    BUCKET: new FakeR2() as unknown as FakeR2 & R2Bucket,
    ALLOW_UNAUTHENTICATED: 'true',
    ...over,
  } as Env & { BUCKET: FakeR2 & R2Bucket };
}

export const deps = (fetchImpl: typeof fetch = async () => new Response('{}')): Deps => ({ fetch: fetchImpl, now: () => NOW });

export const post = (path: string, body: unknown, headers: Record<string, string> = {}) =>
  new Request(`https://agent-art.test${path}`, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: JSON.stringify(body) });
export const get = (path: string, headers: Record<string, string> = {}) => new Request(`https://agent-art.test${path}`, { headers });
