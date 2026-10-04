// Shared settings and helpers for the planner, the summary page and the charts.

export const MAX_LEVEL = 6;
export const STEP = 0.25;
export const DEEP_WATER_M = 1.0;

// Map colours (MapLibre needs plain values). Same as index.css.
export const COLORS = {
  dry: "#56656F",
  reaching: "#E0892B",
  inside: "#C9402A",
  deep: "#6E1710",
  water: "#5E9BD0",
  river: "#5AA6E8",
  road: "#3B5162",
  roadCut: "#C9402A",
  highlight: "#8C8CF0",
  ink: "#10222F",
  land: "#16242F",
};

// The three options. `key` is the backend's name for each one.
//  color   = fill on the light summary charts (checked for colour-blind separation)
//  colorDk = fill on the dark planner panel
//  text    = text tint on the dark panel
export const OPTIONS = [
  {
    key: "channel_clearing_m",
    name: "Dredge the river",
    short: "dredging the river",
    color: "#BF8740",
    colorDk: "#BF8740",
    text: "#D6A273",
    presets: { low: 0.1, medium: 0.25, high: 0.5 }, // replaced by /measures when the backend is up
    stop: (v) => `${v} m`,
    effect: (v) => `−${v} m`,
    describe: (v) => `Every flood ${v} m lower. The benefit fades as silt returns.`,
  },
  {
    key: "raise_homes",
    name: "Raise homes",
    short: "raising homes",
    color: "#4646A8",
    colorDk: "#7474D8",
    text: "#A9A9F5",
    presets: { low: 50, medium: 100, high: 250 },
    stop: (v) => `${v} homes`,
    effect: (v) => `${v} homes`,
    describe: (v, area) =>
      `Lift up to ${v} homes by 1 m, ${area ? `in ${titleCase(areaLabel(area))}` : "anywhere in town (pick an area to target it)"}.`,
  },
  {
    key: "nature_based",
    name: "Riverbank vegetation",
    short: "riverbank vegetation",
    color: "#1B6E3F",
    colorDk: "#2E8F54",
    text: "#7FCB95",
    presets: { low: 2, medium: 5, high: 10 },
    stop: (v) => `${v}%`,
    effect: (v) => `−${v}%`,
    describe: (v) => `Floods ${v}% lower, less in very big floods. Also cuts erosion and silt.`,
  },
];
export const SIZES = [
  ["low", "Low"],
  ["medium", "Med"],
  ["high", "High"],
];
// "All together" adds options in this order: town-wide first, then raise the homes still flooding.
export const ORDER = ["channel_clearing_m", "nature_based", "raise_homes"];
export const optionOf = (key) => OPTIONS.find((o) => o.key === key);

export const fmt = (n) => Math.round(n).toLocaleString("en-US");
export const fmtLevel = (m) => (Math.round(m * 2) === m * 2 ? m.toFixed(1) : m.toFixed(2));
export const areaLabel = (a) => (a.name.startsWith("near ") ? `around ${a.name.slice(5)}` : a.name);
export const titleCase = (s) => s.charAt(0).toUpperCase() + s.slice(1);
export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Plain-language phrase for how many options are switched on.
export const optionsPhrase = (n) =>
  n === 3 ? "all three options" : n === 2 ? "two options" : n === 1 ? "one option" : "no options";
