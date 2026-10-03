// extraLayers.jsx - P2's extra map files: rivers, mangroves, restorable, coast_segments
// Put this file in frontend/src/ next to App.jsx.
//
// What it gives App.jsx:
//   addExtraLayers(map, files)   draws whichever files loaded, returns { rivers: true, ... }
//   setExtraVisibility(map, on)  shows or hides each group
//   EXTRA_DEFAULTS               which toggles start switched on
//   MapLayersPanel               the "Map layers" checkboxes + small legend

import maplibregl from "maplibre-gl";

// ---------- Settings ----------
const COLORS = {
  river: "#1d70b8",
  mangrove: "#2d9a4b",
  restorable: "#8fd694",
  restorableLine: "#4c9a5b",
};
// Coast bands. These colours are different from the home colours on purpose.
const BANDS = [
  ["strong", "Strong (mangroves protect well)", "#2d6a4f"],
  ["partial", "Partial", "#ffd166"],
  ["exposed", "Exposed", "#b5179e"],
];

export const EXTRA_DEFAULTS = { rivers: true, mangroves: false, restorable: false, coast: false };

export const EXTRA_LAYERS = [
  { id: "rivers", label: "Rivers, streams and drains", color: COLORS.river, mapLayers: ["rivers-line"] },
  { id: "mangroves", label: "Mangroves today", color: COLORS.mangrove, mapLayers: ["mangroves-fill"] },
  { id: "restorable", label: "Lost since 1996, could be replanted", color: COLORS.restorable, mapLayers: ["restorable-fill", "restorable-outline"] },
  { id: "coast", label: "Coast: mangrove wave protection", color: "#ffd166", mapLayers: ["coast-line"] },
];

const vis = (id) => (EXTRA_DEFAULTS[id] ? "visible" : "none");

// ---------- Drawing the layers ----------
// files = { rivers, mangroves, restorable, coast } (any of them may be null if it failed to load)
export function addExtraLayers(map, files) {
  const added = {};

  // Layers are slotted in with "beforeId", so they sit under the flood water and homes:
  // rivers, mangroves and restorable go under the water layer; the coast goes under the homes.

  if (files.mangroves) {
    map.addSource("mangroves", { type: "geojson", data: files.mangroves });
    map.addLayer(
      {
        id: "mangroves-fill",
        type: "fill",
        source: "mangroves",
        layout: { visibility: vis("mangroves") },
        paint: { "fill-color": COLORS.mangrove, "fill-opacity": 0.55 },
      },
      "water"
    );
    added.mangroves = true;
  }

  if (files.restorable) {
    map.addSource("restorable", { type: "geojson", data: files.restorable });
    map.addLayer(
      {
        id: "restorable-fill",
        type: "fill",
        source: "restorable",
        layout: { visibility: vis("restorable") },
        paint: { "fill-color": COLORS.restorable, "fill-opacity": 0.35 },
      },
      "water"
    );
    // Dashed outline so it reads as "not there any more"
    map.addLayer(
      {
        id: "restorable-outline",
        type: "line",
        source: "restorable",
        layout: { visibility: vis("restorable") },
        paint: { "line-color": COLORS.restorableLine, "line-width": 1.2, "line-dasharray": [2, 2] },
      },
      "water"
    );
    added.restorable = true;
  }

  if (files.rivers) {
    map.addSource("rivers", { type: "geojson", data: files.rivers });
    map.addLayer(
      {
        id: "rivers-line",
        type: "line",
        source: "rivers",
        layout: { visibility: vis("rivers"), "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": COLORS.river,
          // Main rivers thicker than drains. CHECK the real values of the `waterway`
          // property in rivers.geojson and edit the names below to match.
          "line-width": [
            "match", ["get", "waterway"],
            "river", 4,
            "canal", 2.5,
            "stream", 2,
            "drain", 1,
            1.5, // anything else
          ],
        },
      },
      "water"
    );
    added.rivers = true;
  }

  if (files.coast) {
    map.addSource("coast", { type: "geojson", data: files.coast });
    map.addLayer(
      {
        id: "coast-line",
        type: "line",
        source: "coast",
        layout: { visibility: vis("coast"), "line-cap": "round" },
        paint: {
          "line-width": 5,
          "line-color": [
            "match", ["get", "band_now"],
            "strong", BANDS[0][2],
            "partial", BANDS[1][2],
            "exposed", BANDS[2][2],
            "#999999",
          ],
        },
      },
      "homes"
    );

    // Click a piece of coast to see its details.
    map.on("click", "coast-line", (e) => {
      new maplibregl.Popup({ maxWidth: "280px" })
        .setLngLat(e.lngLat)
        .setDOMContent(coastPopupNode(e.features[0].properties))
        .addTo(map);
    });
    map.on("mouseenter", "coast-line", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "coast-line", () => (map.getCanvas().style.cursor = ""));
    added.coast = true;
  }

  return added;
}

// Show or hide each group. `on` looks like { rivers: true, mangroves: false, ... }
export function setExtraVisibility(map, on) {
  for (const group of EXTRA_LAYERS) {
    for (const layerId of group.mapLayers) {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, "visibility", on[group.id] ? "visible" : "none");
      }
    }
  }
}

// The popup lists every property of the clicked piece.
// TODO: once P2 confirms the field names (mangrove width, wave reduction now vs after
// replanting), show just those with friendly labels instead of the full list.
function coastPopupNode(props) {
  const box = document.createElement("div");
  box.style.cssText = "font-family: sans-serif; font-size: 12px;";

  const title = document.createElement("b");
  title.textContent = `Coast piece: ${props.band_now ?? "unknown"}`;
  box.append(title);

  const table = document.createElement("table");
  table.style.cssText = "margin-top: 6px; border-collapse: collapse;";
  for (const [key, value] of Object.entries(props)) {
    const row = table.insertRow();
    const k = row.insertCell();
    const v = row.insertCell();
    k.style.cssText = "padding: 2px 8px 2px 0; color: #555;";
    k.textContent = key;
    v.textContent = typeof value === "number" ? String(Math.round(value * 100) / 100) : String(value);
  }
  box.append(table);
  return box;
}

// ---------- The "Map layers" checkboxes ----------
function Dot({ color }) {
  return (
    <span style={{
      display: "inline-block", width: 10, height: 10, borderRadius: "50%",
      background: color, marginRight: 6,
    }} />
  );
}

export function MapLayersPanel({ available, on, onChange }) {
  const items = EXTRA_LAYERS.filter((l) => available[l.id]);
  if (items.length === 0) return null;

  const small = { fontSize: 12, color: "#555", margin: "2px 0 6px 22px" };

  return (
    <div>
      <h3 style={{ margin: "20px 0 8px" }}>Map layers</h3>
      {items.map((l) => (
        <div key={l.id} style={{ margin: "4px 0" }}>
          <label style={{ fontSize: 14 }}>
            <input
              type="checkbox"
              checked={!!on[l.id]}
              onChange={(e) => onChange(l.id, e.target.checked)}
            />{" "}
            <Dot color={l.color} />
            {l.label}
          </label>
          {l.id === "rivers" && on.rivers && <div style={small}>Thicker line = bigger river.</div>}
          {l.id === "restorable" && on.restorable && (
            <div style={small}>Mangrove areas lost since 1996 that could be replanted.</div>
          )}
          {l.id === "coast" && on.coast && (
            <div style={small}>
              {BANDS.map(([key, label, color]) => (
                <div key={key}><Dot color={color} />{label}</div>
              ))}
              <div>Click a piece of coast for details.</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
