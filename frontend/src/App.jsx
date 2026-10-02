import React, { useEffect, useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { Map } from 'react-map-gl/maplibre';
import { BAND_COLOURS, counts, loadData, planUpgrades, resiliencePlan } from './api.js';

// Free dark basemap (attribution: © OpenStreetMap contributors, © CARTO).
const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const AREA_NAME = 'Pilot area'; // P1: replace with the real district name

const INITIAL_VIEW = { longitude: 178.1, latitude: -17.5, zoom: 9, pitch: 0, bearing: 0 };

export default function App() {
  const [data, setData] = useState(null);
  const [budget, setBudget] = useState(0);
  const [plan, setPlan] = useState(null);
  const [selected, setSelected] = useState(null);
  const [planText, setPlanText] = useState('');
  const [planBusy, setPlanBusy] = useState(false);

  useEffect(() => {
    loadData().then(setData);
  }, []);

  // Join building points with risk scores and roof labels.
  const buildings = useMemo(() => {
    if (!data) return [];
    const riskById = Object.fromEntries(data.risk.map((r) => [r.id, r]));
    return data.buildings.features
      .filter((f) => riskById[f.properties.id])
      .map((f) => ({
        ...f.properties,
        position: f.geometry.coordinates,
        ...riskById[f.properties.id],
        labels: data.labels[f.properties.id],
      }));
  }, [data]);

  // Re-plan whenever the budget changes (debounced).
  useEffect(() => {
    if (!buildings.length) return;
    if (budget === 0) return setPlan(null);
    const t = setTimeout(() => planUpgrades(buildings, budget).then(setPlan), 200);
    return () => clearTimeout(t);
  }, [budget, buildings]);

  const shown = useMemo(() => {
    if (!plan) return buildings;
    const after = Object.fromEntries(plan.buildings.map((b) => [b.id, b]));
    return buildings.map((b) => ({ ...b, ...after[b.id] }));
  }, [plan, buildings]);

  const before = counts(buildings);
  const after = plan ? plan.after : before;

  const layers = [
    new PathLayer({
      id: 'track',
      data: data?.track?.length ? [{ path: data.track.map((p) => [p.lon, p.lat]) }] : [],
      getPath: (d) => d.path,
      getColor: [180, 200, 255, 200],
      getWidth: 4,
      widthUnits: 'pixels',
    }),
    new ScatterplotLayer({
      id: 'track-points',
      data: data?.track || [],
      getPosition: (p) => [p.lon, p.lat],
      getRadius: 6,
      radiusUnits: 'pixels',
      getFillColor: [180, 200, 255, 255],
    }),
    new ScatterplotLayer({
      id: 'buildings',
      data: shown,
      getPosition: (b) => b.position,
      getRadius: 5,
      radiusUnits: 'pixels',
      getFillColor: (b) => [...BAND_COLOURS[b.band], 220],
      stroked: true,
      getLineColor: (b) => (b.upgraded ? [255, 255, 255, 255] : [0, 0, 0, 0]),
      lineWidthUnits: 'pixels',
      getLineWidth: 2,
      pickable: true,
      onClick: ({ object }) => setSelected(object),
      updateTriggers: { getFillColor: [plan], getLineColor: [plan] },
    }),
  ];

  async function makePlan() {
    setPlanBusy(true);
    try {
      const summary = {
        buildings_scored: buildings.length,
        before,
        after,
        upgraded: plan?.upgraded || [],
        upgrade_assumption: 'An upgraded roof (tie-downs, strapping, repairs) halves roof vulnerability in this model.',
        validation: data.validation,
      };
      const r = await resiliencePlan(AREA_NAME, summary);
      setPlanText(r.markdown);
    } catch (e) {
      setPlanText(`Could not reach the backend: ${e.message}`);
    } finally {
      setPlanBusy(false);
    }
  }

  function downloadPlan() {
    const blob = new Blob([planText], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'resilience-plan.md';
    a.click();
  }

  if (!data) return <div className="loading">Loading…</div>;

  const v = data.validation;

  return (
    <div className="app">
      <DeckGL initialViewState={INITIAL_VIEW} controller layers={layers}
        getTooltip={({ object }) => object?.band && `${object.id} · ${object.band} risk (${object.risk})`}>
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>

      <aside className="panel">
        <h1>Cyclone Prepare</h1>
        <p className="muted">Which homes to strengthen first, checked against Cyclone Winston (2016).</p>

        <section>
          <h2>Buildings at risk</h2>
          <div className="counts">
            {['high', 'medium', 'low'].map((b) => (
              <div key={b} className={`count ${b}`}>
                <span className="n">{after[b]}</span>
                <span className="label">{b}</span>
                {plan && after[b] !== before[b] && <span className="delta">was {before[b]}</span>}
              </div>
            ))}
          </div>
          <p className="muted small">{buildings.length} buildings scored · modelled, approximate</p>
        </section>

        <section>
          <h2>Upgrade planner</h2>
          <label className="small">Strengthen the {budget} highest-risk homes</label>
          <input type="range" min="0" max={Math.min(200, buildings.length)} value={budget}
            onChange={(e) => setBudget(+e.target.value)} />
          {plan?.local && <p className="muted small">Backend offline — using local calculation.</p>}
        </section>

        <section>
          <h2>Validation against Winston</h2>
          {v ? (
            <>
              {v.mock && <p className="warn small">Mock numbers — replace with real validation.</p>}
              <p><strong>{Math.round(v.model_recall_severe * 100)}%</strong> of severely damaged buildings were flagged high-risk
                (exposure only: {Math.round(v.baseline_recall_severe * 100)}%).</p>
              <p className="muted small">{v.note} Test set: {v.n_test} buildings.</p>
            </>
          ) : <p className="muted">No validation.json yet.</p>}
        </section>

        <section>
          <h2>Resilience plan</h2>
          <button onClick={makePlan} disabled={planBusy}>{planBusy ? 'Writing…' : 'Generate plan'}</button>
          {planText && (
            <>
              <pre className="plan">{planText}</pre>
              <button onClick={downloadPlan}>Download .md</button>
            </>
          )}
        </section>

        {selected && (
          <section className="selected">
            <h2>Building {selected.id} <button className="link" onClick={() => setSelected(null)}>close</button></h2>
            {selected.tile && <img src={`/${selected.tile}`} alt={`Aerial tile of ${selected.id}`} onError={(e) => (e.target.style.display = 'none')} />}
            <p className="small">Village: {selected.village || '—'}</p>
            <p className="small">Risk {selected.risk} ({selected.band}) = exposure {selected.exposure} × vulnerability {selected.vulnerability}</p>
            {selected.labels && (
              <p className="small">Roof: {selected.labels.roof_material}, {selected.labels.roof_shape}, {selected.labels.condition}
                {' '}(AI confidence {selected.labels.confidence})</p>
            )}
          </section>
        )}
      </aside>
    </div>
  );
}
