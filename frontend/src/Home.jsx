// Home: Waterline intro, the data-loading card (river gauge + sources) and "Choose a place".
// The source list ticks off as the real data files finish loading in App.jsx.
import "./home.css";

const PLACES = [
  { id: "nadi", name: "Nadi, Fiji", sub: "Lower Nadi River", ready: true, isTest: true, pin: { left: "16.5%", top: "52%" } },
  { id: "more", name: "More places", sub: "Prepared from the same four open datasets", ready: false },
];

export default function Home({ sources, leaving, onOpen }) {
  const done = sources.filter((s) => s.status === "done").length;
  const failed = sources.some((s) => s.status === "failed");
  const ready = done === sources.length;
  const frac = (done / sources.length) * 0.5; // fills to 3 m on a 0–6 m post

  return (
    <div className={`home${leaving ? " leaving" : ""}`} role="dialog" aria-modal="true" aria-labelledby="home-title">
      <svg className="home-topo" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <g fill="none" stroke="#16242F" strokeWidth="1.4">
          <path d="M-50,110 C250,40 420,200 720,140 S1200,40 1500,120" />
          <path d="M-50,180 C240,120 440,270 740,210 S1210,110 1500,190" />
          <path d="M-50,760 C280,690 480,830 780,770 S1240,690 1500,750" />
          <path d="M-50,830 C270,780 500,900 800,840 S1250,780 1500,820" />
        </g>
      </svg>

      <div className="home-main">
        <div className="home-eyebrow"><i />Flood planning, place by place · COP31</div>
        <h1 className="home-title" id="home-title">Waterline</h1>
        <p className="home-lede">
          Choose a place, simulate the flood and see whose homes it reaches, then compare ways to keep the water out.
        </p>

        <section className="card" aria-labelledby="data-t">
          <div className="card-head"><span className="card-tag">Open data</span><h2 id="data-t">What every place is built from</h2></div>
          <div className="load-title" aria-live="polite">
            {failed ? "Some map data could not load" : ready ? "Map data loaded" : "Loading map data"}
            <span>{done} of {sources.length}</span>
          </div>
          <div className="hg-label">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <rect x="5" y="1" width="6" height="14" fill="#FBFBF7" stroke="#E6EDF2" />
              <path d="M6 3 H9 M6 6 H8 M6 9 H9 M6 12 H8" stroke="#10222F" strokeWidth="1.2" />
              <rect x="5.5" y="9.5" width="5" height="5" fill="rgba(43,116,184,.7)" />
            </svg>
            <b>River gauge</b><span>how far the river rises above normal, in metres</span>
          </div>
          <div role="img" aria-label={`River gauge filling to ${(frac * 6).toFixed(1)} metres above normal`}>
            <div className="hg-post">
              <div className="hg-water" style={{ width: `${frac * 100}%` }} />
              <span className="hg-line" style={{ left: `${frac * 100}%` }} />
            </div>
            <div className="hg-nums">
              {[0, 1, 2, 3, 4, 5, 6].map((m) => (
                <span key={m} className={m === 3 ? "on" : ""} style={{ left: `${(m / 6) * 100}%` }}>{m === 3 ? "3 m" : m}</span>
              ))}
            </div>
          </div>
          <div className="src-h">Where our information comes from</div>
          {sources.map((s) => (
            <div key={s.label} className={`src${s.status === "waiting" ? " wait" : s.status === "failed" ? " failed" : ""}`}>
              <span className="src-ic">
                {s.status === "done" && <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5 L6.5 12 L13 4.5" fill="none" stroke="#9FD3A8" strokeWidth="2.2" /></svg>}
                {s.status === "loading" && <span className="spin" />}
                {s.status === "waiting" && <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3" fill="#3B5162" /></svg>}
                {s.status === "failed" && <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 3 L11 11 M11 3 L3 11" stroke="#FFB4A6" strokeWidth="2" /></svg>}
              </span>
              <span>{s.label}</span>
              <span className="src-name">{s.name}</span>
            </div>
          ))}
        </section>
      </div>

      <div className="home-place">
        <div className="place-title"><span className="place-n">1</span>Choose a place</div>
        <div className="place-sub">Click the city to start.</div>
        <div className="place-map">
          <VitiLevu />
          {PLACES.filter((p) => p.pin).map((p) => (
            <button key={p.id} type="button" className="pin" style={{ left: p.pin.left, top: p.pin.top }} onClick={onOpen} aria-label={`Open ${p.name}`}>
              <span className="pin-dot" />
              <span className="pin-label"><b>{p.name.split(",")[0]}</b><span>{p.sub}</span></span>
            </button>
          ))}
        </div>
        <div className="places">
          {PLACES.map((p) => (
            <button key={p.id} type="button" className="pl" disabled={!p.ready} onClick={onOpen}>
              <span className="pl-dot" style={p.ready ? { background: "var(--inside)" } : { border: "2px dashed #5F7280" }} />
              <span className="pl-n"><b>{p.name}</b><span>{p.sub}</span></span>
              <span className={`pl-tag${p.ready ? " ready" : ""}`}>{p.ready ? "Test city · ready" : "Not prepared yet"}</span>
            </button>
          ))}
        </div>
        <button className="cta" type="button" onClick={onOpen} disabled={!ready && !failed}>
          {ready || failed ? "Open Nadi" : "Loading Nadi…"}
          <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10 H15 M10.5 5.5 L15 10 L10.5 14.5" fill="none" stroke="currentColor" strokeWidth="2.2" /></svg>
        </button>
      </div>

      <div className="home-foot">A planning screen, not a flood forecast. Data: FABDEM, OpenStreetMap, Overture Maps, WorldPop.</div>
    </div>
  );
}

// Schematic outline only, not to scale. Swap for a real overview map when more places are added.
function VitiLevu() {
  return (
    <svg viewBox="0 0 620 440" role="img" aria-label="Schematic outline of Viti Levu, Fiji, with Nadi on the west coast">
      <defs>
        <pattern id="sea" width="14" height="14" patternUnits="userSpaceOnUse"><path d="M0,7 Q3.5,4 7,7 T14,7" fill="none" stroke="#15242F" strokeWidth="1" /></pattern>
      </defs>
      <rect x="0" y="0" width="620" height="440" fill="url(#sea)" />
      <path d="M78,200 C84,128 150,86 236,74 C318,60 410,64 480,96 C552,122 590,178 574,240 C562,300 512,342 440,362 C358,386 266,384 196,358 C124,334 70,276 78,200 Z" fill="#1F3240" stroke="#3B5162" strokeWidth="1.5" />
      <path d="M120,236 C170,220 210,180 260,170 C320,158 360,196 420,190" fill="none" stroke="#5AA6E8" strokeWidth="2.5" strokeLinecap="round" opacity=".8" />
      <path d="M250,260 C300,250 330,290 400,300 C450,306 480,330 520,320" fill="none" stroke="#5AA6E8" strokeWidth="2" strokeLinecap="round" opacity=".6" />
      <text x="330" y="234" textAnchor="middle" style={{ font: "600 20px 'IBM Plex Sans Condensed',sans-serif", fill: "#8FA2B0" }}>Viti Levu</text>
      <circle cx="486" cy="344" r="5" fill="#8FA2B0" />
      <text x="498" y="364" style={{ font: "500 13px 'Public Sans',sans-serif", fill: "#8FA2B0" }}>Suva</text>
      <text x="30" y="420" style={{ font: "500 12px 'Public Sans',sans-serif", fill: "#8FA2B0" }}>Schematic outline, not to scale</text>
    </svg>
  );
}
