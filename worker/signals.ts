/** Stock and weather fetchers (ports of the Python providers). Run in the Worker because Yahoo sends no CORS headers. */
import type { Deps } from './env';
import { BadRequest } from './errors';

export interface Series { label: string; values: number[]; times: string[] }

const DATE = /^\d{4}-\d\d-\d\d$/;
const need = (cond: unknown, msg: string): void => { if (!cond) throw new BadRequest(msg); };
const num = (v: unknown, name: string, lo: number, hi: number): number => {
  const n = Number(v);
  need(Number.isFinite(n) && n >= lo && n <= hi, `${name} must be a number between ${lo} and ${hi}`);
  return n;
};
const date = (v: unknown, name: string): string => { need(typeof v === 'string' && DATE.test(v) && !Number.isNaN(Date.parse(v)), `${name} must be YYYY-MM-DD`); return v as string; };

/** Validated, normalized spec (no label) -> used as the cache key. */
export function normalizeSpec(spec: any): Record<string, string | number> {
  need(spec && typeof spec === 'object', 'spec must be an object');
  const start = date(spec.start, 'start'), end = date(spec.end, 'end');
  need(start <= end, 'start must not be after end');
  need((Date.parse(end) - Date.parse(start)) / 864e5 <= 366 * 30, 'date range too long (max 30 years)');
  if (spec.provider === 'yahoo') {
    need(typeof spec.symbol === 'string' && /^[A-Za-z0-9.^=-]{1,15}$/.test(spec.symbol), 'invalid symbol');
    const field = spec.field ?? 'close';
    need(['close', 'volume', 'return'].includes(field), 'field must be close, volume or return');
    return { provider: 'yahoo', symbol: spec.symbol.toUpperCase(), field, start, end };
  }
  if (spec.provider === 'open_meteo') {
    const variable = spec.variable ?? 'temperature_2m';
    need(typeof variable === 'string' && /^[a-z0-9_]{1,40}$/.test(variable), 'invalid variable');
    return { provider: 'open_meteo', lat: num(spec.lat, 'lat', -90, 90), lon: num(spec.lon, 'lon', -180, 180), variable, start, end };
  }
  throw new BadRequest(`provider must be yahoo or open_meteo, got ${JSON.stringify(spec.provider)}`);
}

export const defaultLabel = (n: Record<string, string | number>): string =>
  n.provider === 'yahoo' ? `${n.symbol}-${n.field}` : String(n.variable);

const UA = 'Mozilla/5.0 (compatible; agent-art/0.1)';

async function get(url: string, deps: Deps): Promise<any> {
  const res = await deps.fetch(url, { headers: { 'user-agent': UA, accept: 'application/json' } });
  if (!res.ok) throw new Error(`upstream ${new URL(url).hostname} answered ${res.status}`);
  return res.json();
}

const day = (t: number) => new Date(t * 1000).toISOString().slice(0, 10);

export async function fetchSeries(n: Record<string, string | number>, deps: Deps): Promise<Omit<Series, 'label'>> {
  if (n.provider === 'yahoo') {
    const p1 = Math.floor(Date.parse(String(n.start)) / 1000), p2 = Math.floor(Date.parse(String(n.end)) / 1000);
    const data = await get(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(String(n.symbol))}?period1=${p1}&period2=${p2}&interval=1d`, deps);
    const r = data?.chart?.result?.[0];
    if (!r) throw new Error(`yahoo returned no data for ${n.symbol}: ${JSON.stringify(data?.chart?.error ?? null)}`);
    const q = r.indicators.quote[0];
    const rows: [number, number, number][] = [];
    (r.timestamp as number[]).forEach((t, i) => { if (q.close[i] != null && q.volume[i] != null) rows.push([t, q.close[i], q.volume[i]]); });
    need(rows.length >= 2, 'fewer than 2 trading days in that range');
    const close = rows.map((x) => x[1]);
    const values = n.field === 'volume' ? rows.map((x) => x[2])
      : n.field === 'return' ? close.map((c, i) => (i === 0 ? 0 : ((c - close[i - 1]) / close[i - 1]) * 100))
      : close;
    return { values, times: rows.map((x) => day(x[0])) };
  }
  const q = new URLSearchParams({ latitude: String(n.lat), longitude: String(n.lon), start_date: String(n.start), end_date: String(n.end), hourly: String(n.variable) });
  const data = await get(`https://archive-api.open-meteo.com/v1/archive?${q}`, deps);
  const times: string[] = data?.hourly?.time, vals: (number | null)[] = data?.hourly?.[String(n.variable)];
  if (!times || !vals) throw new Error(`open-meteo returned no "${n.variable}" data: ${JSON.stringify(data?.reason ?? null)}`);
  const keep = times.map((t, i) => [t, vals[i]] as const).filter(([, v]) => v !== null);
  need(keep.length >= 2, 'fewer than 2 data points in that range');
  return { values: keep.map(([, v]) => v as number), times: keep.map(([t]) => t) };
}
