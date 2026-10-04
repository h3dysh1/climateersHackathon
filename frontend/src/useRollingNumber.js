import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "./options";

// Rolls a displayed number towards `target` (about half a second, easing out).
// Jumps straight there when the user prefers reduced motion.
export default function useRollingNumber(target, duration = 520) {
  const [shown, setShown] = useState(target ?? 0);
  const current = useRef(target ?? 0);
  const raf = useRef(0);

  useEffect(() => {
    if (target == null) return undefined;
    cancelAnimationFrame(raf.current);
    const from = current.current;
    if (prefersReducedMotion() || from === target) {
      current.current = target;
      setShown(target);
      return undefined;
    }
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / duration);
      const v = Math.round(from + (target - from) * (1 - Math.pow(1 - p, 3)));
      current.current = v;
      setShown(v);
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);

  return shown;
}
