// App.jsx - Nadi flood planner
//
// Part A (already working): the flood map, slider, headline counts and ranked list.
// Part B (new): the Options panel with Compare and Combine tabs.
//
// Part B calls P3's POST /compare-measures (USE_PLACEHOLDER = false below). The placeholder
// model is kept only as a fallback for layout testing.

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { addExtraLayers, setExtraVisibility, EXTRA_DEFAULTS, MapLayersPanel } from "./extraLayers";

// Backend address. Put it in frontend/.env.local like:  VITE_API_URL=http://localhost:8000
const API_URL = import.meta.env.VITE_API_URL;

// =====================================================================
// CONNECTING TO P3 (everything you need to change is in this block)
// =====================================================================
const USE_PLACEHOLDER = false; // true = made-up numbers for layout testing only
const COMPARE_ROUTE = "/compare-measures";

// What "Low / Med / High" means for each option: the presets in backend/app/measures.json.
// "Med" is what the pitch and charts use (0.25 m clearing, 5% vegetation, 100 homes raised 1 m).
const PRESETS = {
  channel_clearing_m: { Low: 0.1, Med: 0.25, High: 0.5 }, // metres the river is lowered
  nature_based: {
    Low: { reduction_pct: 2 },
    Med: { reduction_pct: 5 },
    High: { reduction_pct: 10 },
  },
  raise_homes: {
    Low: { count: 50, height_m: 1.0 },
    Med: { count: 100, height_m: 1.0 },
    High: { count: 250, height_m: 1.0 },
  },
};

// The "Raise homes" target: a circle around the picked hotspot. Hotspots are usually 250 m grid
// squares with names like "Nawaka Village 2", which don't match any building's `area`, so we
// target by position instead of by name.
const TARGET_RADIUS_M = 200;
function targetFor(area) {
  return area ? { lon: area.lon, lat: area.lat, radius_m: TARGET_RADIUS_M } : undefined;
}
function metresBetween(a, b) {
  const dx = (a.lon - b.lon) * 111320 * Math.cos((b.lat * Math.PI) / 180);
  const dy = (a.lat - b.lat) * 110540;
  return Math.hypot(dx, dy);
}
// =====================================================================

// ---------- 1. SETTINGS ----------
const NADI_CENTER = [177.44, -17.79]; // [longitude, latitude]
const NADI_BOUNDS = [[177.38, -17.86], [177.52, -17.72]]; // same box as the data
const MAX_LEVEL = 6;
const STEP = 0.25;
const START_LEVEL = 2;
const DEBOUNCE_MS = 300;
const DEEP_WATER_M = 1.0;
const FLOOR_M = 0.3; // assumed floor height above ground (backend/places/nadi.json)
const ROAD_CUT_DEPTH_M = 0.3; // road cut once water is this deep (backend/app/measures.json)
const LEVELS = Array.from({ length: 13 }, (_, i) => i * 0.5); // 0, 0.5 ... 6

// Same colours as index.css (MapLibre needs them as plain values)
const COLORS = {
  dry: "#a3afa8",
  reaching: "#e3a43a",
  inside: "#cf4a2f",
  deep: "#7a1f1f",
  water: "#3b87b5",
  road: "#8c9a93",
  roadCut: "#cf4a2f",
  highlight: "#4e5da8",
  ink: "#16323f",
};

// The three options. `key` is the backend's name for each one.
const OPTIONS = [
  {
    key: "channel_clearing_m",
    name: "Dredge the river",
    color: "#a06a2c",
    presets: { low: 0.1, medium: 0.25, high: 0.5 }, // replaced by /measures when the backend is up
    describe: (v) => `Every flood ${v} m lower. The benefit fades as silt returns.`,
  },
  {
    key: "raise_homes",
    name: "Raise homes",
    color: "#4e5da8",
    presets: { low: 50, medium: 100, high: 250 },
    describe: (v, area) =>
      `Lift up to ${v} homes by 1 m, ${
        area ? (area.name.startsWith("near ") ? areaLabel(area) : `in ${area.name}`) : "anywhere in town (pick an area to target it)"
      }.`,
  },
  {
    key: "nature_based",
    name: "Riverbank vegetation",
    color: "#3f8a55",
    presets: { low: 2, medium: 5, high: 10 },
    describe: (v) => `Floods ${v}% lower, less in very big floods. Also cuts erosion and silt.`,
  },
];

// The three options. `key` is P3's name for each one.
const MEASURES = [
  { key: "channel_clearing_m", label: "Clear river channel", color: "#1b998b" },
  { key: "raise_homes", label: "Raise homes", color: "#f18f01" },
  { key: "nature_based", label: "Riverbank vegetation", color: "#6a4c93" },
];
// "All together" adds options in this order: town-wide first, then raise the homes still flooding.
const ORDER = ["channel_clearing_m", "nature_based", "raise_homes"];
const optionOf = (key) => OPTIONS.find((o) => o.key === key);

// ---------- 2. HELPERS ----------
const fmt = (n) => Math.round(n).toLocaleString();
const areaLabel = (a) => (a.name.startsWith("near ") ? `around ${a.name.slice(5)}` : a.name);
const titleCase = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function pointsToGeoJSON(rows) {
  return {
    type: "FeatureCollection",
    features: rows.map((r) => ({
      type: "Feature",
      properties: r,
      geometry: { type: "Point", coordinates: [r.lon, r.lat] },
    })),
  };
}

async function getJSON(path, signal) {
  const res = await fetch(`${API_URL}${path}`, { signal });
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

async function postJSON(path, body, signal) {
  if (!API_URL) throw new Error("VITE_API_URL is not set");
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

const idOf = (x) => (x !== null && typeof x === "object" ? x.id : x);

// Where "Raise homes" applies: a named village exactly, or a circle around an "around X" area.
function targetFor(area) {
  if (!area) return undefined;
  if (area.name_source === "place" && !area.name.startsWith("near ")) return { area: area.name };
  return { lon: area.lon, lat: area.lat, radius_m: NEAR_RADIUS_M };
}

function inTarget(b, target) {
  if (!target) return false;
  if (target.area) return b.area === target.area;
  const dx = (b.lon - target.lon) * 111320 * Math.cos((target.lat * Math.PI) / 180);
  const dy = (b.lat - target.lat) * 110540;
  return Math.hypot(dx, dy) <= target.radius_m;
}

function backendResult(flood, hot) {
  const base = flood.baseline;
  const homeStatus = new Map();
  for (const h of base.buildings) {
    const status = h.water_inside ? (h.depth_m >= DEEP_WATER_M ? 3 : 2) : h.depth_m > 0 ? 1 : 0;
    homeStatus.set(h.id, status);
  }
  const floodedFacilities = new Set(base.facilities_flooded.map(idOf));
  const cutRoads = new Set(base.roads_cut.map(idOf));
  return {
    homeStatus,
    floodedFacilities,
    cutRoads,
    counts: { people: base.people_water_inside, facilities: floodedFacilities.size, roads: cutRoads.size },
    hotspots: hot.areas,
    topShare: hot.top_areas_share_of_people,
  };
}

// Backup plan: work the map colours out in the browser when the backend is down.
function localResult(data, level) {
  const homeStatus = new Map();
  let people = 0;
  // Same rules as backend/app/flood.py, so numbers don't jump when the backend wakes up.
  for (const b of data.buildings) {
    const reached = level >= b.floods_at_m;
    const depth = reached ? level - b.ground_m : 0;
    const inside = reached && level > b.ground_m + FLOOR_M;
    let status = 0;
    if (reached && level > b.ground_m + DEFAULT_FLOOR_M) {
      status = depth >= DEEP_WATER_M ? 3 : 2;
      people += b.people;
    } else if (reached) {
      status = 1;
    }
    homeStatus.set(b.id, status);
  }
  const floodedFacilities = new Set(
    data.facilities.filter((f) => level >= f.floods_at_m && level > f.ground_m + FLOOR_M).map((f) => f.id)
  );
  const cutRoads = new Set(data.roads.filter((r) => level - r.low_point_m >= ROAD_CUT_DEPTH_M).map((r) => r.id));
  return {
    homeStatus,
    floodedFacilities,
    cutRoads,
    counts: { people, facilities: floodedFacilities.size, roads: cutRoads.size },
    hotspots: null,
    topShare: null,
  };
}

function applyResult(map, data, result) {
  map.getSource("homes").setData(
    pointsToGeoJSON(data.buildings.map((b) => ({ ...b, status: result.homeStatus.get(b.id) ?? 0 })))
  );
  map.getSource("facilities").setData(
    pointsToGeoJSON(data.facilities.map((f) => ({ ...f, flooded: result.floodedFacilities.has(f.id) })))
  );
  map.getSource("roads").setData({
    ...data.roadsGeo,
    features: data.roadsGeo.features.map((f) => ({
      ...f,
      properties: { ...f.properties, cut: result.cutRoads.has(f.properties.id) },
    })),
  });
}

// Ticked options + Low/Medium/High -> the backend's `options` object.
function buildOptions(choice, presets, area) {
  const out = {};
  for (const o of OPTIONS) {
    const c = choice[o.key];
    if (!c.on) continue;
    const v = presets[o.key][c.size];
    if (o.key === "channel_clearing_m") out[o.key] = v;
    if (o.key === "nature_based") out[o.key] = { reduction_pct: v };
    if (o.key === "raise_homes") {
      const t = targetFor(area);
      out[o.key] = { count: v, height_m: 1.0, ...(t ? { target: t } : {}) };
    }
  }
  return out;
}

// ---------- 3. THE RIVER GAUGE (the slider) ----------
function Gauge({ level, onChange }) {
  const ref = useRef(null);
  const H = 520; // SVG units; the element scales to its CSS height
  const W = 54;
  const pad = 14;
  const y = (m) => pad + (1 - m / MAX_LEVEL) * (H - 2 * pad);
  const snap = (m) => Math.min(MAX_LEVEL, Math.max(0, Math.round(m / STEP) * STEP));

  function fromPointer(e) {
    const r = ref.current.getBoundingClientRect();
    const frac = 1 - (e.clientY - r.top - (pad / H) * r.height) / (r.height * (1 - (2 * pad) / H));
    onChange(snap(frac * MAX_LEVEL));
  }
  function onKey(e) {
    const steps = { ArrowUp: STEP, ArrowRight: STEP, ArrowDown: -STEP, ArrowLeft: -STEP, PageUp: 1, PageDown: -1 };
    if (e.key in steps) onChange(snap(level + steps[e.key]));
    else if (e.key === "Home") onChange(0);
    else if (e.key === "End") onChange(MAX_LEVEL);
    else return;
    e.preventDefault();
  }

  // Staff gauge "E" marks: a bar on every other 10 cm, a longer bar at each half metre.
  const marks = [];
  for (let d = 0; d < MAX_LEVEL * 10; d += 2) {
    const long = d % 10 === 0 || d % 10 === 4;
    marks.push(<rect key={d} x={W / 2} y={y((d + 1) / 10)} width={long ? 20 : 13} height={(H - 2 * pad) / (MAX_LEVEL * 10)} fill={COLORS.ink} />);
  }
  const fracPct = (y(level) / H) * 100;

  return (
    <div
      ref={ref}
      className="gauge"
      role="slider"
      tabIndex={0}
      aria-label="River rise above normal level"
      aria-valuemin={0}
      aria-valuemax={MAX_LEVEL}
      aria-valuenow={level}
      aria-valuetext={`${level.toFixed(2)} metres above normal`}
      onKeyDown={onKey}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        fromPointer(e);
      }}
      onPointerMove={(e) => e.buttons === 1 && fromPointer(e)}
    >
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <rect className="gauge-post" x={6} y={pad - 6} width={W - 12} height={H - 2 * pad + 12} rx={4} fill="#ffffff" stroke={COLORS.ink} strokeWidth={1.5} />
        {marks}
        {Array.from({ length: MAX_LEVEL + 1 }, (_, m) => (
          <text key={m} x={18} y={y(m) + 5} textAnchor="middle" fontFamily="Barlow Condensed, sans-serif" fontWeight="700" fontSize="17" fill={m % 2 ? COLORS.inside : COLORS.ink}>
            {m}
          </text>
        ))}
        <rect x={6} y={y(level)} width={W - 12} height={Math.max(0, H - pad + 6 - y(level))} rx={4} fill={COLORS.water} fillOpacity={0.55} />
        <line x1={0} x2={W} y1={y(level)} y2={y(level)} stroke={COLORS.water} strokeWidth={3} />
      </svg>
      <div className="gauge-read" style={{ top: `${fracPct}%` }}>
        <span className="v">{level.toFixed(level % 1 ? 2 : 1)} m</span>
        <span className="l">river rise above normal</span>
      </div>
    </div>
  );
}

// ---------- 4. RESULT CHARTS ----------
function CompareBars({ result, level }) {
  const total = result.baseline.people_water_inside;
  const best = result.options[0];
  return (
    <div className="bars">
      <p className="verdict">
        On its own, <b>{optionOf(best.key).name.toLowerCase()}</b> keeps water out of the most homes at a {level} m
        flood: <b>{fmt(best.at_design_level.people_protected)}</b> of the {fmt(total)} people affected.
      </p>
      {result.options.map((o) => {
        const n = o.at_design_level.people_protected;
        return (
          <div key={o.key} className="bar-row">
            <span>{optionOf(o.key).name}</span>
            <div className="bar-track" role="img" aria-label={`${fmt(n)} people protected`}>
              <span style={{ width: `${Math.min(100, (n / total) * 100)}%`, background: optionOf(o.key).color }} />
            </div>
            <span className="bar-val">{fmt(n)}</span>
          </div>
        );
      })}
      {mitigation.options
        .filter((o) => o.key === "raise_homes" && o.at_design_level.people_protected === 0 && o.homes_too_deep_to_raise)
        .map((o) => (
          <p key="deep" style={styles.muted}>
            Raising homes helps nobody here at this level: water is too deep for the raise
            ({o.homes_too_deep_to_raise.toLocaleString()} homes too deep). Try a lower river rise or another area.
          </p>
        ))}
    </div>
  );
}

function CompareLines({ result, level }) {
  const W = 380, H = 190, pad = { l: 40, r: 18, t: 10, b: 32 };
  const base = result.baseline.curve ?? [];
  const series = result.options
    .filter((o) => o.curve && o.curve.length === base.length)
    .map((o) => ({
      key: o.key,
      label: optionOf(o.key).name,
      color: optionOf(o.key).color,
      // people protected at each river rise = do nothing minus with this option
      points: o.curve.map((p, i) => ({ lv: p.level_m, v: Math.max(0, base[i].people_water_inside - p.people_water_inside) })),
    }));
  if (!series.length) return null;

  const maxY = Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.v)));
  const stepY = maxY > 2000 ? 1000 : maxY > 800 ? 500 : maxY > 200 ? 100 : 50;
  const niceMax = Math.ceil(maxY / stepY) * stepY;
  const x = (lv) => pad.l + (lv / MAX_LEVEL) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - v / niceMax) * (H - pad.t - pad.b);

  return (
    <div className="lines">
      <p className="chart-title">People protected as the river rises</p>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="People protected by each option at each river rise">
        {[0, niceMax / 2, niceMax].map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="#d5ddd6" />
            <text x={pad.l - 6} y={y(t) + 4} fontSize="11" textAnchor="end">{fmt(t)}</text>
          </g>
        ))}
        {[0, 1, 2, 3, 4, 5, 6].map((lv) => (
          <text key={lv} x={x(lv)} y={H - 16} fontSize="11" textAnchor="middle">{lv} m</text>
        ))}
        <text x={(pad.l + W - pad.r) / 2} y={H - 2} fontSize="11" textAnchor="middle">River rise above normal</text>
        <line x1={x(level)} x2={x(level)} y1={pad.t} y2={y(0)} stroke={COLORS.water} strokeWidth="2" opacity="0.6" />
        {series.map((s) => (
          <polyline
            key={s.key}
            fill="none"
            stroke={s.color}
            strokeWidth={2.25}
            strokeLinejoin="round"
            points={s.points.map((p) => `${x(p.lv)},${y(p.v)}`).join(" ")}
          />
        ))}
      </svg>
      <div className="legend-row">
        {series.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <p className="hint">The blue line is the gauge level. Where a line falls back towards zero, that option has stopped helping.</p>
    </div>
  );
}

function Waterfall({ result }) {
  const base = result.baseline.people_water_inside;
  const lay = result.layering;
  if (!lay) return null;
  const steps = lay.steps;
  const total = steps[steps.length - 1].people_protected_so_far;
  const ranked = lay.orders_compared ?? [];
  const best = ranked[0];
  const worst = ranked[ranked.length - 1];
  const orderMatters = best && worst && best.people_protected !== worst.people_protected;

  return (
    <div className="bars">
      <p className="verdict">
        Together they keep water out of the homes of <b>{fmt(total)}</b> of {fmt(base)} people (
        {Math.round((total / base) * 100)}%).
      </p>
      <div className="wf-row">
        <span>Do nothing</span>
        <div className="bar-track"><span style={{ width: "100%", background: COLORS.inside }} /></div>
        <span className="wf-val"><b>{fmt(base)}</b></span>
      </div>
      {steps.map((s) => {
        const o = optionOf(s.added);
        return (
          <div key={s.step} className="wf-row">
            <span>+ {o.name}</span>
            <div className="bar-track" role="img" aria-label={`${fmt(s.people_added_protection)} more people protected`}>
              <span style={{ width: `${(s.people_still_water_inside / base) * 100}%`, background: COLORS.inside }} />
              <span style={{ width: `${(s.people_added_protection / base) * 100}%`, background: o.color }} />
            </div>
            <span className="wf-val">
              −{fmt(s.people_added_protection)} <b>{fmt(s.people_still_water_inside)}</b>
            </span>
          </div>
        );
      })}
      <div className="legend-row">
        <span><i style={{ background: COLORS.inside }} />Still water inside</span>
        <span>Colour: protected by that step</span>
        <span><i style={{ background: "#d5ddd6" }} />Protected by earlier steps</span>
      </div>
      {orderMatters ? (
        <p className="hint">
          Order matters: {best.order.map((k) => optionOf(k).name.toLowerCase()).join(", then ")} protects{" "}
          {fmt(best.people_protected)}, the worst order {fmt(worst.people_protected)}. Raise homes last so every lift goes
          to a home that is still flooding.
        </p>
      ) : (
        steps.length > 1 && <p className="hint">At this flood level, the order makes no difference.</p>
      )}
    </div>
  );
}

// ---------- 5. THE WRITTEN PLAN ----------
// A small Markdown reader for the plan: headings, bullet and numbered lists, **bold**, _italic_.
// It builds React elements (never raw HTML), so text from the AI can't inject anything.
function inline(text, keyBase) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|_[^_]+_)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const t = m[0];
    parts.push(t.startsWith("**") ? <b key={`${keyBase}-${i++}`}>{t.slice(2, -2)}</b> : <em key={`${keyBase}-${i++}`}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function Markdown({ text }) {
  const blocks = [];
  let list = null;
  const flush = () => {
    if (list) blocks.push(list);
    list = null;
  };
  text.split("\n").forEach((raw, n) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)/);
    if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        flush();
        list = { type, items: [], key: n };
      }
      list.items.push(inline((bullet || numbered)[1], n));
      return;
    }
    flush();
    if (!line.trim()) return;
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      const Tag = h[1].length === 1 ? "h3" : "h4";
      blocks.push({ type: Tag, content: inline(h[2], n), key: n });
    } else {
      blocks.push({ type: "p", content: inline(line, n), key: n });
    }
  });
  flush();
  return (
    <div className="plan-doc">
      {blocks.map((b) => {
        if (b.type === "ul" || b.type === "ol") {
          const List = b.type;
          return <List key={b.key}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</List>;
        }
        const Tag = b.type;
        return <Tag key={b.key}>{b.content}</Tag>;
      })}
    </div>
  );
}

// Per-building rows are huge and the plan doesn't need them.
function slimFlood(flood) {
  const strip = (x) => (x ? { ...x, buildings: undefined } : x);
  return { ...flood, baseline: strip(flood.baseline), with_measures: strip(flood.with_measures) };
}

// ---------- 6. THE PAGE ----------
export default function App() {
  const mapDiv = useRef(null);
  const mapRef = useRef(null);

  const [data, setData] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [level, setLevel] = useState(0);
  const [selectedArea, setSelectedArea] = useState(null); // picked hotspot {name, lon, lat}; also the Raise homes target
  const [backend, setBackend] = useState("checking");
  const [counts, setCounts] = useState(null);
  const [hotspots, setHotspots] = useState(null);
  const [topShare, setTopShare] = useState(null);
  const [extraOn, setExtraOn] = useState(EXTRA_DEFAULTS);
  const [extraAvailable, setExtraAvailable] = useState({});
  const [presets, setPresets] = useState(() => Object.fromEntries(OPTIONS.map((o) => [o.key, o.presets])));

  const [tab, setTab] = useState("compare");
  const [choice, setChoice] = useState({
    channel_clearing_m: { on: true, size: "medium" },
    raise_homes: { on: true, size: "medium" },
    nature_based: { on: true, size: "medium" },
  });
  const [result, setResult] = useState(null);
  const [resultState, setResultState] = useState("idle"); // idle | loading | ready | error

  const [plan, setPlan] = useState(null); // { markdown, provider, fallback, error, settingsKey }
  const [planState, setPlanState] = useState("idle"); // idle | loading | error
  const [copied, setCopied] = useState(false);

  const setOpt = (key, patch) => setChoice((c) => ({ ...c, [key]: { ...c[key], ...patch } }));

  // Check the backend once and read the option presets from /measures.
  useEffect(() => {
    if (!API_URL) {
      setBackend("not-set");
      return;
    }
    getJSON("/health")
      .then(() => {
        setBackend("online");
        return getJSON("/measures");
      })
      .then((m) => {
        if (!m) return;
        setPresets((p) => {
          const next = { ...p };
          for (const o of OPTIONS) if (m[o.key]?.presets) next[o.key] = m[o.key].presets;
          return next;
        });
      })
      .catch(() => setBackend("offline"));
  }, []);

  // Set up the map and load the data files once.
  useEffect(() => {
    let cancelled = false;
    const map = new maplibregl.Map({
      container: mapDiv.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [
          { id: "basemap", type: "raster", source: "osm", paint: { "raster-saturation": -0.6, "raster-opacity": 0.85 } },
        ],
      },
      center: NADI_CENTER,
      zoom: 12.3,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    mapRef.current = map;

    const mapLoaded = new Promise((resolve) => map.on("load", resolve));
    const file = (name) =>
      fetch(`/data/${name}`).then((r) => {
        if (!r.ok) throw new Error(`Could not load /data/${name}`);
        return r.json();
      });
    const optional = (name) => file(name).catch(() => null);

    Promise.all([
      mapLoaded,
      file("buildings.json"),
      file("facilities.json"),
      file("roads.json"),
      file("roads.geojson"),
      file("flood_extents.geojson"),
      optional("rivers.geojson"),
      optional("mangroves.geojson"),
      optional("restorable.geojson"),
      optional("coast_segments.geojson"),
    ])
      .then(([, buildings, facilities, roads, roadsGeo, floodExtents, rivers, mangroves, restorable, coast]) => {
        if (cancelled) return;

        // Top to bottom on screen: facilities, highlight, homes, roads, water, basemap.
        map.addSource("water", { type: "geojson", data: floodExtents });
        map.addLayer({
          id: "water",
          type: "fill",
          source: "water",
          filter: ["==", ["get", "level_m"], -1],
          paint: { "fill-color": COLORS.water, "fill-opacity": 0.42 },
        });

        map.addSource("roads", { type: "geojson", data: roadsGeo });
        map.addLayer({
          id: "roads",
          type: "line",
          source: "roads",
          paint: {
            "line-color": ["case", ["==", ["get", "cut"], true], COLORS.roadCut, COLORS.road],
            "line-width": ["interpolate", ["linear"], ["zoom"],
              11, ["case", ["==", ["get", "cut"], true], 1.6, 0.5],
              15, ["case", ["==", ["get", "cut"], true], 4, 2]],
            "line-opacity": ["case", ["==", ["get", "cut"], true], 0.95, 0.6],
          },
        });

        map.addSource("homes", { type: "geojson", data: pointsToGeoJSON(buildings) });
        map.addLayer({
          id: "homes",
          type: "circle",
          source: "homes",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 1.6, 14, 3, 17, 6],
            "circle-color": ["match", ["get", "status"], 3, COLORS.deep, 2, COLORS.inside, 1, COLORS.reaching, COLORS.dry],
            "circle-opacity": ["match", ["get", "status"], 0, 0.55, 1],
          },
        });
        map.addLayer({
          id: "highlight",
          type: "circle",
          source: "homes",
          filter: ["in", ["get", "id"], ["literal", []]],
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 3.5, 17, 10],
            "circle-color": "rgba(0,0,0,0)",
            "circle-stroke-color": COLORS.highlight,
            "circle-stroke-width": 1.5,
          },
        });

        map.addSource("facilities", { type: "geojson", data: pointsToGeoJSON(facilities) });
        map.addLayer({
          id: "facilities",
          type: "circle",
          source: "facilities",
          paint: {
            "circle-radius": 6,
            "circle-color": ["case", ["==", ["get", "flooded"], true], COLORS.inside, "#ffffff"],
            "circle-stroke-color": COLORS.ink,
            "circle-stroke-width": 2,
          },
        });
        map.on("click", "facilities", (e) => {
          const p = e.features[0].properties;
          new maplibregl.Popup({ closeButton: false })
            .setLngLat(e.lngLat)
            .setText(`${p.name || "Facility"} (${p.type || "facility"}): ${p.flooded === true || p.flooded === "true" ? "flooded" : "dry"}`)
            .addTo(map);
        });
        map.on("mouseenter", "facilities", () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", "facilities", () => (map.getCanvas().style.cursor = ""));

        setExtraAvailable(addExtraLayers(map, { rivers, mangroves, restorable, coast }));
        // Frame the town, leaving room on the left for the gauge.
        const narrow = mapDiv.current.clientWidth < 600;
        map.fitBounds(NADI_BOUNDS, { padding: { left: narrow ? 90 : 230, right: narrow ? 16 : 40, top: 30, bottom: 30 }, duration: 0 });
        setData({ buildings, facilities, roads, roadsGeo });
        setReady(true);
      })
      .catch((err) => !cancelled && setError(err.message));

    return () => {
      cancelled = true;
      map.remove();
    };
  }, []);

  // Gauge moves -> the water layer follows straight away (outlines exist every 0.5 m).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    // Outlines exist every 0.5 m; show the highest one at or below the slider (0.25 -> 0, 1.75 -> 1.5).
    map.setFilter("water", ["==", ["get", "level_m"], Math.floor(level * 2) / 2]);
  }, [level, ready]);

  // Gauge rests for 300 ms -> ask the backend for the flood picture (or work it out locally).
  useEffect(() => {
    if (!ready || !data) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      let res = null;
      if (API_URL) {
        try {
          const body = { level_m: level, buildings: data.buildings, facilities: data.facilities };
          const [flood, hot] = await Promise.all([
            postJSON("/flood", { ...body, roads: data.roads }, controller.signal),
            postJSON("/hotspots", { ...body, top: 8, group_by: "place" }, controller.signal),
          ]);
          res = backendResult(flood, hot);
          setBackend("online");
        } catch (err) {
          if (err.name === "AbortError") return;
          console.warn("Backend problem, using local colours:", err);
          setBackend("offline");
        }
      }
      if (!res) res = localResult(data, level);
      if (controller.signal.aborted) return;
      applyResult(mapRef.current, data, res);
      setCounts(res.counts);
      setHotspots(res.hotspots);
      setTopShare(res.topShare);
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [level, ready, data]);

  // Level, options, tab or area change -> refresh the results (backend /compare-measures).
  useEffect(() => {
    if (!ready || !data || backend !== "online") return;
    const opts = buildOptions(choice, presets, area);
    const order = ORDER.filter((k) => opts[k]);
    if (!order.length) {
      setResult(null);
      setResultState("idle");
      return;
    }
    const controller = new AbortController();
    setResultState("loading");
    const timer = setTimeout(async () => {
      try {
        const t = targetFor(area);
        const together = tab === "combine";
        const res = await postJSON(
          "/compare-measures",
          {
            level_m: level,
            options: opts,
            buildings: data.buildings,
            facilities: data.facilities,
            roads: data.roads,
            ...(t ? { target: t } : {}),
            ...(together
              ? { order, min_m: level, max_m: level, step_m: 1 } // no curves needed
              : { min_m: 0, max_m: MAX_LEVEL, step_m: 0.5 }),
          },
          controller.signal
        );
        if (controller.signal.aborted) return;
        setResult({ ...res, tab });
        setResultState("ready");
      } catch (err) {
        if (err.name === "AbortError") return;
        console.warn("Compare problem:", err);
        setResultState("error");
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [level, options, tab, selectedArea, ready, data]);

  // Area picked in the list -> ring the homes inside the target circle on the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !data) return;
    const ids = selectedArea
      ? data.buildings.filter((b) => metresBetween(b, selectedArea) <= TARGET_RADIUS_M).map((b) => b.id)
      : [];
    map.setFilter("highlight", ["in", ["get", "id"], ["literal", ids]]);
  }, [selectedArea, ready, data]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setExtraVisibility(map, extraOn);
  }, [extraOn, extraAvailable, ready]);

  function pickArea(area) {
    setSelectedArea({ name: area.name, lon: area.lon, lat: area.lat });
    mapRef.current.flyTo({ center: [area.lon, area.lat], zoom: 15, pitch: 30 });
  }

  function downloadPlan() {
    const blob = new Blob([plan.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nadi-flood-plan-${level}m.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function pickArea(a) {
    if (area && area.name === a.name) {
      setArea(null);
      return;
    }
    setArea(a);
    if (a.lon != null) mapRef.current.flyTo({ center: [a.lon, a.lat], zoom: 14.5, duration: 900 });
  }

  const anyOn = OPTIONS.some((o) => choice[o.key].on);
  const levelText = `${level.toFixed(level % 1 ? 2 : 1)} m`;
  const maxPeople = hotspots?.length ? hotspots[0].people_water_inside : 1;
  const showResult = result && result.tab === tab && resultState !== "error";

  return (
    <div className="page">
      <div className="map-wrap">
        <div ref={mapDiv} className="map" />
        <Gauge level={level} onChange={setLevel} />
        <details className="key" open={typeof window === "undefined" || window.innerWidth > 860}>
          <summary>Key</summary>
          <div className="key-item"><i style={{ background: COLORS.inside }} />Water inside home</div>
          <div className="key-item"><i style={{ background: COLORS.deep }} />Deep water (1 m or more)</div>
          <div className="key-item"><i style={{ background: COLORS.reaching }} />Water at the door, not inside</div>
          <div className="key-item"><i style={{ background: COLORS.dry }} />Dry home</div>
          <div className="key-item"><i className="sq" style={{ background: COLORS.water }} />Flood water</div>
          <div className="key-item"><i className="ln" style={{ background: COLORS.roadCut }} />Road cut (30 cm of water)</div>
          <div className="key-item"><i style={{ background: "#fff", border: `2px solid ${COLORS.ink}` }} />Clinic, school or other facility</div>
        </details>
      </div>

      <aside className="panel">
        <header className="brand">
          <h1>Nadi flood planner</h1>
          <p>Raise the river on the gauge to see whose homes it reaches, then test three ways to keep the water out.</p>
        </header>

        {error && <p className="notice error">{error}</p>}
        {backend === "offline" && (
          <p className="notice">The backend is not running, so the map is worked out in the browser and the areas and results are hidden. Start it with uvicorn and reload.</p>
        )}
        {backend === "not-set" && (
          <p className="notice">No backend address set. Add VITE_API_URL to frontend/.env.local and restart npm run dev.</p>
        )}

        {/* 1. Where water gets inside */}
        <section className="step" aria-labelledby="s1">
          <div className="step-head"><span className="step-n">1</span><h2 id="s1">Where water gets inside</h2></div>
          {counts && (
            <p className="lede" aria-live="polite">
              {counts.people > 0 ? (
                <>
                  At {levelText}, water gets inside the homes of <span className="num inside">{fmt(counts.people)}</span> people,
                  floods <span className="num">{fmt(counts.facilities)}</span>{" "}
                  {counts.facilities === 1 ? "facility" : "facilities"} and cuts{" "}
                  <span className="num">{fmt(counts.roads)}</span> road sections.
                </>
              ) : (
                <>At {levelText}, no homes have water inside. Drag the gauge on the map to raise the river.</>
              )}
            </p>
          )}
          {hotspots && hotspots.length > 0 && (
            <>
              <p className="muted">
                Most affected areas
                {topShare != null && topShare < 0.995 ? `, with ${Math.round(topShare * 100)}% of those people` : ""}. Pick
                one to target raised homes there.
              </p>
              <ul className="areas">
                {hotspots.map((a) => {
                  const deepShare = a.people_water_inside ? Math.min(1, a.people_deep_water / a.people_water_inside) : 0;
                  const width = (a.people_water_inside / maxPeople) * 100;
                  return (
                    <li key={a.name}>
                      <button className="area" aria-pressed={area?.name === a.name} onClick={() => pickArea(a)}>
                        <span className="area-name">{titleCase(areaLabel(a))}</span>
                        <span className="area-count">{fmt(a.people_water_inside)}</span>
                        <span className="area-bar" aria-hidden="true">
                          <span style={{ width: `${width}%`, display: "flex" }}>
                            <span className="deep" style={{ width: `${deepShare * 100}%` }} />
                          </span>
                        </span>
                        <span className="area-meta">
                          {fmt(a.people_deep_water)} in deep water
                          {a.facilities_flooded?.length ? ` · ${a.facilities_flooded.join(", ")} flooded` : ""}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </section>

        {/* 2. Test options */}
        <section className="step" aria-labelledby="s2">
          <div className="step-head"><span className="step-n">2</span><h2 id="s2">Test options</h2></div>
          {OPTIONS.map((o) => {
            const c = choice[o.key];
            return (
              <div key={o.key} className={`option${c.on ? "" : " off"}`}>
                <div className="option-top">
                  <label className="switch">
                    <input type="checkbox" checked={c.on} onChange={(e) => setOpt(o.key, { on: e.target.checked })} aria-label={`Use ${o.name}`} />
                    <span />
                  </label>
                  <span className="option-name">
                    <span className="swatch" style={{ background: o.color }} />
                    {o.name}
                  </span>
                  <div className="seg" role="group" aria-label={`${o.name} size`}>
                    {SIZES.map(([k, label]) => (
                      <button key={k} disabled={!c.on} aria-pressed={c.size === k} onClick={() => setOpt(o.key, { size: k })}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="option-desc">{o.describe(presets[o.key][c.size], o.key === "raise_homes" ? area : null)}</p>
              </div>
            );
          })}
        </section>

        {/* 3. Results */}
        <section className="step" aria-labelledby="s3">
          <div className="step-head">
            <span className="step-n">3</span>
            <h2 id="s3">Results</h2>
            <span className="spacer" />
            <div className="seg" role="group" aria-label="How to compare">
              <button aria-pressed={tab === "compare"} onClick={() => setTab("compare")}>One at a time</button>
              <button aria-pressed={tab === "combine"} onClick={() => setTab("combine")}>All together</button>
            </div>
            {hotspots.map((a) => (
              <button
                key={a.name}
                onClick={() => pickArea(a)}
                style={{
                  ...styles.row, ...styles.rowButton,
                  background: selectedArea?.name === a.name ? "#efe3fb" : "transparent",
                }}
              >
                <span>{a.rank}</span>
                <span style={{ textAlign: "left" }}>{a.name}</span>
                <span>{a.people_water_inside.toLocaleString()}</span>
                <span>{a.people_deep_water.toLocaleString()}</span>
                <span>{(a.facilities_flooded ?? []).length}</span>
              </button>
            ))}
          </div>
        )}

        {/* 2. Options */}
        <div style={styles.optionsHeader}>
          <h3 style={{ ...styles.h3, margin: 0 }}>Options</h3>
          <div>
            <button
              onClick={() => setTab("compare")}
              style={{ ...styles.tab, ...(tab === "compare" ? styles.tabOn : {}) }}
            >Compare</button>
            <button
              onClick={() => setTab("combine")}
              style={{ ...styles.tab, ...(tab === "combine" ? styles.tabOn : {}) }}
            >Combine</button>
          </div>
        </div>

        {MEASURES.map((m) => (
          <div key={m.key} style={styles.optionRow}>
            <label style={{ flex: 1, fontSize: 14 }}>
              <input
                type="checkbox"
                checked={options[m.key].on}
                onChange={(e) => setOpt(m.key, { on: e.target.checked })}
              />{" "}
              <Dot color={m.color} />
              {m.key === "raise_homes"
                ? `Raise homes${selectedArea ? ` near ${selectedArea.name}` : " (town-wide; pick an area above to target)"}`
                : m.label}
            </label>
            <select
              value={options[m.key].size}
              disabled={!options[m.key].on}
              onChange={(e) => setOpt(m.key, { size: e.target.value })}
              aria-label={`${m.label} size`}
            >
              {SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        ))}

        {/* OPTIONAL, LATER: the "Find best mix" button goes here, in the Combine tab.
        {tab === "combine" && <button onClick={findBestMix}>Find best mix</button>}
        */}

        <p className="footer">
          A planning screen, not a flood forecast: it shows which ground the river reaches as it rises (height above
          nearest drainage), not how water flows. Option effects are what-ifs. Data: FABDEM, OpenStreetMap, Overture
          Maps, WorldPop.
        </p>
      </aside>
    </div>
  );
}
