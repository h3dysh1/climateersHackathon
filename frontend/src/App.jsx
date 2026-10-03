// App.jsx - Nadi flood planner (P1 frontend)
//
// Part A (already working): the flood map, slider, headline counts and ranked list.
// Part B (new): the Options panel with Compare and Combine tabs.
//
// Part B uses PLACEHOLDER numbers for now (USE_PLACEHOLDER = true below).
// The placeholder data copies the shape of P3's compare_options() answer, so when the real
// backend is ready you should only need to change the "CONNECTING TO P3" block.

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// Address of P3's backend. Put it in frontend/.env like:  VITE_API_URL=http://localhost:8000
const API_URL = import.meta.env.VITE_API_URL;

// =====================================================================
// CONNECTING TO P3 (everything you need to change is in this block)
// =====================================================================
const USE_PLACEHOLDER = true; // set to false once P3's compare route works
const COMPARE_ROUTE = "/compare"; // TODO: ask P3 for the real route

// What "Low / Med / High" means for each option. These numbers are GUESSES.
// TODO: ask P3 for the real values (they may live in measures.json).
// The names on the left (channel_clearing_m etc.) are P3's names.
const PRESETS = {
  channel_clearing_m: { Low: 0.25, Med: 0.5, High: 1.0 }, // metres the river is lowered
  nature_based: {
    Low: { reduction_pct: 5 },
    Med: { reduction_pct: 10 },
    High: { reduction_pct: 20 },
  },
  raise_homes: {
    Low: { count: 50, height_m: 0.5 },
    Med: { count: 100, height_m: 1.0 },
    High: { count: 200, height_m: 1.5 },
  },
};

// How the "Raise homes" target (e.g. Nawaka) is sent.
// TODO: ask P3 what shape `target` should have. This is a guess.
function targetFor(areaName) {
  return areaName ? { area: areaName } : undefined;
}
// =====================================================================

// ---------- 1. SETTINGS ----------
const NADI_CENTER = [177.42, -17.8]; // [longitude, latitude]
const DEBOUNCE_MS = 300;
const DEEP_WATER_M = 1.0;
const LEVELS = Array.from({ length: 13 }, (_, i) => i * 0.5); // 0, 0.5 ... 6

// Keep these colours the same everywhere (map, legend, list)
const COLORS = {
  dry: "#8d99ae",
  reaching: "#f9a03f",
  inside: "#d62828",
  deep: "#7f0000",
  water: "#2b8cbe",
  road: "#444444",
  roadCut: "#d62828",
  highlight: "#7b2cbf",
  protected: "#2a9d8f",
};

const STATUS_LABELS = [
  ["dry", "Dry home"],
  ["reaching", "Water reaching, not inside"],
  ["inside", "Water inside"],
  ["deep", "Deep water (1 m or more)"],
];

// The three options. `key` is P3's name for each one.
const MEASURES = [
  { key: "channel_clearing_m", label: "Dredging volume", color: "#1b998b" },
  { key: "raise_homes", label: "Raise homes", color: "#f18f01" },
  { key: "nature_based", label: "Wetlands & vegetation", color: "#6a4c93" },
];
const SIZES = ["Low", "Med", "High"];
// Combine tab order: lower the river first, then raise homes, then vegetation
const ORDER = ["channel_clearing_m", "raise_homes", "nature_based"];
const labelOf = (key) => MEASURES.find((m) => m.key === key)?.label ?? key;
const colorOf = (key) => MEASURES.find((m) => m.key === key)?.color ?? "#999";

// ---------- 2. HELPERS: flood map ----------
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

const idOf = (x) => (x !== null && typeof x === "object" ? x.id : x);

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

// Backup plan: work everything out in the browser (used when the backend is down).
function localResult(data, level) {
  const homeStatus = new Map();
  let people = 0;
  for (const b of data.buildings) {
    const depth = level - b.ground_m;
    const inside = level >= b.floods_at_m && level > b.ground_m + 0.3;
    let status = 0;
    if (inside) {
      status = depth >= DEEP_WATER_M ? 3 : 2;
      people += b.people;
    } else if (depth > 0) {
      status = 1;
    }
    homeStatus.set(b.id, status);
  }
  const floodedFacilities = new Set(
    data.facilities.filter((f) => level >= f.floods_at_m).map((f) => f.id)
  );
  const cutRoads = new Set(data.roads.filter((r) => r.low_point_m <= level).map((r) => r.id));
  return {
    homeStatus,
    floodedFacilities,
    cutRoads,
    counts: { people, facilities: floodedFacilities.size, roads: cutRoads.size },
    hotspots: null,
    topShare: null,
  };
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
    counts: {
      people: base.people_water_inside,
      facilities: floodedFacilities.size,
      roads: cutRoads.size,
    },
    hotspots: hot.areas,
    topShare: hot.top_areas_share_of_people,
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

// ---------- 3. HELPERS: options panel ----------
// Turn the ticked boxes + Low/Med/High choices into P3's `options` object.
function buildOptions(optionState, targetArea) {
  const out = {};
  for (const m of MEASURES) {
    const o = optionState[m.key];
    if (!o.on) continue;
    let cfg = PRESETS[m.key][o.size];
    if (m.key === "raise_homes") cfg = { ...cfg, target: targetFor(targetArea) };
    out[m.key] = cfg;
  }
  return out;
}

// ----- PLACEHOLDER MODEL (made-up numbers; delete when P3's route is connected) -----
const mockBaseline = (lv) => Math.round(2100 * Math.pow(lv / 3, 1.4));

// People still with water inside after applying `steps` in order. steps = [[key, setting], ...]
function mockAfter(level, steps) {
  let lvl = level;
  let wet = 0;
  let raised = 0;
  let townWide = false;
  let town = mockBaseline(level);
  for (const [key, cfg] of steps) {
    if (key === "channel_clearing_m") {
      lvl = Math.max(0, level - cfg);
      townWide = true;
    } else if (key === "nature_based") {
      wet = cfg.reduction_pct;
      townWide = true;
    } else if (key === "raise_homes") {
      // Raising first wastes some lifts on homes the other options would have kept dry.
      raised = Math.min(town * 0.5, cfg.count * 3.5 * cfg.height_m * (townWide ? 1 : 0.65));
    }
    town = mockBaseline(lvl) * (1 - (wet / 100) * Math.max(0, 1 - lvl / 8));
  }
  return Math.round(Math.max(0, town - raised));
}

function permutations(arr) {
  if (arr.length <= 1) return [arr];
  return arr.flatMap((x, i) =>
    permutations([...arr.slice(0, i), ...arr.slice(i + 1)]).map((p) => [x, ...p])
  );
}

// Same shape as P3's compare_options() answer.
function mockCompare(level, options, order) {
  const base = mockBaseline(level);
  const curve = (steps) =>
    LEVELS.map((lv) => ({ level_m: lv, people_water_inside: mockAfter(lv, steps) }));

  const singles = Object.keys(options)
    .map((key) => {
      const steps = [[key, options[key]]];
      const after = mockAfter(level, steps);
      return {
        key,
        at_design_level: {
          people_protected: Math.max(0, base - after),
          people_still_water_inside: after,
        },
        curve: curve(steps),
      };
    })
    .sort((a, b) => b.at_design_level.people_protected - a.at_design_level.people_protected)
    .map((o, i) => ({ ...o, rank: i + 1 }));

  const stepsFor = (ord) =>
    ord.map((key, i) => {
      const so = ord.slice(0, i + 1).map((k) => [k, options[k]]);
      const before = i === 0 ? base : mockAfter(level, so.slice(0, -1));
      const after = mockAfter(level, so);
      return {
        step: i + 1,
        added: key,
        people_added_protection: Math.max(0, before - after),
        people_protected_so_far: Math.max(0, base - after),
        people_still_water_inside: after,
      };
    });

  let layering = null;
  if (order && order.length) {
    layering = {
      order,
      steps: stepsFor(order),
      orders_compared: permutations(order)
        .map((p) => {
          const s = stepsFor(p);
          return { order: p, people_protected: s[s.length - 1].people_protected_so_far };
        })
        .sort((a, b) => b.people_protected - a.people_protected),
      note: "Placeholder numbers. Order only changes which homes get raised.",
    };
  }

  return {
    level_m: level,
    baseline: { people_water_inside: base, curve: curve([]) },
    options: singles,
    layering,
  };
}
// ----- end of placeholder model -----

// ---------- 4. CHARTS ----------
function CompareBars({ mitigation, level }) {
  const total = mitigation.baseline.people_water_inside;
  if (!total) {
    return <p style={styles.muted}>Nobody has water inside at this river level, so there is nothing to protect. Raise the slider.</p>;
  }
  return (
    <div>
      <p style={styles.chartTitle}>
        People protected at a {level.toFixed(1)} m flood (out of {total.toLocaleString()} with water inside)
      </p>
      {mitigation.options.map((o) => {
        const n = o.at_design_level.people_protected;
        return (
          <div key={o.key} style={styles.barRow}>
            <span style={styles.barLabel}>{labelOf(o.key)}</span>
            <div style={styles.barTrack}>
              <div style={{ ...styles.barFill, width: `${Math.min(100, (n / total) * 100)}%`, background: colorOf(o.key) }} />
            </div>
            <span style={styles.barValue}>{n.toLocaleString()}</span>
          </div>
        );
      })}
    </div>
  );
}

function CompareLines({ mitigation, level }) {
  const W = 380, H = 210, pad = { l: 46, r: 10, t: 10, b: 30 };
  const series = [
    { key: "base", label: "Do nothing", color: "#333333", curve: mitigation.baseline.curve },
    ...mitigation.options.map((o) => ({ key: o.key, label: labelOf(o.key), color: colorOf(o.key), curve: o.curve })),
  ].filter((s) => s.curve && s.curve.length);

  if (series.length === 0) {
    return <p style={styles.muted}>No curve data yet. The backend needs a list of river levels in the request.</p>;
  }

  const maxY = Math.max(1, ...series.flatMap((s) => s.curve.map((p) => p.people_water_inside)));
  const x = (lv) => pad.l + (lv / 6) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - v / maxY) * (H - pad.t - pad.b);

  return (
    <div>
      <p style={styles.chartTitle}>People with water inside, at each river rise</p>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%" }} role="img" aria-label="Line chart of people with water inside against river rise">
        <line x1={pad.l} y1={y(0)} x2={W - pad.r} y2={y(0)} stroke="#999" />
        <line x1={pad.l} y1={pad.t} x2={pad.l} y2={y(0)} stroke="#999" />
        <text x={pad.l - 6} y={y(0) + 4} fontSize="10" textAnchor="end">0</text>
        <text x={pad.l - 6} y={pad.t + 8} fontSize="10" textAnchor="end">{maxY.toLocaleString()}</text>
        {[0, 1, 2, 3, 4, 5, 6].map((lv) => (
          <text key={lv} x={x(lv)} y={H - 14} fontSize="10" textAnchor="middle">{lv}</text>
        ))}
        <text x={(pad.l + W - pad.r) / 2} y={H - 2} fontSize="10" textAnchor="middle">River rise above normal (m)</text>
        <line x1={x(level)} y1={pad.t} x2={x(level)} y2={y(0)} stroke="#999" strokeDasharray="4 3" />
        {series.map((s) => (
          <polyline
            key={s.key}
            fill="none"
            stroke={s.color}
            strokeWidth={s.key === "base" ? 2.5 : 2}
            points={s.curve.map((p) => `${x(p.level_m)},${y(p.people_water_inside)}`).join(" ")}
          />
        ))}
      </svg>
      <div style={styles.legend}>
        {series.map((s) => (
          <span key={s.key} style={{ marginRight: 12, whiteSpace: "nowrap" }}>
            <Dot color={s.color} /> {s.label}
          </span>
        ))}
      </div>
      <p style={styles.muted}>The dotted line is the river rise on the slider. Where a line meets the dark "Do nothing" line, that option has stopped helping.</p>
    </div>
  );
}

function Waterfall({ mitigation }) {
  const base = mitigation.baseline.people_water_inside;
  const layering = mitigation.layering;
  if (!layering) return <p style={styles.muted}>Loading combined results...</p>;
  if (!base) {
    return <p style={styles.muted}>Nobody has water inside at this river level, so there is nothing to protect. Raise the slider.</p>;
  }
  const steps = layering.steps;
  const totalProtected = steps[steps.length - 1].people_protected_so_far;
  const best = layering.orders_compared?.[0]?.order;

  return (
    <div>
      <p style={styles.chartTitle}>
        Together these protect {totalProtected.toLocaleString()} people ({Math.round((totalProtected / base) * 100)}%)
      </p>
      <div style={styles.wfRow}>
        <span style={styles.wfLabel}>Do nothing</span>
        <div style={styles.barTrack}><div style={{ ...styles.barFill, width: "100%", background: COLORS.inside }} /></div>
        <span style={styles.wfValue}>{base.toLocaleString()}</span>
      </div>
      {steps.map((s) => {
        const still = (s.people_still_water_inside / base) * 100;
        const added = (s.people_added_protection / base) * 100;
        return (
          <div key={s.step} style={styles.wfRow}>
            <span style={styles.wfLabel}>+ {labelOf(s.added)}</span>
            <div style={styles.barTrack}>
              <div style={{ display: "flex", height: "100%" }}>
                <div style={{ width: `${still}%`, background: COLORS.inside }} />
                <div style={{ width: `${added}%`, background: COLORS.protected }} />
              </div>
            </div>
            <span style={styles.wfValue}>
              -{s.people_added_protection.toLocaleString()} → {s.people_still_water_inside.toLocaleString()}
            </span>
          </div>
        );
      })}
      <div style={styles.legend}>
        <span style={{ marginRight: 12 }}><Dot color={COLORS.inside} /> Still water inside</span>
        <span><Dot color={COLORS.protected} /> Protected by this step</span>
      </div>
      {best && best.length > 1 && (
        <p style={styles.muted}>Best order: {best.map(labelOf).join(" → ")}</p>
      )}
      {layering.note && <p style={styles.muted}>{layering.note}</p>}
    </div>
  );
}

// ---------- 5. THE PAGE ----------
export default function App() {
  const mapDiv = useRef(null);
  const mapRef = useRef(null);

  const [data, setData] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [level, setLevel] = useState(0);
  const [selectedArea, setSelectedArea] = useState(null); // also the "target" for Raise homes
  const [backend, setBackend] = useState("checking");
  const [counts, setCounts] = useState(null);
  const [hotspots, setHotspots] = useState(null);
  const [topShare, setTopShare] = useState(null);

  // Options panel
  const [tab, setTab] = useState("compare");
  const [options, setOptions] = useState({
    channel_clearing_m: { on: true, size: "Med" },
    raise_homes: { on: true, size: "Med" },
    nature_based: { on: true, size: "Med" },
  });
  const [mitigation, setMitigation] = useState(null);
  const [mitigationError, setMitigationError] = useState("");

  function setOpt(key, patch) {
    setOptions((o) => ({ ...o, [key]: { ...o[key], ...patch } }));
  }

  // Check the backend once at the start (GET /health).
  useEffect(() => {
    if (!API_URL) {
      setBackend("not-set");
      return;
    }
    fetch(`${API_URL}/health`)
      .then((r) => setBackend(r.ok ? "online" : "offline"))
      .catch(() => setBackend("offline"));
  }, []);

  // Set up the map and load the data files once, at the start.
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
        layers: [{ id: "basemap", type: "raster", source: "osm" }],
      },
      center: NADI_CENTER,
      zoom: 12,
      pitch: 30,
    });
    mapRef.current = map;

    const mapLoaded = new Promise((resolve) => map.on("load", resolve));
    const getJSON = (name) =>
      fetch(`/data/${name}`).then((r) => {
        if (!r.ok) throw new Error(`Could not load /data/${name}`);
        return r.json();
      });

    Promise.all([
      mapLoaded,
      getJSON("buildings.json"),
      getJSON("facilities.json"),
      getJSON("roads.json"),
      getJSON("roads.geojson"),
      getJSON("flood_extents.geojson"),
    ])
      .then(([, buildings, facilities, roads, roadsGeo, floodExtents]) => {
        if (cancelled) return;

        // Top to bottom on screen: facilities, homes, roads, water, basemap.
        map.addSource("water", { type: "geojson", data: floodExtents });
        map.addLayer({
          id: "water",
          type: "fill",
          source: "water",
          filter: ["==", ["get", "level_m"], 0],
          paint: { "fill-color": COLORS.water, "fill-opacity": 0.5 },
        });

        map.addSource("roads", { type: "geojson", data: roadsGeo });
        map.addLayer({
          id: "roads",
          type: "line",
          source: "roads",
          paint: {
            "line-color": ["case", ["==", ["get", "cut"], true], COLORS.roadCut, COLORS.road],
            "line-width": 3,
          },
        });

        map.addSource("homes", { type: "geojson", data: pointsToGeoJSON(buildings) });
        map.addLayer({
          id: "homes",
          type: "circle",
          source: "homes",
          paint: {
            "circle-radius": 3,
            "circle-color": [
              "match", ["get", "status"],
              3, COLORS.deep,
              2, COLORS.inside,
              1, COLORS.reaching,
              COLORS.dry,
            ],
          },
        });
        map.addLayer({
          id: "highlight",
          type: "circle",
          source: "homes",
          filter: ["==", ["get", "area"], "__none__"],
          paint: {
            "circle-radius": 7,
            "circle-color": COLORS.highlight,
            "circle-opacity": 0.25,
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
            "circle-radius": 7,
            "circle-color": ["case", ["==", ["get", "flooded"], true], COLORS.inside, COLORS.dry],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
          },
        });

        setData({ buildings, facilities, roads, roadsGeo });
        setReady(true);
      })
      .catch((err) => !cancelled && setError(err.message));

    return () => {
      cancelled = true;
      map.remove();
    };
  }, []);

  // Slider moves -> the water layer changes straight away.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("water", ["==", ["get", "level_m"], level]);
  }, [level, ready]);

  // Slider stops for 300 ms -> ask the backend for the flood picture (or use the backup plan).
  useEffect(() => {
    if (!ready || !data) return;
    const controller = new AbortController();

    const timer = setTimeout(async () => {
      let result = null;

      if (API_URL) {
        try {
          const [flood, hot] = await Promise.all([
            postJSON(
              "/flood",
              { level_m: level, buildings: data.buildings, facilities: data.facilities, roads: data.roads },
              controller.signal
            ),
            postJSON(
              "/hotspots",
              { level_m: level, buildings: data.buildings, facilities: data.facilities, top: 10 },
              controller.signal
            ),
          ]);
          result = backendResult(flood, hot);
          setBackend("online");
        } catch (err) {
          if (err.name === "AbortError") return;
          console.warn("Backend problem, using local colours:", err);
          setBackend("offline");
        }
      }

      if (!result) result = localResult(data, level);
      if (controller.signal.aborted) return;

      applyResult(mapRef.current, data, result);
      setCounts(result.counts);
      setHotspots(result.hotspots);
      setTopShare(result.topShare);
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [level, ready, data]);

  // Slider, options, tab or target change -> refresh the Compare / Combine results.
  useEffect(() => {
    if (!ready || !data) return;
    const opts = buildOptions(options, selectedArea);
    const order = ORDER.filter((k) => opts[k]);
    if (order.length === 0) {
      setMitigation(null);
      return;
    }
    const controller = new AbortController();

    const timer = setTimeout(async () => {
      try {
        let result;
        if (USE_PLACEHOLDER) {
          result = mockCompare(level, opts, order);
        } else {
          // Real call. TODO: check these field names with P3.
          // `levels` is only sent for the Compare tab and `order` only for the Combine tab,
          // because the backend recalculates every level for every option.
          result = await postJSON(
            COMPARE_ROUTE,
            {
              level_m: level,
              options: opts,
              buildings: data.buildings,
              facilities: data.facilities,
              roads: data.roads,
              levels: tab === "compare" ? LEVELS : [],
              target: targetFor(selectedArea) ?? null,
              order: tab === "combine" ? order : null,
            },
            controller.signal
          );
        }
        if (controller.signal.aborted) return;
        setMitigation(result);
        setMitigationError("");
      } catch (err) {
        if (err.name === "AbortError") return;
        console.warn("Compare problem:", err);
        setMitigation(null);
        setMitigationError("Could not load results from the backend.");
      }
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [level, options, tab, selectedArea, ready, data]);

  // Area picked in the list -> ring its homes on the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("highlight", ["==", ["get", "area"], selectedArea ?? "__none__"]);
  }, [selectedArea, ready]);

  function pickArea(area) {
    setSelectedArea(area.name);
    mapRef.current.flyTo({ center: [area.lon, area.lat], zoom: 15, pitch: 30 });
  }

  // OPTIONAL, LATER: "Find best mix" (tries all 64 presets within an effort budget,
  // then switches the boxes to the winner). Left switched off for now.
  // function findBestMix() {
  //   // Ask the backend's optimiser for the best settings, then call setOptions(...) with them.
  //   // The route and the response format are not known yet.
  // }

  const anyOn = MEASURES.some((m) => options[m.key].on);

  return (
    <div style={styles.page}>
      <div ref={mapDiv} style={styles.map} />

      <aside style={styles.panel}>
        <h2 style={styles.h2}>Nadi flood planner</h2>
        {error && <p style={styles.error}>{error}</p>}
        {backend === "offline" && (
          <p style={styles.note}>Backend offline. Map colours are worked out locally and the ranked list is unavailable.</p>
        )}
        {backend === "not-set" && (
          <p style={styles.note}>No backend address set (VITE_API_URL). Using local calculations only.</p>
        )}

        {/* Slider */}
        <label style={styles.sliderLabel}>
          River rise above normal: <b>{level.toFixed(2)} m</b>
          <input
            type="range" min="0" max="6" step="0.25" value={level}
            onChange={(e) => setLevel(Number(e.target.value))}
            style={{ width: "100%" }}
          />
        </label>

        {/* Headline counts */}
        {counts && (
          <div style={styles.counts}>
            <Count number={counts.people} label="people with water inside" />
            <Count number={counts.facilities} label="facilities flooded" />
            <Count number={counts.roads} label="road sections cut" />
          </div>
        )}

        {/* 1. Most affected areas */}
        <h3 style={styles.h3}>Most affected areas</h3>
        {hotspots === null && counts && <p style={styles.muted}>Ranked list unavailable (needs the backend).</p>}
        {hotspots && hotspots.length === 0 && <p style={styles.muted}>Move the slider to see flooded areas.</p>}
        {hotspots && hotspots.length > 0 && (
          <div>
            {topShare !== null && topShare !== undefined && (
              <p style={styles.muted}>
                These areas hold {Math.round(topShare * 100)}% of the people with water inside. Click one to target it.
              </p>
            )}
            <div style={{ ...styles.row, fontWeight: 600 }}>
              <span>#</span><span>Area</span><span>Inside</span><span>Deep</span><span>Facilities</span>
            </div>
            {hotspots.map((a) => (
              <button
                key={a.name}
                onClick={() => pickArea(a)}
                style={{
                  ...styles.row, ...styles.rowButton,
                  background: selectedArea === a.name ? "#efe3fb" : "transparent",
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
                ? `Raise homes${selectedArea ? ` in ${selectedArea}` : " (pick an area above)"}`
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

        {/* 3. Results (changes with the tab) */}
        <h3 style={styles.h3}>Results</h3>
        {USE_PLACEHOLDER && (
          <p style={styles.note}>Placeholder numbers: made up to test the layout, not real model results.</p>
        )}
        {mitigationError && <p style={styles.error}>{mitigationError}</p>}
        {!anyOn && <p style={styles.muted}>Tick at least one option to see results.</p>}
        {anyOn && !mitigation && !mitigationError && <p style={styles.muted}>Loading results...</p>}
        {anyOn && mitigation && tab === "compare" && (
          <>
            <CompareBars mitigation={mitigation} level={level} />
            <CompareLines mitigation={mitigation} level={level} />
          </>
        )}
        {anyOn && mitigation && tab === "combine" && <Waterfall mitigation={mitigation} />}

        {/* Key */}
        <h3 style={styles.h3}>Key</h3>
        <div style={styles.legend}>
          {STATUS_LABELS.map(([key, label]) => (
            <div key={key}><Dot color={COLORS[key]} /> {label}</div>
          ))}
          <div><Dot color={COLORS.water} /> Flood water</div>
          <div><Dot color={COLORS.roadCut} /> Cut road</div>
        </div>

        <p style={styles.footer}>
          Modelled exposure (HAND), not a river-flow simulation. Data: FABDEM, OpenStreetMap, Overture.
        </p>
      </aside>
    </div>
  );
}

function Count({ number, label }) {
  return (
    <div style={styles.count}>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{number.toLocaleString()}</div>
      <div style={{ fontSize: 12 }}>{label}</div>
    </div>
  );
}

function Dot({ color }) {
  return (
    <span style={{
      display: "inline-block", width: 10, height: 10, borderRadius: "50%",
      background: color, marginRight: 6,
    }} />
  );
}

// ---------- 6. STYLES ----------
const styles = {
  page: { display: "flex", position: "fixed", inset: 0, fontFamily: "sans-serif" },
  map: { flex: 1, position: "relative" },
  panel: { width: 440, padding: 16, overflowY: "auto", background: "#fff", boxSizing: "border-box" },
  h2: { margin: "0 0 12px" },
  h3: { margin: "20px 0 8px" },
  sliderLabel: { display: "block", fontSize: 14 },
  counts: { display: "flex", gap: 8, marginTop: 16 },
  count: { flex: 1, background: "#f1f3f5", borderRadius: 6, padding: 8, textAlign: "center" },
  row: { display: "grid", gridTemplateColumns: "24px 1fr 56px 48px 70px", gap: 4, fontSize: 13, padding: "6px 4px" },
  rowButton: { width: "100%", border: "none", borderBottom: "1px solid #e9ecef", cursor: "pointer", font: "inherit", fontSize: 13 },
  legend: { fontSize: 13, lineHeight: 1.7 },
  footer: { fontSize: 12, color: "#555", marginTop: 20 },
  error: { color: "#b00020", fontSize: 13 },
  note: { background: "#fff3cd", padding: 8, borderRadius: 6, fontSize: 12 },
  muted: { fontSize: 13, color: "#555" },
  optionsHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", margin: "20px 0 8px" },
  tab: { border: "1px solid #adb5bd", background: "#fff", padding: "4px 12px", cursor: "pointer", font: "inherit", fontSize: 13 },
  tabOn: { background: "#1d3557", color: "#fff", borderColor: "#1d3557" },
  optionRow: { display: "flex", alignItems: "center", gap: 8, padding: "4px 0" },
  chartTitle: { fontSize: 13, fontWeight: 600, margin: "8px 0" },
  barRow: { display: "grid", gridTemplateColumns: "130px 1fr 52px", gap: 8, alignItems: "center", fontSize: 13, margin: "6px 0" },
  barLabel: { textAlign: "left" },
  barTrack: { background: "#e9ecef", height: 14, borderRadius: 3, overflow: "hidden" },
  barFill: { height: "100%" },
  barValue: { textAlign: "right" },
  wfRow: { display: "grid", gridTemplateColumns: "140px 1fr 96px", gap: 8, alignItems: "center", fontSize: 13, margin: "6px 0" },
  wfLabel: { textAlign: "left" },
  wfValue: { textAlign: "right", fontSize: 12 },
};
