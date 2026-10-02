// Data loading, API calls and the restoration model (must match backend/app/restoration.py).

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const WAVE_REDUCTION_PER_100M = 0.13;
const WAVE_REDUCTION_CAP = 0.66;
const SURGE_REDUCTION_M_PER_KM = 0.1;
export const BANDS = ['exposed', 'partial', 'strong'];

export const BAND_COLOURS = {
  exposed: [230, 72, 62],
  partial: [240, 170, 50],
  strong: [60, 190, 140],
};

export const waveReduction = (w) => +Math.min(WAVE_REDUCTION_CAP, (WAVE_REDUCTION_PER_100M * Math.max(0, w)) / 100).toFixed(3);
export const surgeReductionM = (w) => +((SURGE_REDUCTION_M_PER_KM * Math.max(0, w)) / 1000).toFixed(3);
export function protectionBand(w) {
  const r = waveReduction(w);
  if (r >= 0.4) return 'strong';
  if (r >= 0.2) return 'partial';
  return 'exposed';
}

function peopleByBand(segments, widthOf) {
  const out = { exposed: 0, partial: 0, strong: 0 };
  for (const s of segments) out[protectionBand(widthOf(s))] += s.surge_people || 0;
  return out;
}

// Local copy of /scenario so the app works even if the backend is asleep.
export function runScenarioLocal(segments, restoreIds) {
  const chosen = new Set(restoreIds);
  const widthAfter = (s) => s.existing_width_m + (chosen.has(s.id) ? s.restorable_width_m : 0);
  const restored = segments.filter((s) => chosen.has(s.id));
  const better = restored
    .filter((s) => BANDS.indexOf(protectionBand(widthAfter(s))) > BANDS.indexOf(protectionBand(s.existing_width_m)))
    .reduce((n, s) => n + (s.surge_people || 0), 0);
  return {
    restored: restored.map((s) => s.id),
    hectares: +restored.reduce((n, s) => n + (s.restorable_ha || 0), 0).toFixed(1),
    people_better_protected: better,
    before: peopleByBand(segments, (s) => s.existing_width_m),
    after: peopleByBand(segments, widthAfter),
    segments: segments.map((s) => ({
      id: s.id,
      width_m: widthAfter(s),
      wave_reduction: waveReduction(widthAfter(s)),
      surge_reduction_m: surgeReductionM(widthAfter(s)),
      band: protectionBand(widthAfter(s)),
      restored: chosen.has(s.id),
    })),
    local: true,
  };
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
  const empty = { type: 'FeatureCollection', features: [] };
  const [track, segments, mangroves, buildings, validation] = await Promise.all([
    getJson('/data/track.json', []),
    getJson('/data/coast_segments.geojson', empty),
    getJson('/data/mangroves.geojson', empty),
    getJson('/data/buildings.geojson', empty),
    getJson('/data/validation.json', null),
  ]);
  return { track, segments, mangroves, buildings, validation };
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

export async function runScenario(segments, restoreIds) {
  try {
    return await post('/scenario', {
      restore_ids: restoreIds,
      segments: segments.map(({ id, existing_width_m, restorable_width_m, restorable_ha, surge_people }) =>
        ({ id, existing_width_m, restorable_width_m, restorable_ha, surge_people })),
    });
  } catch {
    return runScenarioLocal(segments, restoreIds);
  }
}

export async function restorationPlan(areaName, summary) {
  return post('/restoration-plan', { area_name: areaName, summary });
}
