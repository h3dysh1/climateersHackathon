import React, { useEffect, useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { Map } from 'react-map-gl/maplibre';
import { BAND_COLOURS, loadData, protectionBand, restorationPlan, runScenario } from './api.js';

// Free dark basemap (attribution: © OpenStreetMap contributors, © CARTO).
const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const AREA_NAME = 'Lautoka'; // pilot city
const INITIAL_VIEW = { longitude: 177.44, latitude: -17.62, zoom: 11.5, pitch: 0, bearing: 0 };

export default function App() {
  const [data, setData] = useState(null);
  const [restoreIds, setRestoreIds] = useState([]);
  const [scenario, setScenario] = useState(null);
  const [selected, setSelected] = useState(null);
  const [planText, setPlanText] = useState('');
  const [planBusy, setPlanBusy] = useState(false);

  useEffect(() => {
    loadData().then(setData);
  }, []);

  const segments = useMemo(() => (data ? data.segments.features.map((f) => ({ ...f.properties, path: f.geometry.coordinates })) : []), [data]);
  const ranked = useMemo(() => [...segments].filter((s) => s.restorable_ha > 0).sort((a, b) => b.priority - a.priority), [segments]);

  useEffect(() => {
    if (!segments.length) return;
    runScenario(segments, restoreIds).then(setScenario);
  }, [restoreIds, segments]);

  const after = useMemo(() => Object.fromEntries((scenario?.segments || []).map((s) => [s.id, s])), [scenario]);

  const toggle = (id) => setRestoreIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  const restoreTop = (n) => setRestoreIds(ranked.slice(0, n).map((s) => s.id));

  const layers = [
    new GeoJsonLayer({
      id: 'mangroves',
      data: data?.mangroves,
      filled: true,
      getFillColor: [60, 190, 140, 110],
      stroked: false,
    }),
    new ScatterplotLayer({
      id: 'buildings',
      data: data?.buildings.features || [],
      getPosition: (f) => f.geometry.coordinates,
      getRadius: 3,
      radiusUnits: 'pixels',
      getFillColor: (f) => {
        const band = after[f.properties.segment_id]?.band;
        return band ? [...BAND_COLOURS[band], 160] : [140, 150, 165, 120];
      },
      updateTriggers: { getFillColor: [scenario] },
    }),
    new PathLayer({
      id: 'coast',
      data: segments,
      getPath: (s) => s.path,
      getColor: (s) => {
        const a = after[s.id];
        if (a?.restored) return [120, 230, 255, 255];
        return [...BAND_COLOURS[a?.band || protectionBand(s.existing_width_m)], 255];
      },
      getWidth: (s) => (restoreIds.includes(s.id) ? 9 : 6),
      widthUnits: 'pixels',
      capRounded: true,
      pickable: true,
      onClick: ({ object }) => {
        setSelected(object);
        if (object.restorable_ha > 0) toggle(object.id);
      },
      updateTriggers: { getColor: [scenario], getWidth: [restoreIds] },
    }),
    new PathLayer({
      id: 'track',
      data: data?.track?.length ? [{ path: data.track.map((p) => [p.lon, p.lat]) }] : [],
      getPath: (d) => d.path,
      getColor: [180, 200, 255, 140],
      getWidth: 3,
      widthUnits: 'pixels',
    }),
  ];

  async function makePlan() {
    setPlanBusy(true);
    try {
      const top = ranked.slice(0, 5).map(({ id, restorable_ha, surge_people, priority, wave_reduction_now, wave_reduction_restored }) =>
        ({ id, restorable_ha, surge_people, priority, wave_reduction_now, wave_reduction_restored }));
      const summary = {
        restored: scenario.restored,
        hectares: scenario.hectares,
        people_better_protected: scenario.people_better_protected,
        surge_exposed_people_by_protection_before: scenario.before,
        surge_exposed_people_by_protection_after: scenario.after,
        top_ranked_sites: top,
        model: 'Wave height reduction 13% per 100 m of mangroves (low end of 13-66% field range), capped at 66%; surge reduction 0.1 m per km.',
        validation: data.validation,
      };
      const r = await restorationPlan(AREA_NAME, summary);
      setPlanText(r.markdown);
    } catch (e) {
      setPlanText(`Could not reach the backend: ${e.message}`);
    } finally {
      setPlanBusy(false);
    }
  }

  function downloadPlan() {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([planText], { type: 'text/markdown' }));
    a.download = 'restoration-plan.md';
    a.click();
  }

  if (!data) return <div className="loading">Loading…</div>;
  const v = data.validation;
  const s = scenario;

  return (
    <div className="app">
      <DeckGL initialViewState={INITIAL_VIEW} controller layers={layers}
        getTooltip={({ object }) => object?.restorable_width_m !== undefined &&
          `${object.id}: ${object.existing_width_m} m mangroves now, +${object.restorable_width_m} m restorable · ${object.surge_people} people behind`}>
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>

      <aside className="panel">
        <h1>Restore to Protect</h1>
        <p className="muted">Where restoring mangroves protects the most people from cyclone waves in {AREA_NAME}.</p>

        <section>
          <h2>People in surge-exposed homes</h2>
          {s && (
            <div className="counts">
              {['exposed', 'partial', 'strong'].map((b) => (
                <div key={b} className={`count ${b}`}>
                  <span className="n">{s.after[b]}</span>
                  <span className="label">{b === 'strong' ? 'well buffered' : b === 'partial' ? 'partly buffered' : 'no buffer'}</span>
                  {s.after[b] !== s.before[b] && <span className="delta">was {s.before[b]}</span>}
                </div>
              ))}
            </div>
          )}
          <p className="muted small">Protection = mangrove width in front of the coast. Modelled, approximate.</p>
        </section>

        <section>
          <h2>Restoration scenario</h2>
          <p className="small">Click coast segments on the map, or:</p>
          <div className="row">
            <button onClick={() => restoreTop(3)}>Top 3 sites</button>
            <button onClick={() => restoreTop(10)}>Top 10</button>
            <button className="ghost" onClick={() => setRestoreIds([])}>Clear</button>
          </div>
          {s && (
            <p><strong>{s.hectares} ha</strong> restored on {s.restored.length} segments · <strong>{s.people_better_protected}</strong> people move to better protection.</p>
          )}
          {s?.local && <p className="muted small">Backend offline — using local calculation.</p>}
          <ol className="ranked small">
            {ranked.slice(0, 5).map((r) => (
              <li key={r.id} className={restoreIds.includes(r.id) ? 'on' : ''} onClick={() => toggle(r.id)}>
                {r.id}: {r.restorable_ha} ha, {r.surge_people} people behind
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2>Evidence from Cyclone Winston</h2>
          {v ? (
            <>
              {v.mock && <p className="warn small">Mock numbers — replace with real validation.</p>}
              <p>Severe damage near the coast: <strong>{Math.round(v.severe_rate_with_mangroves * 100)}%</strong> of buildings behind mangroves vs <strong>{Math.round(v.severe_rate_without * 100)}%</strong> without.</p>
              <p className="muted small">{v.note}</p>
            </>
          ) : <p className="muted">No validation.json yet.</p>}
        </section>

        <section>
          <h2>Restoration plan</h2>
          <button onClick={makePlan} disabled={planBusy || !s}>{planBusy ? 'Writing…' : 'Generate plan'}</button>
          {planText && (
            <>
              <pre className="plan">{planText}</pre>
              <button onClick={downloadPlan}>Download .md</button>
            </>
          )}
        </section>

        {selected && (
          <section>
            <h2>Segment {selected.id} <button className="link" onClick={() => setSelected(null)}>close</button></h2>
            <p className="small">Mangroves now: {selected.existing_width_m} m wide (cuts waves ~{Math.round(selected.wave_reduction_now * 100)}%)</p>
            <p className="small">Restorable: +{selected.restorable_width_m} m, {selected.restorable_ha} ha (would cut waves ~{Math.round(selected.wave_reduction_restored * 100)}%)</p>
            <p className="small">Behind it: {selected.buildings_behind} buildings, {selected.people_behind} people ({selected.surge_people} in surge zone)</p>
            <p className="muted small">Storm-surge reduction is small (~{selected.surge_reduction_restored_m} m); the main benefit is waves and erosion.</p>
          </section>
        )}
      </aside>
    </div>
  );
}
