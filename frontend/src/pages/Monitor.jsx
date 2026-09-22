import { useMemo, useState } from "react";
import client from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import LiveECGPanel from "../components/ecg/LiveECGPanel.jsx";
import Header from "../components/layout/Header.jsx";
import Sidebar from "../components/layout/Sidebar.jsx";
import { useLiveECGStream } from "../hooks/useLiveECGStream.js";

const DEMO_CONDITIONS = ["N", "A", "V", "L", "R"];

export default function Monitor() {
  const { token } = useAuth();
  const [mode, setMode] = useState("analysis"); // analysis | synthetic_demo
  const [analysisId, setAnalysisId] = useState("");
  const [condition, setCondition] = useState("N");
  const [enabled, setEnabled] = useState(false);
  const [windowSize, setWindowSize] = useState(520);
  const [chunkSize, setChunkSize] = useState(24);
  const [tickMs, setTickMs] = useState(40);
  const [loop, setLoop] = useState(true);
  const [hint, setHint] = useState("");

  const analysisIdNum = useMemo(() => {
    const n = Number(analysisId);
    return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
  }, [analysisId]);

  const { status, error, meta, series } = useLiveECGStream({
    token,
    analysisId: analysisIdNum,
    mode,
    condition,
    windowSize,
    chunkSize,
    tickMs,
    loop,
    enabled,
  });

  async function tryLoadLatestAnalysisId() {
    setHint("");
    try {
      const { data } = await client.get("/ecg/history");
      const first = Array.isArray(data) ? data[0] : null;
      if (first?.analysis_id) {
        setAnalysisId(String(first.analysis_id));
        setHint(`Loaded latest analysis: #${first.analysis_id}`);
      } else {
        setHint("No history yet. Upload a CSV first.");
      }
    } catch {
      setHint("Could not load history.");
    }
  }

  const ready =
    mode === "synthetic_demo" ? true : analysisIdNum != null;

  return (
    <div className="flex min-h-screen bg-clinical-950 bg-grid">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Header />
        <main className="flex flex-1 gap-4 overflow-hidden p-4">
          <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
            <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="font-display text-sm font-semibold text-white">Real-time ECG Monitor</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Streams small batches over WebSocket and renders a scrolling monitor strip.
                  </p>
                </div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Status:{" "}
                  <span className="text-slate-200">
                    {status}
                  </span>
                </span>
              </div>

              <div className="mt-4 flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Source
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                  >
                    <option value="analysis">From analysis upload</option>
                    <option value="synthetic_demo">Demo synthetic stream</option>
                  </select>
                </label>

                {mode === "analysis" ? (
                  <>
                    <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Analysis ID
                      <input
                        value={analysisId}
                        onChange={(e) => setAnalysisId(e.target.value)}
                        placeholder="e.g. 1"
                        className="w-28 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={tryLoadLatestAnalysisId}
                      className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-slate-800/50"
                    >
                      Use latest
                    </button>
                  </>
                ) : (
                  <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    Condition
                    <select
                      value={condition}
                      onChange={(e) => setCondition(e.target.value)}
                      className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                    >
                      {DEMO_CONDITIONS.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Window
                  <input
                    type="number"
                    min={120}
                    max={1600}
                    value={windowSize}
                    onChange={(e) => setWindowSize(Number(e.target.value))}
                    className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                  />
                </label>
                <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Chunk
                  <input
                    type="number"
                    min={4}
                    max={128}
                    value={chunkSize}
                    onChange={(e) => setChunkSize(Number(e.target.value))}
                    className="w-20 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                  />
                </label>
                <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Tick (ms)
                  <input
                    type="number"
                    min={10}
                    max={200}
                    value={tickMs}
                    onChange={(e) => setTickMs(Number(e.target.value))}
                    className="w-20 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                  />
                </label>
                <label className="inline-flex cursor-pointer items-center gap-1.5 text-[10px] font-medium text-slate-400">
                  <input
                    type="checkbox"
                    className="rounded border-slate-600 bg-clinical-850 text-cyan-500 focus:ring-cyan-500/40"
                    checked={loop}
                    onChange={(e) => setLoop(e.target.checked)}
                  />
                  Loop
                </label>

                <button
                  type="button"
                  onClick={() => setEnabled((v) => !v)}
                  disabled={!ready}
                  className="rounded-lg border border-cyan-700/60 bg-cyan-950/30 px-3 py-2 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-900/30 disabled:opacity-50"
                >
                  {enabled ? "Stop stream" : "Start stream"}
                </button>
              </div>

              {hint && <p className="mt-3 text-xs text-slate-400">{hint}</p>}
              {error && <p className="mt-3 text-xs text-amber-200/90">{error}</p>}
              {meta && (
                <p className="mt-3 text-[10px] text-slate-500">
                  Source: <span className="text-slate-300">{meta.source}</span> · fs:{" "}
                  <span className="text-slate-300">{meta.sampling_rate_hz}</span> · length:{" "}
                  <span className="text-slate-300">{meta.signal_length}</span>
                </p>
              )}
            </div>

            <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <h3 className="text-sm font-semibold text-white">Live waveform</h3>
              <p className="mt-1 text-xs text-slate-500">
                This panel renders the incoming stream in a moving strip (sliding window).
              </p>
              <div className="mt-3">
                <LiveECGPanel series={series} />
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

