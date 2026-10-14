/**
 * Verifies the Cloudflare Access login on every API request, so the Worker is safe even if the Access policy is
 * missing or misconfigured. Fails closed: with no Access settings the API refuses to run (except in local dev).
 * See https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
 */
import type { Deps, Env } from './env';

interface Jwk extends JsonWebKey { kid?: string }
let certCache: { domain: string; at: number; keys: Jwk[] } | null = null;
const CERT_TTL_MS = 60 * 60 * 1000;

const b64url = (s: string): Uint8Array => {
  const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '='));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
};
const json = (s: string) => JSON.parse(new TextDecoder().decode(b64url(s)));

async function certs(domain: string, deps: Deps, force = false): Promise<Jwk[]> {
  const nowMs = deps.now().getTime();
  if (!force && certCache && certCache.domain === domain && nowMs - certCache.at < CERT_TTL_MS) return certCache.keys;
  const res = await deps.fetch(`https://${domain}/cdn-cgi/access/certs`);
  if (!res.ok) throw new Error(`could not load Access certs (${res.status})`);
  const keys = ((await res.json()) as { keys: Jwk[] }).keys;
  certCache = { domain, at: nowMs, keys };
  return keys;
}

export function resetCertCache() { certCache = null; }

/** Returns the token's claims, or throws. */
export async function verifyAccessJwt(token: string, env: Env, deps: Deps): Promise<{ email?: string; sub?: string }> {
  const [h, p, sig] = token.split('.');
  if (!h || !p || !sig) throw new Error('malformed token');
  const header = json(h);
  if (header.alg !== 'RS256') throw new Error('unexpected algorithm');
  const domain = env.ACCESS_TEAM_DOMAIN!;
  let jwk = (await certs(domain, deps)).find((k) => k.kid === header.kid);
  if (!jwk) jwk = (await certs(domain, deps, true)).find((k) => k.kid === header.kid);   // key rotation
  if (!jwk) throw new Error('unknown signing key');
  const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
  const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64url(sig), new TextEncoder().encode(`${h}.${p}`));
  if (!ok) throw new Error('bad signature');
  const claims = json(p);
  const aud: string[] = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!aud.includes(env.ACCESS_AUD!)) throw new Error('wrong audience');
  if (claims.iss !== `https://${domain}`) throw new Error('wrong issuer');
  const now = deps.now().getTime() / 1000;
  if (typeof claims.exp !== 'number' || claims.exp <= now) throw new Error('token expired');
  if (typeof claims.nbf === 'number' && claims.nbf > now + 60) throw new Error('token not yet valid');
  return claims;
}

const err = (status: number, error: string) =>
  new Response(JSON.stringify({ error }), { status, headers: { 'content-type': 'application/json' } });

/** null = allowed; otherwise the response to send. */
export async function checkAccess(req: Request, env: Env, deps: Deps): Promise<Response | null> {
  if (env.ALLOW_UNAUTHENTICATED === 'true') return null;
  if (!env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) {
    return err(503, 'Cloudflare Access is not configured: set ACCESS_TEAM_DOMAIN and ACCESS_AUD (see README), or ALLOW_UNAUTHENTICATED=true for local dev.');
  }
  const cookie = /(?:^|;\s*)CF_Authorization=([^;]+)/.exec(req.headers.get('cookie') ?? '')?.[1];
  const token = req.headers.get('cf-access-jwt-assertion') ?? cookie;
  if (!token) return err(401, 'Not logged in through Cloudflare Access.');
  try {
    await verifyAccessJwt(token, env, deps);
    return null;
  } catch {
    return err(403, 'Access token rejected.');
  }
}
