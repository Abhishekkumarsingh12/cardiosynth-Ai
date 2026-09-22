import { useEffect, useMemo, useRef, useState } from "react";

/** Visible samples in the scrolling “monitor” strip (capped by source length). */
const DEFAULT_WINDOW = 520;
/** Base samples advanced per tick at speed 1× */
const BASE_STEP = 2;
const TICK_MS = 48;

/**
 * Drives a sliding-window view over a 1-D ECG sample array for live monitor animation.
 * When live mode is off, callers should render the original full `sourceSeries`.
 */
export function useLiveECGSimulation(sourceSeries) {
  const src = Array.isArray(sourceSeries) ? sourceSeries : [];
  const len = src.length;
  const hasSignal = len > 0;

  const [liveEnabled, setLiveEnabled] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loop, setLoop] = useState(true);
  const [tick, setTick] = useState(0);

  const offsetRef = useRef(0);

  const windowSize = useMemo(() => {
    if (!len) return 0;
    return Math.min(DEFAULT_WINDOW, len);
  }, [len]);

  // Reset playhead when the underlying signal changes
  useEffect(() => {
    offsetRef.current = 0;
    setTick((t) => t + 1);
  }, [sourceSeries, len]);

  useEffect(() => {
    if (!liveEnabled) {
      setPlaying(false);
      offsetRef.current = 0;
    }
  }, [liveEnabled]);

  useEffect(() => {
    if (!liveEnabled || !playing || !hasSignal || windowSize === 0) return undefined;

    const id = setInterval(() => {
      const step = Math.max(1, Math.round(BASE_STEP * speed));
      const maxStart = Math.max(0, len - windowSize);

      if (loop) {
        offsetRef.current = (offsetRef.current + step) % len;
      } else {
        const next = offsetRef.current + step;
        if (next >= maxStart) {
          offsetRef.current = maxStart;
          setPlaying(false);
        } else {
          offsetRef.current = next;
        }
      }
      setTick((t) => t + 1);
    }, TICK_MS);

    return () => clearInterval(id);
  }, [liveEnabled, playing, hasSignal, len, windowSize, loop, speed]);

  const displaySeries = useMemo(() => {
    if (!hasSignal) return [];
    if (!liveEnabled) return src;

    const W = windowSize;
    const maxStart = Math.max(0, len - W);
    const out = new Array(W);

    if (loop) {
      const o = Math.floor(offsetRef.current) % len;
      for (let i = 0; i < W; i += 1) {
        out[i] = src[(o + i) % len];
      }
    } else {
      const start = Math.min(Math.floor(offsetRef.current), maxStart);
      for (let i = 0; i < W; i += 1) {
        out[i] = src[start + i];
      }
    }
    return out;
  }, [src, len, hasSignal, liveEnabled, windowSize, loop, tick]);

  return {
    displaySeries,
    liveEnabled,
    setLiveEnabled,
    playing,
    setPlaying,
    speed,
    setSpeed,
    loop,
    setLoop,
    hasSignal,
  };
}
