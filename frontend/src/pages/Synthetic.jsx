import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import client from "../api/client.js";
import LiveECGPanel from "../components/ecg/LiveECGPanel.jsx";
import ECGExplainChart from "../components/ecg/ECGExplainChart.jsx";
import Header from "../components/layout/Header.jsx";
import Sidebar from "../components/layout/Sidebar.jsx";

const CLASSES = ["", "N", "L", "R", "A", "V"];
const PLAYGROUND_CONDITIONS = ["Normal", "AFib", "PVC"];

function formatApiDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((x) => (typeof x === "string" ? x : x?.msg || JSON.stringify(x))).join(" ");
  }
  if (typeof detail === "object" && detail.message) return String(detail.message);
  try {
    return JSON.stringify(detail);
  } catch {
    return "Request failed.";
  }
}

function Spinner() {
  return (
    <span
      className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-violet-500/30 border-t-violet-300"
      aria-hidden
    />
  );
}

function ViewToggle({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-3 py-1 text-xs font-medium transition ${
        active
          ? "border-cyan-600/60 bg-cyan-950/30 text-cyan-200"
          : "border-slate-800/80 bg-clinical-850/40 text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

export default function Synthetic() {
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState("from-analysis"); // from-analysis | playground
  const [analysisId, setAnalysisId] = useState("");
  const [targetClass, setTargetClass] = useState("");
  const [numSamples, setNumSamples] = useState(360);
  const [noiseScale, setNoiseScale] = useState(0.08);
  const [diversitySeed, setDiversitySeed] = useState("");
  const [numBeats, setNumBeats] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [result, setResult] = useState(null);
  const [viewMode, setViewMode] = useState("synthetic");
  const [pgCondition, setPgCondition] = useState("Normal");
  const [pgNumSamples, setPgNumSamples] = useState(720);
  const [pgNoiseScale, setPgNoiseScale] = useState(0.08);
  const [pgSeed, setPgSeed] = useState("");
  const [pgBusy, setPgBusy] = useState(false);
  const [pgResult, setPgResult] = useState(null);

  useEffect(() => {
    const raw = searchParams.get("analysis_id");
    if (raw == null || String(raw).trim() === "") return;
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) {
      setAnalysisId(String(Math.trunc(n)));
      setTab("from-analysis");
    }
  }, [searchParams]);

  async function generate() {
    const id = Number(analysisId);
    if (!id) {
      setErrorMsg("Enter a valid analysis ID.");
      setMsg("");
      setResult(null);
      return;
    }
    setBusy(true);
    setMsg("");
    setErrorMsg("");
    setResult(null);
    try {
      const body = {
        target_class: targetClass || null,
        num_samples: Math.min(8000, Math.max(64, Number(numSamples) || 360)),
        noise_scale: Math.min(1, Math.max(0, Number(noiseScale))),
        diversity_seed: diversitySeed.trim() === "" ? null : Number(diversitySeed),
        num_beats: numBeats.trim() === "" ? null : Math.min(48, Math.max(1, Number(numBeats))),
      };
      const { data } = await client.post(`/ecg/generate-synthetic/${id}`, body);
      setResult(data);
      setMsg("Synthetic generation complete.");
      window.dispatchEvent(new Event("cardiosynth-data-changed"));
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErrorMsg(formatApiDetail(d) || "Synthetic generation failed.");
      setMsg("");
    } finally {
      setBusy(false);
    }
  }

  async function downloadCsv() {
    const sid = result?.run?.id;
    if (!sid) return;
    try {
      const res = await client.get(`/ecg/synthetic-file/${sid}`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `synthetic_run_${sid}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setErrorMsg("Could not download CSV.");
    }
  }

  async function generatePlayground() {
    setPgBusy(true);
    setMsg("");
    setErrorMsg("");
    setPgResult(null);
    try {
      const body = {
        condition: pgCondition,
        num_samples: Math.min(8000, Math.max(64, Number(pgNumSamples) || 720)),
        noise_scale: Math.min(1, Math.max(0, Number(pgNoiseScale))),
        diversity_seed: pgSeed.trim() === "" ? null : Number(pgSeed),
      };
      const { data } = await client.post("/synthetic/generate", body);
      setPgResult(data);
      setMsg("Playground generation complete.");
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErrorMsg(formatApiDetail(d) || "Playground generation failed.");
      setMsg("");
    } finally {
      setPgBusy(false);
    }
  }

  function downloadPlaygroundCsv() {
    const txt = pgResult?.csv_text;
    if (!txt) return;
    const blob = new Blob([txt], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `synthetic_playground_${String(pgResult?.condition || "ecg").replace(/\s+/g, "_")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const meta = result?.metadata;
  const backend = meta?.generation_backend;
  const quality = result?.quality;
  const refSeries = result?.preview_reference;
  const synSeries = result?.preview_synthetic;
  const hasSyntheticPreview = Array.isArray(synSeries) && synSeries.length > 0;
  const hasReferencePreview = Array.isArray(refSeries) && refSeries.length > 0;
  const zcmp = quality?.comparison_vs_reference_z;

  return (
    <div className="flex min-h-screen bg-clinical-950 bg-grid">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Header />
        <main className="flex flex-1 gap-4 overflow-hidden p-4">
          <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
            <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-2">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setTab("from-analysis")}
                  className={`rounded-lg border px-3 py-1 text-xs font-medium transition ${
                    tab === "from-analysis"
                      ? "border-cyan-600/60 bg-cyan-950/30 text-cyan-200"
                      : "border-slate-800/80 bg-clinical-850/40 text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                  }`}
                >
                  From analysis
                </button>
                <button
                  type="button"
                  onClick={() => setTab("playground")}
                  className={`rounded-lg border px-3 py-1 text-xs font-medium transition ${
                    tab === "playground"
                      ? "border-cyan-600/60 bg-cyan-950/30 text-cyan-200"
                      : "border-slate-800/80 bg-clinical-850/40 text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                  }`}
                >
                  Synthetic playground
                </button>
              </div>
            </div>

            {tab === "playground" && (
              <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
                <h2 className="font-display text-sm font-semibold text-white">Synthetic Data Playground</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Generate a condition-labeled ECG strip and run prediction + explainability on it.
                </p>

                <div className="mt-4 flex flex-wrap items-end gap-3">
                  <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    Condition
                    <select
                      value={pgCondition}
                      onChange={(e) => setPgCondition(e.target.value)}
                      className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                    >
                      {PLAYGROUND_CONDITIONS.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    Samples
                    <input
                      type="number"
                      min={64}
                      max={8000}
                      value={pgNumSamples}
                      onChange={(e) => setPgNumSamples(e.target.value)}
                      className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    Noise
                    <input
                      type="number"
                      step="0.02"
                      min={0}
                      max={1}
                      value={pgNoiseScale}
                      onChange={(e) => setPgNoiseScale(e.target.value)}
                      className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    Seed (optional)
                    <input
                      value={pgSeed}
                      onChange={(e) => setPgSeed(e.target.value)}
                      placeholder="rng"
                      className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={generatePlayground}
                    disabled={pgBusy}
                    className="rounded-lg border border-violet-700/60 bg-violet-950/40 px-3 py-2 text-xs font-semibold text-violet-200 transition hover:bg-violet-900/40 disabled:opacity-50"
                  >
                    {pgBusy ? "Generating…" : "Generate"}
                  </button>
                  <button
                    type="button"
                    onClick={downloadPlaygroundCsv}
                    disabled={!pgResult?.csv_text}
                    className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-slate-800/50 disabled:opacity-50"
                  >
                    Download CSV
                  </button>
                </div>

                {pgResult && (
                  <div className="mt-4 space-y-4">
                    <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                      <h3 className="text-sm font-semibold text-white">Playground waveform</h3>
                      <div className="mt-3">
                        <LiveECGPanel series={pgResult.waveform} />
                      </div>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                        <h3 className="text-sm font-semibold text-white">Prediction</h3>
                        <p className="mt-2 text-xs text-slate-400">
                          {pgResult.prediction?.predicted_class || pgResult.prediction?.label}{" "}
                          {typeof pgResult.prediction?.confidence === "number"
                            ? `(${(pgResult.prediction.confidence * 100).toFixed(1)}%)`
                            : ""}
                        </p>
                        {pgResult.explanation?.explanation_text && (
                          <p className="mt-3 text-xs text-slate-500">{pgResult.explanation.explanation_text}</p>
                        )}
                      </div>
                      <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                        <h3 className="text-sm font-semibold text-white">Explainability</h3>
                        <div className="mt-3">
                          <ECGExplainChart
                            waveform={pgResult.explanation?.window_waveform}
                            importance={pgResult.explanation?.importance_normalized}
                            regions={pgResult.explanation?.important_regions}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {tab === "from-analysis" && (
              <>
                <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
                  <h2 className="font-display text-sm font-semibold text-white">Synthetic generation</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Tries conditional DDPM when weights are present; otherwise uses a parametric single-lead synthesizer
                    (research only — not clinical).
                  </p>
                  <div className="mt-4 flex flex-wrap items-end gap-3">
                    <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Analysis ID
                      <input
                        value={analysisId}
                        onChange={(e) => setAnalysisId(e.target.value)}
                        placeholder="analysis_id"
                        className="w-28 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Target class
                      <select
                        value={targetClass}
                        onChange={(e) => setTargetClass(e.target.value)}
                        className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                      >
                        {CLASSES.map((c) => (
                          <option key={c || "auto"} value={c}>
                            {c === "" ? "From analysis" : c}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Samples
                      <input
                        type="number"
                        min={64}
                        max={8000}
                        value={numSamples}
                        onChange={(e) => setNumSamples(e.target.value)}
                        className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Noise (procedural)
                      <input
                        type="number"
                        step="0.02"
                        min={0}
                        max={1}
                        value={noiseScale}
                        onChange={(e) => setNoiseScale(e.target.value)}
                        className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Seed (optional)
                      <input
                        value={diversitySeed}
                        onChange={(e) => setDiversitySeed(e.target.value)}
                        placeholder="rng"
                        className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Beats (optional)
                      <input
                        value={numBeats}
                        onChange={(e) => setNumBeats(e.target.value)}
                        placeholder="auto"
                        className="w-20 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={generate}
                      disabled={busy}
                      className="flex items-center gap-2 rounded-lg border border-violet-700/60 bg-violet-950/40 px-3 py-2 text-xs font-semibold text-violet-200 transition hover:bg-violet-900/40 disabled:opacity-50"
                    >
                      {busy && <Spinner />}
                      {busy ? "Generating…" : "Generate"}
                    </button>
                  </div>
                  {msg && <p className="mt-3 text-xs text-cyan-200/90">{msg}</p>}
                </div>

                {!result && !errorMsg && (
                  <div className="rounded-xl border border-dashed border-slate-700 bg-clinical-850/30 p-6 text-center text-sm text-slate-500">
                    No waveform yet. Enter an analysis ID and click Generate to preview the synthetic ECG here.
                  </div>
                )}

                {errorMsg && (
                  <div className="rounded-xl border border-rose-900/50 bg-rose-950/25 p-4 text-xs text-rose-200/95">
                    {errorMsg}
                  </div>
                )}

                {result && (
                  <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-white">Generated waveform</h3>
                        <p className="mt-1 text-xs text-slate-500">
                          Preview from the API response (normalized for display).
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <ViewToggle active={viewMode === "synthetic"} onClick={() => setViewMode("synthetic")}>
                          Synthetic only
                        </ViewToggle>
                        <ViewToggle active={viewMode === "compare"} onClick={() => setViewMode("compare")}>
                          Reference vs synthetic
                        </ViewToggle>
                      </div>
                    </div>

                {!hasSyntheticPreview && (
                  <p className="mt-4 text-xs text-amber-200/85">
                    No preview samples were returned for the synthetic trace. CSV download may still be available.
                  </p>
                )}

                <div className="mt-4 space-y-4">
                  {viewMode === "synthetic" && hasSyntheticPreview && (
                    <LiveECGPanel series={synSeries} />
                  )}
                  {viewMode === "compare" && (
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div>
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                          Reference (normalized)
                        </p>
                        {hasReferencePreview ? (
                          <LiveECGPanel series={refSeries} />
                        ) : (
                          <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 text-xs text-slate-500">
                            Reference preview unavailable.
                          </div>
                        )}
                      </div>
                      <div>
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                          Synthetic output
                        </p>
                        {hasSyntheticPreview ? (
                          <LiveECGPanel series={synSeries} />
                        ) : (
                          <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 text-xs text-slate-500">
                            Synthetic preview unavailable.
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-6 border-t border-slate-800/80 pt-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Run metadata</h4>
                    <button
                      type="button"
                      onClick={downloadCsv}
                      disabled={!result?.run?.id}
                      className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-slate-800/50 disabled:opacity-50"
                    >
                      Download CSV
                    </button>
                  </div>
                  <dl className="mt-3 space-y-2 text-xs">
                    <div className="flex justify-between border-b border-slate-800/60 py-1.5">
                      <dt className="text-slate-500">Target class (condition)</dt>
                      <dd className="text-right text-slate-200">{meta?.condition_label ?? "—"}</dd>
                    </div>
                    <div className="flex justify-between border-b border-slate-800/60 py-1.5">
                      <dt className="text-slate-500">Generated samples</dt>
                      <dd className="text-right text-slate-200">
                        {meta?.output_samples ?? (hasSyntheticPreview ? synSeries.length : "—")}
                      </dd>
                    </div>
                    <div className="flex justify-between border-b border-slate-800/60 py-1.5">
                      <dt className="text-slate-500">Generation backend</dt>
                      <dd className="text-right font-mono text-[11px] text-slate-200">{backend ?? "—"}</dd>
                    </div>
                    {result?.run?.id != null && (
                      <div className="flex justify-between border-b border-slate-800/60 py-1.5">
                        <dt className="text-slate-500">Run ID</dt>
                        <dd className="text-right text-slate-200">#{result.run.id}</dd>
                      </div>
                    )}
                    {quality?.peak_to_peak != null && (
                      <div className="flex justify-between border-b border-slate-800/60 py-1.5">
                        <dt className="text-slate-500">Peak-to-peak (procedural)</dt>
                        <dd className="text-right text-slate-200">
                          {typeof quality.peak_to_peak === "number" ? quality.peak_to_peak.toFixed(4) : quality.peak_to_peak}
                        </dd>
                      </div>
                    )}
                    {zcmp && (
                      <>
                        <div className="flex justify-between border-b border-slate-800/60 py-1.5">
                          <dt className="text-slate-500">MSE vs reference (z-scored)</dt>
                          <dd className="text-right text-slate-200">
                            {zcmp.mse != null ? zcmp.mse.toFixed(4) : "—"}
                          </dd>
                        </div>
                        <div className="flex justify-between py-1.5">
                          <dt className="text-slate-500">Correlation vs reference</dt>
                          <dd className="text-right text-slate-200">
                            {zcmp.correlation != null ? zcmp.correlation.toFixed(4) : "—"}
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>
                </div>
              </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
