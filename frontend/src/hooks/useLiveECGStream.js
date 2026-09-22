import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Maintains a sliding-window buffer fed by the backend WebSocket stream.
 *
 * Backend: ws://<host>/api/ecg/live?token=...&analysis_id=...&chunk_size=...&tick_ms=...
 */
export function useLiveECGStream({
  token,
  analysisId,
  mode = "analysis",
  condition = "",
  windowSize = 520,
  chunkSize = 24,
  tickMs = 40,
  loop = true,
  enabled = false,
}) {
  const [status, setStatus] = useState("idle"); // idle | connecting | live | error | closed
  const [error, setError] = useState("");
  const [meta, setMeta] = useState(null);
  const [waveform, setWaveform] = useState([]);
  const lastChunkAtRef = useRef(0);
  const simPhaseRef = useRef(0);
  const wsRef = useRef(null);

  const canConnect = enabled && (mode !== "analysis" || !!analysisId);

  const url = useMemo(() => {
    if (!canConnect) return "";
    // IMPORTANT: The monitor expects this exact backend path.
    // Default local dev: ws://127.0.0.1:8000/ws/ecg-stream/{analysis_id}
    const base = import.meta?.env?.VITE_BACKEND_WS_URL || "ws://127.0.0.1:8000";
    if (mode === "analysis") {
      const u = new URL(`${base.replace(/^http/, "ws")}/ws/ecg-stream/${analysisId}`);
      // token is optional on this compat route; keep it if available for secured deployments.
      if (token) u.searchParams.set("token", token);
      return u.toString();
    }

    // Keep existing streaming route for non-analysis modes (demo).
    const loc = window.location;
    const proto = loc.protocol === "https:" ? "wss:" : "ws:";
    const u = new URL(`${proto}//${loc.host}/api/ecg/live`);
    if (token) u.searchParams.set("token", token);
    u.searchParams.set("mode", mode);
    if (condition) u.searchParams.set("condition", condition);
    u.searchParams.set("chunk_size", String(chunkSize));
    u.searchParams.set("tick_ms", String(tickMs));
    u.searchParams.set("loop", loop ? "true" : "false");
    return u.toString();
  }, [canConnect, token, mode, condition, analysisId, chunkSize, tickMs, loop]);

  useEffect(() => {
    if (!canConnect || !url) {
      setStatus("idle");
      setError("");
      setMeta(null);
      setWaveform([]);
      lastChunkAtRef.current = 0;
      return undefined;
    }

    setStatus("connecting");
    setError("");
    setMeta(null);
    setWaveform([]);
    lastChunkAtRef.current = 0;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] open:", url);
      setStatus("live");
    };
    ws.onerror = () => {
      console.log("[WS] error");
      setStatus("error");
      setError("WebSocket connection error.");
    };
    ws.onclose = (ev) => {
      console.log("[WS] close:", { code: ev.code, reason: ev.reason, wasClean: ev.wasClean });
      setStatus("closed");
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        console.log("Received:", msg);
        if (msg?.type === "meta") {
          setMeta(msg);
          return;
        }
        if (msg?.type === "error") {
          setStatus("error");
          setError(msg.message || "Stream error.");
          return;
        }
        // Accept both backend payload styles:
        // - new contract: { chunk: [...] }
        // - legacy: { type: "chunk", samples: [...] }
        const chunk = Array.isArray(msg?.chunk) ? msg.chunk : Array.isArray(msg?.samples) ? msg.samples : null;
        if (chunk) {
          const cleaned = chunk
            .map((v) => Number(v))
            .filter((v) => Number.isFinite(v));
          if (cleaned.length === 0) return;
          lastChunkAtRef.current = Date.now();
          const W = Math.max(16, Number(windowSize) || 520);
          setWaveform((prev) => {
            const updated = prev.concat(cleaned);
            return updated.length > W ? updated.slice(updated.length - W) : updated;
          });
        }
      } catch {
        // ignore
      }
    };

    return () => {
      try {
        ws.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    };
  }, [canConnect, url, windowSize]);

  // Fallback: if backend sends nothing (or is down), simulate a moving ECG-like waveform.
  useEffect(() => {
    if (!enabled) return undefined;

    const intervalMs = Math.max(10, Number(tickMs) || 40);
    const W = Math.max(16, Number(windowSize) || 520);
    const cs = Math.max(4, Number(chunkSize) || 24);
    const silenceMs = 900;

    const id = setInterval(() => {
      const last = lastChunkAtRef.current;
      const tooQuiet = !last || Date.now() - last > silenceMs;
      if (!tooQuiet) return;

      // Simple ECG-ish: sine + a narrow periodic "QRS-like" spike + mild noise
      const out = [];
      let phase = simPhaseRef.current || 0;
      for (let k = 0; k < cs; k += 1) {
        phase += 0.12;
        const base = Math.sin(phase) * 0.12;
        const beat = (phase % (Math.PI * 2)) / (Math.PI * 2); // 0..1
        const qrs = Math.exp(-Math.pow((beat - 0.18) / 0.03, 2)) * 1.0;
        const noise = (Math.random() - 0.5) * 0.02;
        out.push(base + qrs + noise);
      }
      simPhaseRef.current = phase;

      setWaveform((prev) => {
        const updated = prev.concat(out);
        return updated.length > W ? updated.slice(updated.length - W) : updated;
      });
    }, intervalMs);

    return () => clearInterval(id);
  }, [enabled, tickMs, windowSize, chunkSize]);

  return { status, error, meta, series: waveform };
}

