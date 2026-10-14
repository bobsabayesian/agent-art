/** R2 layout:  sessions/<id>/runs/<ts>-s<seed>.{config.json,svg}   sessions/<id>/exports/...   cache/signals/<hash>.json */
import type { Env } from './env';
import { BadRequest } from './errors';

const ID = /^[A-Za-z0-9_-]{8,64}$/;
const KEY = /^sessions\/[A-Za-z0-9_-]{8,64}\/(runs|exports)\/[A-Za-z0-9._-]{1,120}$/;
export const MAX_CONFIG_BYTES = 8_000_000;
export const MAX_SVG_BYTES = 30_000_000;

export const validSessionId = (id: string) => ID.test(id);
export const validObjectKey = (key: string) => KEY.test(key) && !key.includes('..');

/** 2026-10-14T11:52:03.123Z -> 2026-10-14T11-52-03-123Z (sorts chronologically, safe in keys). */
export const stamp = (d: Date) => d.toISOString().replace(/[:.]/g, '-');

export interface SaveBody { kind: 'run' | 'export'; seed?: unknown; config: unknown; svg?: unknown }

export function parseSaveBody(b: any): { kind: 'run' | 'export'; seed: string; config: string; svg?: string } {
  if (!b || typeof b !== 'object') throw new BadRequest('body must be an object');
  if (b.kind !== 'run' && b.kind !== 'export') throw new BadRequest('kind must be "run" or "export"');
  if (!b.config || typeof b.config !== 'object') throw new BadRequest('config is required');
  const config = JSON.stringify(b.config, null, 2);
  if (config.length > MAX_CONFIG_BYTES) throw new BadRequest('config too large');
  let svg: string | undefined;
  if (b.svg !== undefined) {
    if (typeof b.svg !== 'string' || !b.svg.trimStart().startsWith('<?xml') && !b.svg.trimStart().startsWith('<svg')) throw new BadRequest('svg must be SVG text');
    if (b.svg.length > MAX_SVG_BYTES) throw new BadRequest('svg too large');
    svg = b.svg;
  }
  const n = Number(b.seed);
  const seed = Number.isFinite(n) ? String(Math.trunc(Math.abs(n)) % 1e9) : 'x';
  return { kind: b.kind, seed, config, svg };
}

export async function saveBundle(env: Env, sessionId: string, body: unknown, now: Date): Promise<string[]> {
  const { kind, seed, config, svg } = parseSaveBody(body);
  const dir = `sessions/${sessionId}/${kind === 'run' ? 'runs' : 'exports'}`;
  const base = `${dir}/${stamp(now)}-s${seed}`;
  const keys = [`${base}.config.json`];
  await env.BUCKET.put(keys[0], config, { httpMetadata: { contentType: 'application/json' } });
  if (svg !== undefined) {
    keys.push(`${base}.svg`);
    await env.BUCKET.put(keys[1], svg, { httpMetadata: { contentType: 'image/svg+xml' } });
  }
  return keys;
}

export async function listSessions(env: Env): Promise<string[]> {
  const out: string[] = [];
  let cursor: string | undefined;
  do {
    const page = await env.BUCKET.list({ prefix: 'sessions/', delimiter: '/', cursor });
    for (const p of page.delimitedPrefixes) { const id = p.slice('sessions/'.length, -1); if (validSessionId(id)) out.push(id); }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor && out.length < 5000);
  return out.sort().reverse().slice(0, 100);   // ids start with a UTC timestamp: newest first
}

export async function listObjects(env: Env, sessionId: string) {
  const objects: { key: string; size: number; uploaded: string }[] = [];
  let cursor: string | undefined;
  do {
    const page = await env.BUCKET.list({ prefix: `sessions/${sessionId}/`, cursor });
    for (const o of page.objects) objects.push({ key: o.key, size: o.size, uploaded: o.uploaded.toISOString() });
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor && objects.length < 5000);
  return objects;
}
