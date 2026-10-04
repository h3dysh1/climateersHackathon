// App.jsx - Waterline (Nadi is the test city)
//
// Screens (hash routes, so the map stays loaded underneath):
//   #/              Home: what Waterline is, the data loading, choose a place
//   #/nadi          Planner: map with the river gauge and key; panel with 1 · 2 · 3
//   #/nadi/summary  Summary: the current scenario with charts from the backend, and the written plan
//
// 1. Where water gets inside: drag the river gauge; homes, facilities and roads update, and the most
//    affected areas are listed (backend: /flood and /hotspots).
// 2. Test options: dredging, raising homes and riverbank vegetation, each Low / Med / High
//    (presets come from the backend's /measures).
// 3. Results: one /compare-measures call gives each option alone and all of them layered in order.
// Styles live in index.css.

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./planner.css"; // map page styles (must load before Home and Summary)
import { addExtraLayers, setExtraVisibility, EXTRA_DEFAULTS, EXTRA_LAYERS, BANDS } from "./extraLayers";
import RiverGauge from "./RiverGauge";
import Home from "./Home";
import Summary from "./Summary";
import useRollingNumber from "./useRollingNumber";
import {
  MAX_LEVEL, DEEP_WATER_M, COLORS, OPTIONS, SIZES, ORDER, optionOf,
  fmt, fmtLevel, areaLabel, titleCase, optionsPhrase,
} from "./options";

// Backend address. Put it in frontend/.env.local like:  VITE_API_URL=http://localhost:8000
const API_URL = import.meta.env.VITE_API_URL;

// ---------- 1. SETTINGS ----------
const NADI_CENTER = [177.44, -17.79]; // [longitude, latitude]
const NADI_BOUNDS = [[177.38, -17.86], [177.52, -17.72]]; // same box as the data
const START_LEVEL = 2;
const DEBOUNCE_MS = 300;
const DEFAULT_FLOOR_M = 0.3;
const NEAR_RADIUS_M = 800; // "Around X" areas are targeted as a circle around their centre
const ROW_H = 64; // height of one row in the areas list (rows slide when they re-rank)

// The data behind each source on the home screen (files in public/data).
const SOURCES = [
  { label: "Ground height", name: "FABDEM", files: ["flood_extents.geojson"] },
  { label: "Rivers and roads", name: "OpenStreetMap", files: ["roads.json", "roads.geojson"] },
  { label: "Homes and buildings", name: "Overture Maps", files: ["buildings.json", "facilities.json"] },
  { label: "Where people live", name: "WorldPop", files: ["buildings.json"] }, // people per building
];

// ---------- 2. HELPERS ----------
function pointsToGeoJSON(rows) {
  return {
    type: "FeatureCollection",
    features: rows.map((r) => ({ type: "Feature", properties: r, geometry: { type: "Point", coordinates: [r.lon, r.lat] } })),
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
  for (const b of data.buildings) {
    const reached = level >= b.floods_at_m;
    const depth = level - b.ground_m;
    let status = 0;
    if (reached && level > b.ground_m + DEFAULT_FLOOR_M) {
      status = depth >= DEEP_WATER_M ? 3 : 2;
      people += b.people;
    } else if (reached && depth > 0) {
      status = 1;
    }
    homeStatus.set(b.id, status);
  }
  const floodedFacilities = new Set(
    data.facilities.filter((f) => level >= f.floods_at_m && level > f.ground_m + DEFAULT_FLOOR_M).map((f) => f.id)
  );
  const cutRoads = new Set(data.roads.filter((r) => level - r.low_point_m >= 0.3).map((r) => r.id));
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
    features: data.roadsGeo.features.map((f) => ({ ...f, properties: { ...f.properties, cut: result.cutRoads.has(f.properties.id) } })),
  });
}

// Switched-on options + Low/Med/High -> the backend's `options` object.
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

// Per-building rows are huge and the plan doesn't need them.
function slimFlood(flood) {
  const strip = (x) => (x ? { ...x, buildings: undefined } : x);
  return { ...flood, baseline: strip(flood.baseline), with_measures: strip(flood.with_measures) };
}

const screenFromHash = () => {
  const h = window.location.hash.replace(/^#\/?/, "");
  if (h.startsWith("nadi/summary")) return "summary";
  if (h.startsWith("nadi")) return "planner";
  return "home";
};

// One /compare-measures call gives each option alone AND all of them layered in ORDER.
// withCurves adds people-with-water-inside at every 0.5 m (for the summary charts).
function useCompare({ enabled, withCurves, ready, data, backend, level, choice, presets, area, setRes, setState }) {
  useEffect(() => {
    if (!enabled || !ready || !data || backend !== "online") return undefined;
    const opts = buildOptions(choice, presets, area);
    const order = ORDER.filter((k) => opts[k]);
    if (!order.length) {
      setRes(null);
      setState("idle");
      return undefined;
    }
    const controller = new AbortController();
    setState("loading");
    const timer = setTimeout(async () => {
      try {
        const t = targetFor(area);
        const res = await postJSON(
          "/compare-measures",
          {
            level_m: level,
            options: opts,
            buildings: data.buildings,
            facilities: data.facilities,
            roads: data.roads,
            order,
            ...(t ? { target: t } : {}),
            ...(withCurves ? { min_m: 0, max_m: MAX_LEVEL, step_m: 0.5 } : { min_m: level, max_m: level, step_m: 1 }),
          },
          controller.signal
        );
        if (controller.signal.aborted) return;
        setRes({ ...res, forLevel: level });
        setState("ready");
      } catch (err) {
        if (err.name === "AbortError") return;
        console.warn("Compare problem:", err);
        setState("error");
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, withCurves, ready, data, backend, level, choice, presets, area, setRes, setState]);
}

// ---------- 3. SMALL PIECES ----------
function OptionIcon({ k }) {
  if (k === "channel_clearing_m")
    return (
      <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><path d="M2 9 C6 6 10 12 14 9 S22 6 24 9" fill="none" stroke="#5AA6E8" strokeWidth="2" /><path d="M2 16 H24 M4 20 H22 M7 24 H19" stroke="#D6A273" strokeWidth="2.4" /></svg>
    );
  if (k === "raise_homes")
    return (
      <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><path d="M5 14 L13 7 L21 14 V22 H5 Z" fill="none" stroke="#A9A9F5" strokeWidth="2.2" strokeLinejoin="round" /><path d="M13 5 V1.5 M10.5 4 L13 1.5 L15.5 4" fill="none" stroke="#A9A9F5" strokeWidth="1.8" /><path d="M3 25 H23" stroke="#5AA6E8" strokeWidth="2" /></svg>
    );
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><path d="M8 22 C8 14 4 11 2 10 C7 10 9 13 9 16 M12 22 C12 12 15 7 19 5 C17 10 15 14 15 22 M18 22 C18 17 21 14 24 14" fill="none" stroke="#7FCB95" strokeWidth="2" strokeLinecap="round" /><path d="M1 24 H25" stroke="#D6A273" strokeWidth="2" /></svg>
  );
}

function MapKey({ available, on, onChange }) {
  const layers = EXTRA_LAYERS.filter((l) => available[l.id]);
  return (
    <details className="key" open={typeof window === "undefined" || window.innerWidth > 860}>
      <summary>
        Key and map layers
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 5 L7 9.5 L11 5" fill="none" stroke="currentColor" strokeWidth="2" /></svg>
      </summary>
      <div className="key-body">
        <div className="key-item"><i style={{ background: COLORS.reaching }} />Water at the door, not inside</div>
        <div className="key-item"><i style={{ background: COLORS.inside }} />Water inside home</div>
        <div className="key-item"><i style={{ background: COLORS.deep, boxShadow: "0 0 0 1.5px #E6EDF2" }} />Deep water (1 m or more)</div>
        <div className="key-item"><i style={{ background: COLORS.dry }} />Dry home</div>
        <div className="key-item"><i className="sq" style={{ background: COLORS.water }} />Flood water</div>
        <div className="key-item"><i className="ln" style={{ background: COLORS.roadCut }} />Road cut (30 cm of water)</div>
        <div className="key-item"><i style={{ background: "#fff", border: `2px solid ${COLORS.ink}` }} />Clinic, school or other facility</div>
        <div className="key-item"><i style={{ background: COLORS.inside, border: "2px solid #fff" }} />Facility flooded</div>
        <div className="key-item"><i style={{ background: "transparent", border: `1.5px solid ${COLORS.highlight}` }} />Homes in the raise-homes area</div>
        {layers.length > 0 && (
          <>
            <div className="key-div" />
            <div className="key-sub">Map layers</div>
            {layers.map((l) => (
              <div key={l.id}>
                <label className="key-chk">
                  <input type="checkbox" checked={!!on[l.id]} onChange={(e) => onChange(l.id, e.target.checked)} />
                  <span>{l.label}</span>
                </label>
                {l.id === "rivers" && on.rivers && <div className="key-note">Thicker line = bigger river.</div>}
                {l.id === "coast" && on.coast && (
                  <div className="key-note">
                    {BANDS.map(([key, label, color]) => (
                      <span key={key} className="key-item"><i style={{ background: color }} />{label}</span>
                    ))}
                    <span>Click a piece of coast for details.</span>
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </details>
  );
}

// ---------- 4. THE PAGE ----------
export default function App() {
  const mapDiv = useRef(null);
  const mapRef = useRef(null);

  const [screen, setScreen] = useState(screenFromHash);
  const [data, setData] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [files, setFiles] = useState({}); // file name -> "loading" | "done" | "failed"
  const [level, setLevel] = useState(START_LEVEL);
  const [area, setArea] = useState(null); // picked area: also the target for "Raise homes"
  const [backend, setBackend] = useState("checking");
  const [counts, setCounts] = useState(null);
  const [hotspots, setHotspots] = useState(null);
  const [topShare, setTopShare] = useState(null);
  const [extraOn, setExtraOn] = useState(EXTRA_DEFAULTS);
  const [extraAvailable, setExtraAvailable] = useState({});
  const [presets, setPresets] = useState(() => Object.fromEntries(OPTIONS.map((o) => [o.key, o.presets])));

  const [view, setView] = useState("together"); // results view in the planner: together | single
  const [choice, setChoice] = useState({
    channel_clearing_m: { on: true, size: "medium" },
    raise_homes: { on: true, size: "medium" },
    nature_based: { on: true, size: "medium" },
  });
  const [result, setResult] = useState(null); // planner: /compare-measures at the gauge level
  const [resultState, setResultState] = useState("idle"); // idle | loading | ready | error
  const [summary, setSummary] = useState(null); // summary page: same call with curves for 0–6 m
  const [summaryState, setSummaryState] = useState("idle");

  const [plan, setPlan] = useState(null); // { markdown, provider, fallback, error, settingsKey }
  const [planState, setPlanState] = useState("idle"); // idle | loading | error
  const [copied, setCopied] = useState(false);

  const setOpt = (key, patch) => setChoice((c) => ({ ...c, [key]: { ...c[key], ...patch } }));
  const peopleShown = useRollingNumber(counts?.people);

  // Hash routes
  useEffect(() => {
    const onHash = () => setScreen(screenFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (screen === "planner") mapRef.current?.resize();
  }, [screen]);

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
          dark: {
            // Standard OpenStreetMap tiles (no API key), turned into a dark map by the paint settings below.
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            maxzoom: 19,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [
          { id: "land", type: "background", paint: { "background-color": COLORS.land } },
          {
            id: "basemap",
            type: "raster",
            source: "dark",
            paint: {
              "raster-brightness-min": 0.92, // min above max flips light to dark
              "raster-brightness-max": 0.08,
              "raster-saturation": -0.85,
              "raster-contrast": 0.1,
              "raster-opacity": 0.9,
            },
          },
        ],
        layers: [
          { id: "land", type: "background", paint: { "background-color": COLORS.land } },
          { id: "basemap", type: "raster", source: "dark", paint: { "raster-opacity": 0.9 } },
        ],
      },
      center: NADI_CENTER,
      zoom: 12.3,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    mapRef.current = map;

    const mapLoaded = new Promise((resolve) => map.on("load", resolve));
    const mark = (name, status) => !cancelled && setFiles((f) => ({ ...f, [name]: status }));
    const file = (name) => {
      mark(name, "loading");
      return fetch(`/data/${name}`)
        .then((r) => {
          if (!r.ok) throw new Error(`Could not load /data/${name}`);
          return r.json();
        })
        .then((j) => {
          mark(name, "done");
          return j;
        })
        .catch((e) => {
          mark(name, "failed");
          throw e;
        });
    };
    const optional = (name) => fetch(`/data/${name}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);

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
          paint: { "fill-color": COLORS.water, "fill-opacity": 0.5 },
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
            "line-opacity": ["case", ["==", ["get", "cut"], true], 0.95, 0.7],
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
            "circle-opacity": ["match", ["get", "status"], 0, 0.6, 1],
            // a thin light ring keeps dark-red homes visible on the dark map
            "circle-stroke-color": "#E6EDF2",
            "circle-stroke-width": ["match", ["get", "status"], 3, 0.8, 0],
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
            "circle-stroke-color": ["case", ["==", ["get", "flooded"], true], "#ffffff", COLORS.ink],
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
        // Frame the town, leaving room for the key (top left) and the gauge (right edge).
        const narrow = mapDiv.current.clientWidth < 600;
        map.fitBounds(NADI_BOUNDS, { padding: { left: narrow ? 16 : 40, right: narrow ? 90 : 110, top: 30, bottom: 30 }, duration: 0 });
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

  // Results for the planner, and the curves for the summary page, from /compare-measures.
  const deps = { ready, data, backend, level, choice, presets, area };
  useCompare({ ...deps, enabled: true, withCurves: false, setRes: setResult, setState: setResultState });
  useCompare({ ...deps, enabled: screen === "summary", withCurves: true, setRes: setSummary, setState: setSummaryState });

  // Picked area -> ring its homes on the map.
  const targetIds = useMemo(() => {
    if (!data || !area) return [];
    const t = targetFor(area);
    return data.buildings.filter((b) => inTarget(b, t)).map((b) => b.id);
  }, [data, area]);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("highlight", ["in", ["get", "id"], ["literal", choice.raise_homes.on ? targetIds : []]]);
  }, [targetIds, ready, choice.raise_homes.on]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setExtraVisibility(map, extraOn);
  }, [extraOn, extraAvailable, ready]);

  // Areas re-rank as the river rises: remember last ranks so rows can show "up 2" / "down 1".
  const prevRanks = useRef({});
  const [moves, setMoves] = useState({});
  useEffect(() => {
    if (!hotspots) return;
    const now = Object.fromEntries(hotspots.map((a, i) => [a.name, i]));
    const m = {};
    for (const name in now) if (name in prevRanks.current) m[name] = prevRanks.current[name] - now[name];
    prevRanks.current = now;
    setMoves(m);
  }, [hotspots]);

  // The settings a plan was written for, so we can say when it is out of date.
  const settingsKey = JSON.stringify({ level, choice, area: area?.name ?? null });

  async function writePlan() {
    setPlanState("loading");
    setCopied(false);
    try {
      const measures = buildOptions(choice, presets, area);
      const flood = await postJSON("/flood", { level_m: level, buildings: data.buildings, facilities: data.facilities, roads: data.roads, measures });
      const res = await postJSON("/flood-plan", { area_name: "Nadi", place: "nadi", summary: slimFlood(flood) });
      setPlan({ ...res, settingsKey });
      setPlanState("idle");
    } catch (err) {
      console.warn("Plan problem:", err);
      setPlanState("error");
    }
  }
  async function copyPlan() {
    try {
      await navigator.clipboard.writeText(plan.markdown);
      setCopied(true);
    } catch {
      setCopied(false);
    }
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

  // Home screen: each source ticks off when its files have loaded.
  const sources = SOURCES.map((s) => {
    const st = s.files.map((f) => files[f]);
    const status = st.includes("failed") ? "failed" : st.every((x) => x === "done") ? "done" : st.some(Boolean) ? "loading" : "waiting";
    return { label: s.label, name: s.name, status };
  });

  const anyOn = OPTIONS.some((o) => choice[o.key].on);
  const nOn = OPTIONS.filter((o) => choice[o.key].on).length;
  const levelText = `${fmtLevel(level)} m`;
  const maxPeople = hotspots?.length ? hotspots[0].people_water_inside : 1;
  const lay = result?.layering;
  const lastStep = lay?.steps?.[lay.steps.length - 1];
  const base = result?.baseline?.people_water_inside ?? 0;
  const kept = lastStep?.people_protected_so_far ?? 0;
  const singles = result?.options ?? [];
  const best = singles[0];
  const maxAlone = Math.max(1, ...singles.map((o) => o.at_design_level.people_protected));
  const showResult = result && resultState !== "error";

  return (
    <>
      <div className="page" aria-hidden={screen !== "planner"}>
        <div className="map-wrap">
          <div ref={mapDiv} className="map" />
          <MapKey available={extraAvailable} on={extraOn} onChange={(id, value) => setExtraOn((o) => ({ ...o, [id]: value }))} />
          <RiverGauge level={level} onChange={setLevel} people={counts ? peopleShown : null} />
        </div>

        <aside className="panel" aria-label="Flood planner">
          <div className="panel-in">
            <div className="ph-top">
              <div className="ph-eyebrow"><i /><b>Waterline</b> · flood planner</div>
              <nav className="ph-nav" aria-label="Pages">
                <a href="#/">Places</a>
                <a href="#/nadi/summary">Summary</a>
              </nav>
            </div>
            <h1 className="ph-city">Nadi, Fiji<span className="ph-tag">Test city</span></h1>
            <p className="ph-lede">Raise the river on the gauge to see whose homes it reaches, then test three ways to keep the water out.</p>

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
                      At <span className="num">{levelText}</span>, water gets inside the homes of{" "}
                      <span className="num inside">{fmt(peopleShown)}</span> people, floods <span className="num">{fmt(counts.facilities)}</span>{" "}
                      {counts.facilities === 1 ? "facility" : "facilities"} and cuts <span className="num">{fmt(counts.roads)}</span> road sections.
                    </>
                  ) : (
                    <>At {levelText}, no homes have water inside. Drag the river gauge on the map to raise the river.</>
                  )}
                </p>
              )}
              {hotspots && hotspots.length > 0 && (
                <>
                  <div className="areas-head">
                    <b>Most affected areas{topShare != null && topShare < 0.995 ? ` · ${Math.round(topShare * 100)}% of those people` : ""}</b>
                    <span>Pick one to target raised homes</span>
                  </div>
                  <ul className="areas" style={{ height: hotspots.length * ROW_H }}>
                    {hotspots.map((a, i) => {
                      const deep = a.people_water_inside ? Math.min(a.people_deep_water, a.people_water_inside) : 0;
                      const selected = area?.name === a.name;
                      const mv = moves[a.name] || 0;
                      return (
                        <li key={a.name} className="area-row" style={{ top: i * ROW_H }}>
                          <button className="area" type="button" aria-pressed={selected} onClick={() => pickArea(a)}>
                            <span className="area-rank">
                              <span>{String(i + 1).padStart(2, "0")}</span>
                              {mv !== 0 && (
                                <span className="area-move" aria-label={mv > 0 ? `up ${mv}` : `down ${-mv}`}>
                                  <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true"><path d={mv > 0 ? "M4 1 L7.5 6.5 H0.5 Z" : "M4 7 L7.5 1.5 H0.5 Z"} fill="currentColor" /></svg>
                                  {Math.abs(mv)}
                                </span>
                              )}
                            </span>
                            <span className="area-mid">
                              <span className="area-top">
                                <span className="area-name">{titleCase(areaLabel(a))}</span>
                                {selected && choice.raise_homes.on && <span className="area-target">Raise here</span>}
                              </span>
                              <span className="area-bar" aria-hidden="true">
                                <span style={{ left: 0, width: `${(deep / maxPeople) * 100}%`, background: "var(--deep)" }} />
                                <span style={{ left: `${(deep / maxPeople) * 100}%`, width: `${((a.people_water_inside - deep) / maxPeople) * 100}%`, background: "var(--inside)" }} />
                              </span>
                              <span className="area-meta">
                                {fmt(a.people_deep_water)} in deep water
                                {a.facilities_flooded?.length ? ` · ${a.facilities_flooded.join(", ")} flooded` : ""}
                              </span>
                            </span>
                            <span className="area-count">{fmt(a.people_water_inside)}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  <div className="legend-row">
                    <span><i style={{ background: "var(--deep)" }} />People in deep water (1 m+)</span>
                    <span><i style={{ background: "var(--inside)" }} />Water inside, under 1 m</span>
                  </div>
                </>
              )}
            </section>

            {/* 2. Test options */}
            <section className="step" aria-labelledby="s2">
              <div className="step-head"><span className="step-n">2</span><h2 id="s2">Test options</h2></div>
              {OPTIONS.map((o) => {
                const c = choice[o.key];
                const v = presets[o.key][c.size];
                const idx = SIZES.findIndex(([k]) => k === c.size);
                return (
                  <div key={o.key} className={`option${c.on ? "" : " off"}`}>
                    <div className="option-top">
                      <button type="button" className="switch" aria-pressed={c.on} aria-label={`Use ${o.name}`} onClick={() => setOpt(o.key, { on: !c.on })} />
                      <span className="option-icon dim"><OptionIcon k={o.key} /></span>
                      <span className="option-name dim">{o.name}</span>
                      <span className="option-eff dim" style={{ color: o.text }}>{o.effect(v)}</span>
                    </div>
                    <div className="detent dim" role="group" aria-label={`${o.name} size`}>
                      <span className="detent-rail" />
                      <span className="detent-knob" style={{ left: `${16.667 + idx * 33.333}%`, background: c.on ? o.colorDk : "#8C948A" }} />
                      {SIZES.map(([k, label]) => (
                        <button key={k} type="button" className="detent-stop" aria-pressed={c.size === k} onClick={() => setOpt(o.key, { size: k, on: true })}>
                          <span className="detent-notch" />
                          <span className="detent-label">{label}</span>
                          <span className="detent-val">{o.stop(presets[o.key][k])}</span>
                        </button>
                      ))}
                    </div>
                    <p className="option-desc dim">{o.describe(v, o.key === "raise_homes" ? area : null)}</p>
                    {o.key === "raise_homes" && area && (
                      <div className="where dim">
                        Where
                        <div className="seg" role="group" aria-label="Where to raise homes">
                          <button type="button" aria-pressed={true}>{titleCase(areaLabel(area))}</button>
                          <button type="button" aria-pressed={false} onClick={() => setArea(null)}>Town-wide</button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </section>

            {/* 3. Results (short; the full breakdown is on the summary page) */}
            <section className="step" id="results" aria-labelledby="s3">
              <div className="step-head">
                <span className="step-n">3</span>
                <h2 id="s3">Results</h2>
                <span className="spacer" />
                <div className="seg" role="group" aria-label="How to compare">
                  <button type="button" aria-pressed={view === "together"} onClick={() => setView("together")}>All together</button>
                  <button type="button" aria-pressed={view === "single"} onClick={() => setView("single")}>One at a time</button>
                </div>
              </div>
              {backend !== "online" && <p className="muted">Results need the backend.</p>}
              {backend === "online" && !anyOn && <p className="muted">Switch on at least one option above.</p>}
              {backend === "online" && anyOn && counts?.people === 0 && (
                <p className="muted">Nobody has water inside at {levelText}, so there is nothing to protect yet. Raise the river on the gauge.</p>
              )}
              {resultState === "error" && <p className="notice error">The comparison failed. Check the backend terminal for the error.</p>}
              {anyOn && !showResult && resultState === "loading" && <p className="muted">Working out the results…</p>}
              {anyOn && showResult && base > 0 && (
                <div className={resultState === "loading" ? "loading-dim" : ""}>
                  {view === "together" && lastStep ? (
                    <>
                      <div className="verdict-box" aria-live="polite">
                        <div className="verdict-kick">At {fmtLevel(result.forLevel)} m, with {optionsPhrase(nOn)}</div>
                        <div className="verdict-row">
                          <span className="verdict-num">{fmt(kept)}</span>
                          <span className="verdict-of">of {fmt(base)} people would keep water out of their homes</span>
                          <span className="verdict-pct">{Math.round((kept / base) * 100)}%</span>
                        </div>
                        <div className="verdict-bar" aria-hidden="true">
                          {lay.steps.map((s) => (
                            <span key={s.added} style={{ width: `${(s.people_added_protection / base) * 100}%`, background: optionOf(s.added).color }} />
                          ))}
                        </div>
                        <div className="verdict-scale"><span><b>{fmt(kept)}</b> kept dry</span><span><b>{fmt(lastStep.people_still_water_inside)}</b> still have water inside</span></div>
                      </div>
                      <div className="steps-mini" aria-label="What each option adds">
                        {lay.steps.map((s) => (
                          <div key={s.added}>
                            <span className="sw" style={{ background: optionOf(s.added).colorDk }} />
                            <span>{optionOf(s.added).name}</span>
                            <b>−{fmt(s.people_added_protection)}</b>
                          </div>
                        ))}
                      </div>
                      <a className="more" href="#/nadi/summary">Full breakdown and charts in the summary →</a>
                    </>
                  ) : (
                    <>
                      {best && (
                        <div className="verdict-box" aria-live="polite">
                          <div className="verdict-kick">At {fmtLevel(result.forLevel)} m, each option on its own</div>
                          <div className="verdict-row">
                            <span className="verdict-num">{fmt(best.at_design_level.people_protected)}</span>
                            <span className="verdict-of">of {fmt(base)} people protected by {optionOf(best.key).short}, the strongest option on its own here</span>
                          </div>
                        </div>
                      )}
                      <div className="bars">
                        {singles.map((o) => {
                          const n = o.at_design_level.people_protected;
                          return (
                            <div key={o.key} className="bar-row">
                              <span className="bar-name"><i className="sw" style={{ background: optionOf(o.key).colorDk }} />{optionOf(o.key).name}</span>
                              <span className="bar-track" role="img" aria-label={`${fmt(n)} people protected`}>
                                <span style={{ width: `${(n / maxAlone) * 100}%`, background: optionOf(o.key).colorDk }} />
                              </span>
                              <span className="bar-val">{fmt(n)}</span>
                            </div>
                          );
                        })}
                      </div>
                      {singles
                        .filter((o) => o.key === "raise_homes" && o.at_design_level.people_protected === 0 && o.homes_too_deep_to_raise)
                        .map((o) => (
                          <p key="deep" className="hint">
                            Raising homes helps nobody at this level: the water is too deep for a 1 m lift ({fmt(o.homes_too_deep_to_raise)} homes too deep).
                          </p>
                        ))}
                      <a className="more" href="#/nadi/summary">Charts for every river level in the summary →</a>
                    </>
                  )}
                </div>
              )}
            </section>
          </div>

          <p className="footer">
            A planning screen, not a flood forecast: it shows which ground the river reaches as it rises (height above
            nearest drainage), not how water flows. Option effects are what-ifs. Data: FABDEM, OpenStreetMap, Overture Maps, WorldPop.
          </p>
          <div className="strip">
            <span className="strip-t">
              {!counts ? "Loading…" : counts.people === 0 ? `No homes flood at ${levelText}.` : !anyOn || !lastStep ? `At ${levelText}: ` : `With ${optionsPhrase(nOn)}: `}
              {counts && counts.people > 0 && lastStep && anyOn ? (
                <><b>{fmt(kept)}</b> kept dry · {fmt(lastStep.people_still_water_inside)} still flooded</>
              ) : counts && counts.people > 0 ? (
                <><b>{fmt(counts.people)}</b> people with water inside</>
              ) : null}
            </span>
            <button type="button" className="strip-link" onClick={() => document.getElementById("results")?.scrollIntoView({ behavior: "smooth" })}>Results</button>
            <a className="solid" href="#/nadi/summary">Summary</a>
          </div>
        </aside>
      </div>

      {screen === "summary" && (
        <Summary
          level={level}
          choice={choice}
          presets={presets}
          area={area}
          counts={counts}
          hotspots={hotspots}
          backend={backend}
          result={summary}
          resultState={summaryState}
          plan={plan}
          planState={planState}
          onWritePlan={writePlan}
          onCopyPlan={copyPlan}
          onDownloadPlan={downloadPlan}
          copied={copied}
          planOutdated={plan ? plan.settingsKey !== settingsKey : false}
        />
      )}

      {screen === "home" && <Home sources={sources} onOpen={() => (window.location.hash = "#/nadi")} />}
    </>
  );
}
