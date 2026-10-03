/*import { useState } from 'react'
import heroImg from './assets/hero.png'
import reactLogo from './assets/react.svg'
import viteLogo from './assets/vite.svg'
import './App.css'

function App() {
  const [count, setCount] = useState(0)

  return (
    <>
      <section id="center">
        <div className="hero">
          <img src={heroImg} className="base" width="170" height="179" alt="" />
          <img src={reactLogo} className="framework" alt="React logo" />
          <img src={viteLogo} className="vite" alt="Vite logo" />
        </div>
        <div>
          <h1>Get started</h1>
          <p>
            Edit <code>src/App.jsx</code> and save to test <code>HMR</code>
          </p>
        </div>
        <button
          type="button"
          className="counter"
          onClick={() => setCount((count) => count + 1)}
        >
          Count is {count}
        </button>
      </section>

      <div className="ticks"></div>

      <section id="next-steps">
        <div id="docs">
          <svg className="icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#documentation-icon"></use>
          </svg>
          <h2>Documentation</h2>
          <p>Your questions, answered</p>
          <ul>
            <li>
              <a href="https://vite.dev/" target="_blank">
                <img className="logo" src={viteLogo} alt="" />
                Explore Vite
              </a>
            </li>
            <li>
              <a href="https://react.dev/" target="_blank">
                <img className="button-icon" src={reactLogo} alt="" />
                Learn more
              </a>
            </li>
          </ul>
        </div>
        <div id="social">
          <svg className="icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#social-icon"></use>
          </svg>
          <h2>Connect with us</h2>
          <p>Join the Vite community</p>
          <ul>
            <li>
              <a href="https://github.com/vitejs/vite" target="_blank">
                <svg
                  className="button-icon"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#github-icon"></use>
                </svg>
                GitHub
              </a>
            </li>
            <li>
              <a href="https://chat.vite.dev/" target="_blank">
                <svg
                  className="button-icon"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#discord-icon"></use>
                </svg>
                Discord
              </a>
            </li>
            <li>
              <a href="https://x.com/vite_js" target="_blank">
                <svg
                  className="button-icon"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#x-icon"></use>
                </svg>
                X.com
              </a>
            </li>
            <li>
              <a href="https://bsky.app/profile/vite.dev" target="_blank">
                <svg
                  className="button-icon"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#bluesky-icon"></use>
                </svg>
                Bluesky
              </a>
            </li>
          </ul>
        </div>
      </section>

      <div className="ticks"></div>
      <section id="spacer"></section>
    </>
  )
}

export default App
*/

// App.jsx - Nadi flood map (P1 frontend), version with backend calls
//
// How it works:
// - The slider changes the water layer straight away (it reads flood_extents.geojson).
// - 300 ms after the slider stops, the page asks P3's backend (/flood and /hotspots)
//   which homes, facilities and roads are flooded, and fills the counts and ranked list.
// - If the backend is down (or VITE_API_URL is missing), homes, facilities and roads are
//   coloured locally so the map still works, and the ranked list shows "unavailable".

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// Address of P3's backend. Put it in frontend/.env like:  VITE_API_URL=http://localhost:8000
const API_URL = import.meta.env.VITE_API_URL;

// ---------- 1. SETTINGS ----------
const NADI_CENTER = [177.42, -17.8]; // [longitude, latitude]
const DEBOUNCE_MS = 300;
const DEEP_WATER_M = 1.0; // "deep water" = 1 m or more

// Keep these colours the same everywhere (map, legend, list)
const COLORS = {
  dry: "#8d99ae", // dry home: grey
  reaching: "#f9a03f", // water reaches the home but is not inside: amber
  inside: "#d62828", // water inside: red
  deep: "#7f0000", // deep water (1 m or more): dark red
  water: "#2b8cbe", // flood water: semi-transparent blue
  road: "#444444",
  roadCut: "#d62828", // cut road: red
  highlight: "#7b2cbf", // ring around the area picked in the list
};

// Home status numbers: 0 dry, 1 water reaching, 2 water inside, 3 deep water
const STATUS_LABELS = [
  ["dry", "Dry home"],
  ["reaching", "Water reaching, not inside"],
  ["inside", "Water inside"],
  ["deep", "Deep water (1 m or more)"],
];

// ---------- 2. HELPERS ----------
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

// The backend may send flooded things as plain ids or as objects with an id.
const idOf = (x) => (x !== null && typeof x === "object" ? x.id : x);

async function postJSON(path, body, signal) {
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
    hotspots: null, // the ranked list needs the backend
    topShare: null,
  };
}

// Turn the backend's answers into the same shape the page uses.
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

// Push a result onto the map (re-colour homes, facilities and roads).
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

// ---------- 3. THE PAGE ----------
export default function App() {
  const mapDiv = useRef(null);
  const mapRef = useRef(null);

  const [data, setData] = useState(null); // the loaded files
  const [ready, setReady] = useState(false); // map and files both loaded
  const [error, setError] = useState("");
  const [level, setLevel] = useState(0); // slider, in metres
  const [selectedArea, setSelectedArea] = useState(null);
  const [backend, setBackend] = useState("checking"); // checking | online | offline | not-set
  const [counts, setCounts] = useState(null);
  const [hotspots, setHotspots] = useState(null); // null = unavailable
  const [topShare, setTopShare] = useState(null);

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

        // Added bottom first. On screen, top to bottom:
        // facilities, homes, roads, water, basemap.
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

  // Slider stops for 300 ms -> ask the backend (or use the backup plan).
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
          if (err.name === "AbortError") return; // slider moved again, ignore
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

  return (
    <div style={styles.page}>
      <div ref={mapDiv} style={styles.map} />

      <aside style={styles.panel}>
        <h2 style={styles.h2}>Nadi flood map</h2>
        {error && <p style={styles.error}>{error}</p>}
        {backend === "offline" && (
          <p style={styles.note}>Backend offline. Map colours are worked out locally and the ranked list is unavailable.</p>
        )}
        {backend === "not-set" && (
          <p style={styles.note}>No backend address set (VITE_API_URL). Using local calculations only.</p>
        )}

        {/* 1. Slider */}
        <label style={styles.sliderLabel}>
          River rise above normal: <b>{level.toFixed(1)} m</b>
          <input
            type="range" min="0" max="6" step="0.5" value={level}
            onChange={(e) => setLevel(Number(e.target.value))}
            style={{ width: "100%" }}
          />
        </label>

        {/* 2. Headline counts */}
        {counts && (
          <div style={styles.counts}>
            <Count number={counts.people} label="people with water inside" />
            <Count number={counts.facilities} label="facilities flooded" />
            <Count number={counts.roads} label="road sections cut" />
          </div>
        )}

        {/* 3. Most affected areas */}
        <h3 style={styles.h3}>Most affected areas</h3>
        {hotspots === null && counts && <p style={styles.muted}>Ranked list unavailable (needs the backend).</p>}
        {hotspots && hotspots.length === 0 && <p style={styles.muted}>Move the slider to see flooded areas.</p>}
        {hotspots && hotspots.length > 0 && (
          <div>
            {topShare !== null && topShare !== undefined && (
              <p style={styles.muted}>
                These areas hold {Math.round(topShare * 100)}% of the people with water inside.
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

        {/* Legend */}
        <h3 style={styles.h3}>Key</h3>
        <div style={styles.legend}>
          {STATUS_LABELS.map(([key, label]) => (
            <div key={key}><Dot color={COLORS[key]} /> {label}</div>
          ))}
          
          <div><Dot color={COLORS.roadCut} /> Cut road</div>
        </div>

        {/* 4. Footer */}
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

// ---------- 4. STYLES ----------
const styles = {
  page: { display: "flex", position: "fixed", inset: 0, fontFamily: "sans-serif" },
  map: { flex: 1, position: "relative" },
  panel: { width: 360, padding: 16, overflowY: "auto", background: "#fff", boxSizing: "border-box" },
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
};