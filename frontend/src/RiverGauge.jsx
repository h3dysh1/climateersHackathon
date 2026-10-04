// The river staff gauge: the level control, on the right edge of the map beside the panel.
// A native range input sits invisibly on top of the drawing, so dragging, arrow keys and
// screen readers all work without custom pointer code.
import { MAX_LEVEL, STEP, fmt, fmtLevel } from "./options";

export default function RiverGauge({ level, onChange, people }) {
  const frac = level / MAX_LEVEL;
  const set = (m) => onChange(Math.min(MAX_LEVEL, Math.max(0, Math.round(m / STEP) * STEP)));

  return (
    <div className="gauge">
      <div className="gauge-cap">River gauge</div>
      <div className="gauge-wrap">
        <div className="gauge-staff" aria-hidden="true">
          <div className="gauge-scale">
            <svg className="gauge-marks" viewBox="0 0 60 600" preserveAspectRatio="none">
              <defs>
                {/* E-pattern of a real staff gauge: an E, then a mirrored E, every 10 cm */}
                <pattern id="estaff" width="60" height="20" patternUnits="userSpaceOnUse">
                  <rect x="2" y="0" width="5" height="5" fill="#10222F" />
                  <rect x="2" y="0" width="26" height="1" fill="#10222F" />
                  <rect x="2" y="2" width="26" height="1" fill="#10222F" />
                  <rect x="2" y="4" width="26" height="1" fill="#10222F" />
                  <rect x="53" y="10" width="5" height="5" fill="#10222F" />
                  <rect x="32" y="10" width="26" height="1" fill="#10222F" />
                  <rect x="32" y="12" width="26" height="1" fill="#10222F" />
                  <rect x="32" y="14" width="26" height="1" fill="#10222F" />
                </pattern>
              </defs>
              <rect x="0" y="0" width="60" height="600" fill="url(#estaff)" />
            </svg>
            {Array.from({ length: MAX_LEVEL + 1 }, (_, m) => (
              <span key={m} className={`gauge-num${m >= 5 ? " high" : ""}`} style={{ bottom: `${(m / MAX_LEVEL) * 100}%` }}>
                {m}
              </span>
            ))}
            <div className="gauge-water" style={{ height: `calc(${frac * 100}% + 14px)` }}>
              <svg className="gauge-wave" viewBox="0 0 200 8" preserveAspectRatio="none">
                <path d="M0,5 Q12.5,0 25,5 T50,5 T75,5 T100,5 T125,5 T150,5 T175,5 T200,5 V8 H0 Z" fill="rgba(43,116,184,.42)" />
              </svg>
            </div>
          </div>
        </div>

        <input
          className="gauge-input"
          type="range"
          min={0}
          max={MAX_LEVEL}
          step={STEP}
          value={level}
          onChange={(e) => set(Number(e.target.value))}
          aria-label="River rise above normal level, in metres"
          aria-valuetext={`${fmtLevel(level)} metres above normal`}
        />

        {/* Readout riding on the waterline, pointing into the map */}
        <div className="gauge-tab" style={{ bottom: `calc(14px + ${frac} * (100% - 28px))` }} aria-hidden="true">
          <div className="gauge-level"><b className="num">{level.toFixed(2)}</b><span>m</span></div>
          <div className="gauge-sub">river rise above normal</div>
          {people != null && (
            <div className="gauge-hit">
              <svg width="14" height="14" viewBox="0 0 14 14"><path d="M7 1.5 L12.5 6 V12.5 H1.5 V6 Z" fill="#C9402A" stroke="#fff" strokeWidth="1.2" /></svg>
              <span>Water inside homes of <b className="num">{fmt(people)}</b></span>
            </div>
          )}
        </div>
      </div>
      <div className="gauge-btns">
        <button className="gauge-btn" type="button" onClick={() => set(level + STEP)} aria-label={`Raise the river ${STEP} m`}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 9.5 L7 5 L11 9.5" fill="none" stroke="currentColor" strokeWidth="2" /></svg>
        </button>
        <button className="gauge-btn" type="button" onClick={() => set(level - STEP)} aria-label={`Lower the river ${STEP} m`}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 5 L7 9.5 L11 5" fill="none" stroke="currentColor" strokeWidth="2" /></svg>
        </button>
      </div>
    </div>
  );
}
