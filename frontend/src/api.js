// Data loading, API calls and the shared upgrade rule (must match docs/contracts.md).

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const UPGRADE_FACTOR = 0.5;

export const BAND_COLOURS = {
  high: [230, 72, 62],
  medium: [240, 170, 50],
  low: [70, 180, 120],
};

export function band(risk) {
  if (risk >= 0.5) return 'high';
  if (risk >= 0.25) return 'medium';
  return 'low';
}

export function counts(buildings) {
  const c = { high: 0, medium: 0, low: 0 };
  for (const b of buildings) c[b.band] += 1;
  return c;
}

// Local fallback for /plan-upgrades so the UI works even if the backend is down.
export function planUpgradesLocal(buildings, budget) {
  const ranked = [...buildings].sort((a, b) => b.risk - a.risk);
  const chosen = new Set(ranked.slice(0, budget).map((b) => b.id));
  const after = buildings.map((b) => {
    if (!chosen.has(b.id)) return { ...b, upgraded: false };
    const vulnerability = +(b.vulnerability * UPGRADE_FACTOR).toFixed(3);
    const risk = +(b.exposure * vulnerability).toFixed(3);
    return { ...b, vulnerability, risk, band: band(risk), upgraded: true };
  });
  return { upgraded: [...chosen], before: counts(buildings), after: counts(after), buildings: after, local: true };
}

async function getJson(path, fallback) {
  try {
    const r = await fetch(path);
    if (!r.ok) throw new Error(r.statusText);
    return await r.json();
  } catch {
    return fallback;
  }
}

export async function loadData() {
  const [track, buildings, risk, labels, validation] = await Promise.all([
    getJson('/data/track.json', []),
    getJson('/data/buildings.geojson', { features: [] }),
    getJson('/data/risk.json', { buildings: [] }),
    getJson('/data/roof_labels.json', {}),
    getJson('/data/validation.json', null),
  ]);
  return { track, buildings, risk: risk.buildings, labels, validation };
}

async function post(path, body) {
  const r = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return r.json();
}

export async function planUpgrades(buildings, budget) {
  try {
    return await post('/plan-upgrades', {
      budget,
      buildings: buildings.map(({ id, exposure, vulnerability, risk, band }) => ({ id, exposure, vulnerability, risk, band })),
    });
  } catch {
    return planUpgradesLocal(buildings, budget);
  }
}

export async function resiliencePlan(areaName, summary) {
  return post('/resilience-plan', { area_name: areaName, summary });
}
