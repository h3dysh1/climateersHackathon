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

// App.jsx - starter structure for the P1 frontend (React + MapLibre)
//
// Install first:  npm install maplibre-gl
// Make the project with:  npm create vite@latest frontend -- --template react
//
// This is a SKELETON. The data is fake so you can see something working.
// Replace the fake data with real files from P2 (risk.json) and P3 (roof_labels.json) later.


import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
/*
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-csp-worker.js?url";
import "maplibre-gl/dist/maplibre-gl.css";
maplibregl.setWorkerUrl(workerUrl);
*/



// ---------- 1. FAKE DATA (replace later) ----------
// Each building has an id, a place on the map, a risk score (0 to 1) and AI roof labels.
const FAKE_BUILDINGS = [
  { id: 1, lng: 178.44, lat: -18.14, risk: 0.9, roof: "tin", shape: "gable", condition: "poor" },
  { id: 2, lng: 178.45, lat: -18.15, risk: 0.5, roof: "tin", shape: "hip", condition: "fair" },
  { id: 3, lng: 178.46, lat: -18.14, risk: 0.2, roof: "concrete", shape: "flat", condition: "good" },
];

// Turn a risk number into a colour: red = high, orange = medium, green = low
function riskColor(risk) {
  if (risk > 0.66) return "#d62828";
  if (risk > 0.33) return "#f77f00";
  return "#2a9d8f";
}

// ---------- 2. THE MAP ----------
// Draws the map and one coloured dot per building.
// When someone clicks a dot, we tell the page which building was picked.
function MapView({ buildings, onSelect }) {
  const mapDiv = useRef(null);

  useEffect(() => {
    const map = new maplibregl.Map({
      container: mapDiv.current,
      style: "https://demotiles.maplibre.org/style.json", // free test map
      center: [177.45, -17.62], // [longitude, latitude] - change to your pilot area
      zoom: 13,
    });

    map.on("load", () => {
      // Put the buildings on the map as GeoJSON
      map.addSource("buildings", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: buildings.map((b) => ({
            type: "Feature",
            properties: { id: b.id, color: riskColor(b.risk) },
            geometry: { type: "Point", coordinates: [b.lng, b.lat] },
          })),
        },
      });

      // Draw each building as a circle, using its own colour
      map.addLayer({
        id: "buildings-layer",
        type: "circle",
        source: "buildings",
        paint: { "circle-radius": 8, "circle-color": ["get", "color"] },
      });

      // Click a circle -> tell the page which building it was
      map.on("click", "buildings-layer", (e) => {
        const id = e.features[0].properties.id;
        onSelect(buildings.find((b) => b.id === id));
      });
    });

    return () => map.remove(); // clean up when the page closes
  }, [buildings]);

  return <div ref={mapDiv} style={{ position: "absolute", inset: 0 }} />;
}

// ---------- 3. SMALL PIECES OF THE PAGE ----------
function Legend() {
  return (
    <div style={box({ left: 12, bottom: 12 })}>
      <b>Risk (approximate)</b>
      <div><span style={{ color: "#d62828" }}>●</span> High</div>
      <div><span style={{ color: "#f77f00" }}>●</span> Medium</div>
      <div><span style={{ color: "#2a9d8f" }}>●</span> Low</div>
    </div>
  );
}

function BuildingPopup({ building, onClose }) {
  if (!building) return null;
  return (
    <div style={box({ right: 12, top: 12, width: 240 })}>
      <button onClick={onClose}>Close</button>
      <h3>Building {building.id}</h3>
      {/* Later: <img src={`/tiles/${building.id}.png`} /> from P2's image tiles */}
      <p>Roof material: {building.roof}</p>
      <p>Roof shape: {building.shape}</p>
      <p>Condition: {building.condition}</p>
      <p>Risk score: {building.risk} (approximate)</p>
    </div>
  );
}

function ValidationPanel() {
  // Later: fill these in with P2's validation numbers
  return (
    <div style={box({ left: 12, top: 12, width: 220 })}>
      <b>Does the model match reality?</b>
      <p>Match score: -- (waiting for P2)</p>
      <p>Predicted damage vs actual damage goes here.</p>
    </div>
  );
}

function UpgradePlanner({ budget, setBudget, onDownload }) {
  return (
    <div style={box({ right: 12, bottom: 12, width: 240 })}>
      <b>Upgrade planner</b>
      <p>Homes to upgrade: {budget}</p>
      <input
        type="range" min="0" max="3" value={budget}
        onChange={(e) => setBudget(Number(e.target.value))}
      />
      {/* Later: show before/after counts from P3's /plan-upgrades */}
      <button onClick={onDownload}>Download resilience plan</button>
    </div>
  );
}

// ---------- 4. THE WHOLE PAGE ----------
// State = things the page remembers: which building is selected, and the budget.
export default function App() {
  const [selected, setSelected] = useState(null);
  const [budget, setBudget] = useState(0);

  // Pretend upgrade: the highest-risk homes get a lower risk.
  // Later: replace this with a call to P3's POST /plan-upgrades.
  const sorted = [...FAKE_BUILDINGS].sort((a, b) => b.risk - a.risk);
  const upgradedIds = sorted.slice(0, budget).map((b) => b.id);
  const buildings = FAKE_BUILDINGS.map((b) =>
    upgradedIds.includes(b.id) ? { ...b, risk: 0.1 } : b
  );

  function downloadPlan() {
    // Later: call P3's POST /resilience-plan and download the result
    alert("This will call P3's /resilience-plan endpoint.");
  }

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh" }}>
      <MapView buildings={buildings} onSelect={setSelected} />
      <ValidationPanel />
      <BuildingPopup building={selected} onClose={() => setSelected(null)} />
      <UpgradePlanner budget={budget} setBudget={setBudget} onDownload={downloadPlan} />
      <Legend />
    </div>
  );
}

// Simple style helper so floating boxes look the same
function box(position) {
  return {
    position: "absolute", background: "white", padding: 12,
    borderRadius: 6, boxShadow: "0 1px 6px rgba(0,0,0,0.3)",
    fontFamily: "sans-serif", fontSize: 14, ...position,
  };
}

