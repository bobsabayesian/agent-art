import { beforeEach, describe, expect, it } from 'vitest';
import { checkAccess, resetCertCache } from '../worker/access';
import { deps, get, NOW } from './helpers';

const TEAM = 'myteam.cloudflareaccess.com', AUD = 'aud-tag-123';
const enc = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');

async function keypair(kid: string) {
  const kp = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']) as CryptoKeyPair;
  const jwk = { ...(await crypto.subtle.exportKey('jwk', kp.publicKey)), kid, alg: 'RS256', use: 'sig' };
  return { priv: kp.privateKey, jwk };
}
async function token(priv: CryptoKey, kid: string, over: Record<string, unknown> = {}, alg = 'RS256') {
  const h = enc({ alg, kid, typ: 'JWT' });
  const p = enc({ aud: [AUD], iss: `https://${TEAM}`, exp: NOW.getTime() / 1000 + 3600, email: 'me@example.com', ...over });
  const sig = Buffer.from(await crypto.subtle.sign('RSASSA-PKCS1-v1_5', priv, new TextEncoder().encode(`${h}.${p}`))).toString('base64url');
  return `${h}.${p}.${sig}`;
}
const env = { ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD } as any;

describe('Cloudflare Access check', () => {
  let a: Awaited<ReturnType<typeof keypair>>, certHits: number, d: ReturnType<typeof deps>;
  beforeEach(async () => {
    resetCertCache();
    a = await keypair('k1'); certHits = 0;
    d = deps(async () => { certHits++; return new Response(JSON.stringify({ keys: [a.jwk] })); });
  });
  const status = async (req: Request, e = env) => (await checkAccess(req, e, d))?.status ?? 200;

  it('accepts a valid token from the header or the cookie', async () => {
    const t = await token(a.priv, 'k1');
    expect(await status(get('/api/x', { 'cf-access-jwt-assertion': t }))).toBe(200);
    expect(await status(get('/api/x', { cookie: `a=b; CF_Authorization=${t}` }))).toBe(200);
  });
  it('caches the signing keys', async () => {
    const t = await token(a.priv, 'k1');
    await status(get('/api/x', { 'cf-access-jwt-assertion': t })); await status(get('/api/x', { 'cf-access-jwt-assertion': t }));
    expect(certHits).toBe(1);
  });
  it('refetches keys once when the kid is unknown (rotation)', async () => {
    const b = await keypair('k2');
    d = deps(async () => { certHits++; return new Response(JSON.stringify({ keys: certHits === 1 ? [a.jwk] : [a.jwk, b.jwk] })); });
    await status(get('/api/x', { 'cf-access-jwt-assertion': await token(a.priv, 'k1') }));
    expect(await status(get('/api/x', { 'cf-access-jwt-assertion': await token(b.priv, 'k2') }))).toBe(200);
    expect(certHits).toBe(2);
  });
  it.each([
    ['wrong audience', { aud: ['other'] }],
    ['expired', { exp: NOW.getTime() / 1000 - 10 }],
    ['wrong issuer', { iss: 'https://evil.example' }],
    ['not yet valid', { nbf: NOW.getTime() / 1000 + 3600 }],
  ])('rejects %s', async (_n, over) => {
    expect(await status(get('/api/x', { 'cf-access-jwt-assertion': await token(a.priv, 'k1', over) }))).toBe(403);
  });
  it('rejects a token signed by another key, alg none, garbage, or nothing', async () => {
    const evil = await keypair('k1');
    expect(await status(get('/api/x', { 'cf-access-jwt-assertion': await token(evil.priv, 'k1') }))).toBe(403);
    expect(await status(get('/api/x', { 'cf-access-jwt-assertion': await token(a.priv, 'k1', {}, 'none') }))).toBe(403);
    expect(await status(get('/api/x', { 'cf-access-jwt-assertion': 'nope' }))).toBe(403);
    expect(await status(get('/api/x'))).toBe(401);
  });
  it('fails closed when Access is not configured, unless local dev opts out', async () => {
    expect(await status(get('/api/x'), {} as any)).toBe(503);
    expect(await status(get('/api/x'), { ACCESS_TEAM_DOMAIN: TEAM } as any)).toBe(503);
    expect(await status(get('/api/x'), { ALLOW_UNAUTHENTICATED: 'true' } as any)).toBe(200);
    expect(await status(get('/api/x'), { ALLOW_UNAUTHENTICATED: 'yes' } as any)).toBe(503);
  });
});
