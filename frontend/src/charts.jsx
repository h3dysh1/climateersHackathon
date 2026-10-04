// Charts for the summary page (light background). All numbers come from the backend's
// /compare-measures answer and /hotspots; nothing here is estimated.
// Each chart: thin marks, one y-axis, legend + direct labels, hover tooltips (SVG <title>),
// and a "show the numbers" table so nothing depends on colour alone.
import { MAX_LEVEL, fmt, fmtLevel, optionOf, titleCase, areaLabel } from "./options";

const INK = "#0B1620";
const GRID = "#DDE2E5";
const KEPT = "#1B6E3F";
const INSIDE = "#C9402A";
const DEEP = "#6E1710";
const WATERLINE = "#1D5E99";

function niceMax(v) {
  if (v <= 0) return 10;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function Axes({ W, H, pad, maxY, x, y, level }) {
  const ticks = [0, maxY / 2, maxY];
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke={t === 0 ? "#9AA4AB" : GRID} />
          <text x={pad.l - 8} y={y(t) + 4} textAnchor="end">{fmt(t)}</text>
        </g>
      ))}
      {Array.from({ length: MAX_LEVEL + 1 }, (_, lv) => (
        <text key={lv} x={x(lv)} y={H - pad.b + 18} textAnchor="middle">{lv} m</text>
      ))}
      <text x={(pad.l + W - pad.r) / 2} y={H - 4} textAnchor="middle">How far the river rises above normal</text>
      {level != null && (
        <g>
          <line x1={x(level)} x2={x(level)} y1={pad.t - 6} y2={y(0)} stroke={WATERLINE} strokeWidth="2" strokeDasharray="5 4" />
          <text x={x(level)} y={pad.t - 10} textAnchor="middle" className="lab" style={{ fill: WATERLINE }}>
            {fmtLevel(level)} m (gauge)
          </text>
        </g>
      )}
    </g>
  );
}

function Table({ head, rows }) {
  return (
    <details className="fig-table">
      <summary>Show the numbers</summary>
      <table>
        <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
      </table>
    </details>
  );
}

/* 1. People with water inside as the river rises: do nothing vs with the options on */
export function FloodCurveChart({ base, withOptions, level }) {
  if (!base?.length) return null;
  const W = 560, H = 290, pad = { l: 56, r: 120, t: 26, b: 40 };
  const maxY = niceMax(Math.max(...base.map((p) => p.people_water_inside)));
  const x = (lv) => pad.l + (lv / MAX_LEVEL) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - v / maxY) * (H - pad.t - pad.b);
  const line = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.level_m).toFixed(1)},${y(p.people_water_inside).toFixed(1)}`).join(" ");
  const hasWith = withOptions?.length === base.length;
  const band = hasWith
    ? `${line(base)} ${withOptions.slice().reverse().map((p) => `L${x(p.level_m).toFixed(1)},${y(p.people_water_inside).toFixed(1)}`).join(" ")} Z`
    : null;
  const lastB = base[base.length - 1];
  const lastW = hasWith ? withOptions[withOptions.length - 1] : null;
  const stepW = (x(base[1]?.level_m ?? 1) - x(base[0].level_m)) || 20;

  return (
    <figure className="fig">
      <div className="fig-t">People with water inside, as the river rises</div>
      <div className="fig-s">The gap between the two lines is the people the options keep dry at each flood size.</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Line chart of people with water inside at each river rise, with and without the options">
        <Axes W={W} H={H} pad={pad} maxY={maxY} x={x} y={y} level={level} />
        {band && <path d={band} fill={KEPT} opacity=".14" />}
        <path d={line(base)} fill="none" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
        {hasWith && <path d={line(withOptions)} fill="none" stroke={KEPT} strokeWidth="2.5" strokeLinejoin="round" />}
        <text x={x(lastB.level_m) + 8} y={y(lastB.people_water_inside) + 4} className="lab">Do nothing</text>
        {hasWith && <text x={x(lastW.level_m) + 8} y={y(lastW.people_water_inside) + 18} className="lab" style={{ fill: KEPT }}>With the options</text>}
        {base.map((p, i) => (
          <rect key={p.level_m} className="hov" x={x(p.level_m) - stepW / 2} y={pad.t} width={stepW} height={H - pad.t - pad.b} fill="transparent">
            <title>
              {`${fmtLevel(p.level_m)} m: ${fmt(p.people_water_inside)} people with water inside if we do nothing` +
                (hasWith ? `, ${fmt(withOptions[i].people_water_inside)} with the options (${fmt(Math.max(0, p.people_water_inside - withOptions[i].people_water_inside))} kept dry)` : "")}
            </title>
          </rect>
        ))}
      </svg>
      <div className="fig-legend">
        <span><i style={{ background: INK }} />Do nothing</span>
        {hasWith && <span><i style={{ background: KEPT }} />With the options switched on</span>}
        {hasWith && <span><i className="blk" style={{ background: KEPT, opacity: 0.25 }} />Kept dry</span>}
      </div>
      <Table
        head={["River rise", "Do nothing", ...(hasWith ? ["With options", "Kept dry"] : [])]}
        rows={base.map((p, i) => [
          `${fmtLevel(p.level_m)} m`,
          fmt(p.people_water_inside),
          ...(hasWith ? [fmt(withOptions[i].people_water_inside), fmt(Math.max(0, p.people_water_inside - withOptions[i].people_water_inside))] : []),
        ])}
      />
    </figure>
  );
}

/* 2. People kept dry by each option on its own, across river levels */
export function ProtectedLinesChart({ base, options, level }) {
  if (!base?.length) return null;
  const series = options
    .filter((o) => o.curve?.length === base.length)
    .map((o) => ({
      key: o.key,
      name: optionOf(o.key).name,
      color: optionOf(o.key).color,
      pts: o.curve.map((p, i) => ({ lv: p.level_m, v: Math.max(0, base[i].people_water_inside - p.people_water_inside) })),
    }));
  if (!series.length) return null;
  const W = 560, H = 290, pad = { l: 56, r: 150, t: 26, b: 40 };
  const maxY = niceMax(Math.max(1, ...series.flatMap((s) => s.pts.map((p) => p.v))));
  const x = (lv) => pad.l + (lv / MAX_LEVEL) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - v / maxY) * (H - pad.t - pad.b);

  // direct labels at the right end, nudged apart so they never overlap
  const ends = series.map((s) => ({ ...s, ly: y(s.pts[s.pts.length - 1].v) })).sort((a, b) => a.ly - b.ly);
  for (let i = 1; i < ends.length; i++) if (ends[i].ly - ends[i - 1].ly < 16) ends[i].ly = ends[i - 1].ly + 16;

  return (
    <figure className="fig">
      <div className="fig-t">People kept dry by each option on its own</div>
      <div className="fig-s">Raised homes help most near the flood they were raised for. Dredging and vegetation matter more as floods get bigger.</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Line chart of people kept dry by each option at each river rise">
        <Axes W={W} H={H} pad={pad} maxY={maxY} x={x} y={y} level={level} />
        {series.map((s) => (
          <g key={s.key}>
            <polyline fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" points={s.pts.map((p) => `${x(p.lv)},${y(p.v)}`).join(" ")} />
            {s.pts.map((p) => (
              <circle key={p.lv} className="hov" cx={x(p.lv)} cy={y(p.v)} r="9" fill="transparent">
                <title>{`${s.name} at ${fmtLevel(p.lv)} m: ${fmt(p.v)} people kept dry`}</title>
              </circle>
            ))}
          </g>
        ))}
        {ends.map((s) => (
          <text key={s.key} x={W - pad.r + 8} y={s.ly + 4} className="lab" style={{ fill: s.color }}>{s.name}</text>
        ))}
      </svg>
      <div className="fig-legend">
        {series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.name}</span>)}
      </div>
      <Table
        head={["River rise", ...series.map((s) => s.name)]}
        rows={base.map((p, i) => [`${fmtLevel(p.level_m)} m`, ...series.map((s) => fmt(s.pts[i].v))])}
      />
    </figure>
  );
}

/* 3. Each option alone at the gauge level (horizontal bars, labelled) */
export function AloneBars({ options, total, level }) {
  if (!options?.length) return null;
  const rows = options.map((o) => ({ key: o.key, name: optionOf(o.key).name, color: optionOf(o.key).color, v: o.at_design_level.people_protected }));
  const max = Math.max(1, ...rows.map((r) => r.v));
  const W = 560, rowH = 40, padL = 170, padR = 70, H = rows.length * rowH + 8;
  return (
    <figure className="fig">
      <div className="fig-t">Each option on its own, at {fmtLevel(level)} m</div>
      <div className="fig-s">People who would no longer have water inside, out of {fmt(total)}.</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Bar chart of people kept dry by each option at ${fmtLevel(level)} metres`}>
        {rows.map((r, i) => {
          const w = ((W - padL - padR) * r.v) / max;
          const yy = i * rowH + 6;
          return (
            <g key={r.key} className="hov">
              <title>{`${r.name}: ${fmt(r.v)} people kept dry`}</title>
              <text x={0} y={yy + 18} className="lab">{r.name}</text>
              <rect x={padL} y={yy + 4} width={W - padL - padR} height={20} fill="#EEF1F3" />
              <rect x={padL} y={yy + 4} width={Math.max(2, w)} height={20} fill={r.color} />
              <text x={padL + w + 8} y={yy + 19} className="lab" style={{ fontFamily: "var(--font-display)", fontSize: 16 }}>{fmt(r.v)}</text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

/* 4. All together: a waterfall from "do nothing", adding each option in turn */
export function WaterfallChart({ base, layering }) {
  if (!layering?.steps?.length || !base) return null;
  const rows = [{ label: "Do nothing", still: base, added: 0, key: null }, ...layering.steps.map((s) => ({
    label: `+ ${optionOf(s.added).name}`, still: s.people_still_water_inside, added: s.people_added_protection, key: s.added,
  }))];
  const W = 560, rowH = 42, padL = 178, padR = 104, H = rows.length * rowH + 10;
  const sx = (v) => ((W - padL - padR) * v) / base;
  const ranked = layering.orders_compared ?? [];
  const best = ranked[0];
  const worst = ranked[ranked.length - 1];
  const orderMatters = best && worst && best.people_protected !== worst.people_protected;

  return (
    <figure className="fig">
      <div className="fig-t">All together, one option at a time</div>
      <div className="fig-s">Town-wide options first, then raise the homes that are still flooding.</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Waterfall of people still with water inside as each option is added">
        <defs>
          <pattern id="earlier" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="5" height="5" fill="#EEF1F3" /><line x1="0" y1="0" x2="0" y2="5" stroke="#C9D0D5" strokeWidth="1.2" />
          </pattern>
        </defs>
        {rows.map((r, i) => {
          const yy = i * rowH + 6;
          const color = r.key ? optionOf(r.key).color : null;
          return (
            <g key={i} className="hov">
              <title>{r.key ? `${r.label}: ${fmt(r.added)} more kept dry, ${fmt(r.still)} still with water inside` : `Do nothing: ${fmt(r.still)} with water inside`}</title>
              <text x={0} y={yy + 19} className="lab">{r.label}</text>
              <rect x={padL} y={yy + 5} width={W - padL - padR} height={20} fill="url(#earlier)" />
              <rect x={padL} y={yy + 5} width={sx(r.still)} height={20} fill={INSIDE} />
              {r.key && <rect x={padL + sx(r.still) + 2} y={yy + 5} width={Math.max(2, sx(r.added) - 2)} height={20} fill={color} />}
              {r.key && <text x={W - padR + 10} y={yy + 19} style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}>−{fmt(r.added)}</text>}
              <text x={W} y={yy + 20} textAnchor="end" className="lab" style={{ fontFamily: "var(--font-display)", fontSize: 17 }}>{fmt(r.still)}</text>
            </g>
          );
        })}
      </svg>
      <div className="fig-legend">
        <span><i className="blk" style={{ background: INSIDE }} />Still water inside</span>
        <span><i className="blk" style={{ background: "#8F98A0" }} />Colour: kept dry by that step</span>
        <span><i className="blk" style={{ background: "repeating-linear-gradient(45deg,#EEF1F3 0 2px,#C9D0D5 2px 3px)" }} />Kept dry by earlier steps</span>
      </div>
      <p className="fig-note">
        {orderMatters
          ? `Order matters here: ${best.order.map((k) => optionOf(k).short).join(", then ")} keeps ${fmt(best.people_protected)} dry; the worst order keeps ${fmt(worst.people_protected)}.`
          : rows.length > 2 ? "At this flood level, the order makes no difference." : ""}
      </p>
    </figure>
  );
}

/* 5. Most affected areas: people with water inside, split by deep water */
export function AreasChart({ areas }) {
  if (!areas?.length) return null;
  const max = Math.max(1, ...areas.map((a) => a.people_water_inside));
  const W = 560, rowH = 38, padL = 200, padR = 60, H = areas.length * rowH + 8;
  const sx = (v) => ((W - padL - padR) * v) / max;
  return (
    <figure className="fig">
      <div className="fig-t">Most affected areas</div>
      <div className="fig-s">People with water inside their homes, and how many of them are in water 1 m or deeper.</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Bar chart of the most affected areas">
        {areas.map((a, i) => {
          const yy = i * rowH + 4;
          const deep = Math.min(a.people_deep_water, a.people_water_inside);
          return (
            <g key={a.name} className="hov">
              <title>{`${titleCase(areaLabel(a))}: ${fmt(a.people_water_inside)} with water inside, ${fmt(deep)} in deep water`}</title>
              <text x={0} y={yy + 18} className="lab">{titleCase(areaLabel(a)).slice(0, 30)}</text>
              <rect x={padL} y={yy + 5} width={Math.max(2, sx(deep))} height={18} fill={DEEP} />
              <rect x={padL + sx(deep) + (deep ? 2 : 0)} y={yy + 5} width={Math.max(0, sx(a.people_water_inside - deep) - (deep ? 2 : 0))} height={18} fill={INSIDE} />
              <text x={padL + sx(a.people_water_inside) + 8} y={yy + 19} className="lab" style={{ fontFamily: "var(--font-display)", fontSize: 16 }}>{fmt(a.people_water_inside)}</text>
            </g>
          );
        })}
      </svg>
      <div className="fig-legend">
        <span><i className="blk" style={{ background: DEEP }} />In deep water (1 m or more)</span>
        <span><i className="blk" style={{ background: INSIDE }} />Water inside, under 1 m</span>
      </div>
      <Table
        head={["Area", "Water inside", "Deep water"]}
        rows={areas.map((a) => [titleCase(areaLabel(a)), fmt(a.people_water_inside), fmt(a.people_deep_water)])}
      />
    </figure>
  );
}
