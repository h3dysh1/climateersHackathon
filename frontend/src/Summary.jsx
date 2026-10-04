// Summary page: the current scenario (gauge level + options switched on) with charts generated
// from the backend, plus the written plan. Light body, dark hero band.
import "./summary.css";
import { OPTIONS, fmt, fmtLevel, optionOf, optionsPhrase, titleCase, areaLabel } from "./options";
import { FloodCurveChart, ProtectedLinesChart, AloneBars, WaterfallChart, AreasChart } from "./charts";
import Markdown from "./markdown";

export default function Summary({
  level, choice, presets, area, counts, hotspots, backend,
  result, resultState,
  plan, planState, onWritePlan, onCopyPlan, onDownloadPlan, copied, planOutdated,
}) {
  const on = OPTIONS.filter((o) => choice[o.key].on);
  const total = result?.baseline?.people_water_inside ?? counts?.people ?? 0;
  const lay = result?.layering;
  const last = lay?.steps?.[lay.steps.length - 1];
  const kept = last ? last.people_protected_so_far : 0;
  const still = last ? last.people_still_water_inside : total;
  const pct = total ? Math.round((kept / total) * 100) : 0;
  const lv = fmtLevel(level);
  const ready = resultState === "ready" && result;

  return (
    <div className="summary" role="dialog" aria-modal="true" aria-labelledby="sum-title">
      <div className="s-bar"><div className="s-bar-in">
        <b>Waterline · Nadi, Fiji</b>
        <a href="#/">Places</a>
        <button type="button" onClick={() => window.print()}>Print or save as PDF</button>
        <a className="pri" href="#/nadi">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M9 2.5 L4.5 7 L9 11.5" fill="none" stroke="currentColor" strokeWidth="2" /></svg>
          Back to the planner
        </a>
      </div></div>

      <div className="s-hero"><div className="s-hero-in">
        <div className="s-kick">
          <span className="s-tag">Summary</span>
          Nadi, Fiji (test city) · river {lv} m above normal · {on.length ? on.map((o) => `${o.name} ${sizeLabel(choice[o.key].size)}`).join(", ") : "no options switched on"}
        </div>
        {last && total > 0 ? (
          <h1 id="sum-title">
            Together, {optionsPhrase(on.length)} keep water out of the homes of <em>{fmt(kept)} people</em>. {fmt(still)} still flood.
          </h1>
        ) : (
          <h1 id="sum-title">
            At {lv} m, water gets inside the homes of {fmt(total)} {total === 1 ? "person" : "people"}.
          </h1>
        )}
        <p className="s-sub">
          This page sums up who the river reaches at {lv} m, what each option does on its own and together, and what is
          left to solve. Every number comes from the flood model; change the gauge or the options in the planner and it updates.
        </p>
        {last && total > 0 && (
          <div className="s-verdict">
            <div className="s-vbig">
              <span className="s-vnum">{fmt(kept)}</span>
              <span className="s-vof">of {fmt(total)} people would keep<br />water out of their homes</span>
            </div>
            <div>
              <div className="s-vpct">{pct}%</div>
              <div className="s-vbar" aria-hidden="true">
                {lay.steps.map((s) => (
                  <span key={s.added} style={{ width: `${(s.people_added_protection / total) * 100}%`, background: optionOf(s.added).color }} />
                ))}
              </div>
              <div className="s-vscale"><span><b>{fmt(kept)}</b> kept dry</span><span><b>{fmt(still)}</b> still have water inside</span></div>
            </div>
          </div>
        )}
      </div></div>

      <div className="s-wrap">
        {backend !== "online" && <div className="s-err">The charts need the backend. Start it with uvicorn and reload.</div>}
        {backend === "online" && resultState === "loading" && (
          <div className="s-loading"><span className="spin" />Working out the charts for every river level…</div>
        )}
        {resultState === "error" && <div className="s-err">The charts could not be worked out. Check the backend terminal for the error.</div>}

        <section className="s-sec">
          <div className="s-sec-h"><span className="s-sec-n">01</span><h2>The flood at {lv} m</h2></div>
          {counts && (
            <div className="s-stats">
              <div className="s-stat"><b className="inside">{fmt(counts.people)}</b><span>people with water inside their homes</span></div>
              <div className="s-stat"><b>{fmt(counts.facilities)}</b><span>{counts.facilities === 1 ? "facility" : "facilities"} flooded (clinics, schools and others)</span></div>
              <div className="s-stat"><b>{fmt(counts.roads)}</b><span>road sections cut by 30 cm of water</span></div>
            </div>
          )}
          {ready && (
            <div className="s-two">
              <FloodCurveChart base={result.baseline.curve} withOptions={last?.curve} level={level} />
              <AreasChart areas={hotspots} />
            </div>
          )}
          {!ready && hotspots?.length > 0 && <div className="s-two"><AreasChart areas={hotspots} /></div>}
        </section>

        {on.length > 0 && ready && (
          <section className="s-sec">
            <div className="s-sec-h">
              <span className="s-sec-n">02</span><h2>What the options do</h2>
              <p className="s-sec-sub">Each option against doing nothing, then all of them together.</p>
            </div>
            <div className="s-two">
              <AloneBars options={result.options} total={total} level={level} />
              <WaterfallChart base={total} layering={lay} />
            </div>
            <div className="s-two">
              <ProtectedLinesChart base={result.baseline.curve} options={result.options} level={level} />
              <div className="fig-aside">
                <b>How to read these</b>
                <p>Each line is one option on its own, compared with doing nothing, at every river level from 0 to 6 m. The dashed line is the level set on the gauge.</p>
                <p>Where a line drops back towards zero, that option has stopped helping at that flood size.</p>
              </div>
            </div>
          </section>
        )}

        <section className="s-sec">
          <div className="s-sec-h"><span className="s-sec-n">03</span><h2>Settings tested</h2></div>
          <div className="s-settings">
            {OPTIONS.map((o) => {
              const c = choice[o.key];
              const v = presets[o.key][c.size];
              return (
                <div key={o.key} className={`s-set${c.on ? "" : " off"}`}>
                  <i className="sw" style={{ background: o.color, marginTop: 5 }} />
                  <div>
                    <b>{o.name} · {c.on ? sizeLabel(c.size) : "off"}</b>
                    <span className="d">{o.describe(v, o.key === "raise_homes" ? area : null)}</span>
                  </div>
                  <span className="v" style={{ color: o.color }}>{c.on ? o.effect(v) : "Off"}</span>
                </div>
              );
            })}
          </div>
          {area && <p className="fig-note">Raised homes are targeted at {titleCase(areaLabel(area))}.</p>}
        </section>

        <section className="s-sec">
          <div className="s-sec-h">
            <span className="s-sec-n">04</span><h2>Write the plan</h2>
            <p className="s-sec-sub">Turns this scenario into a one-page plan for the council and community leaders.</p>
          </div>
          <div style={{ marginTop: 16 }}>
            <button className="btn" type="button" onClick={onWritePlan} disabled={backend !== "online" || planState === "loading"}>
              {planState === "loading" ? "Writing the plan…" : plan ? "Write it again for these settings" : "Write the plan"}
            </button>
          </div>
          {planState === "error" && <div className="s-err">The plan could not be written. Check the backend terminal for the error.</div>}
          {plan && (
            <div className="plan" aria-live="polite">
              <div className="plan-meta">
                <span>
                  {plan.provider === "gemini" && !plan.fallback
                    ? `Written by Gemini (${plan.model}) from the numbers above`
                    : "Written by the built-in writer from the numbers above"}
                  {plan.fallback && plan.error ? `. Gemini was unavailable: ${plan.error}` : ""}
                </span>
                <span className="plan-actions">
                  <button className="link" type="button" onClick={onCopyPlan}>{copied ? "Copied" : "Copy"}</button>
                  <button className="link" type="button" onClick={onDownloadPlan}>Download</button>
                </span>
              </div>
              {planOutdated && <div className="s-err">You've changed the settings since this plan was written. Write it again to update it.</div>}
              <Markdown text={plan.markdown} />
            </div>
          )}
        </section>

        <div className="s-care">
          <div><b>Read this with care</b>A planning screen, not a flood forecast: it shows which ground the river reaches as it rises (height above nearest drainage), not how water flows. Option effects are what-ifs, for comparing choices.</div>
          <div><b>Where the numbers come from</b>Ground height from FABDEM, rivers and roads from OpenStreetMap, buildings from Overture Maps, and where people live from WorldPop.</div>
        </div>
        <div className="s-end">
          <a className="btn" href="#/nadi">Back to the planner</a>
          <a className="btn out" href="#/">Choose another place</a>
        </div>
      </div>
    </div>
  );
}

const sizeLabel = (s) => ({ low: "Low", medium: "Med", high: "High" })[s] ?? s;
