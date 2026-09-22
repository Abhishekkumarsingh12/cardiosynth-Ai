import { useEffect, useMemo, useState } from "react";
import client from "../api/client.js";
import ECGChart from "../components/ecg/ECGChart.jsx";
import LiveECGPanel from "../components/ecg/LiveECGPanel.jsx";
import ECGExplainChart from "../components/ecg/ECGExplainChart.jsx";
import Header from "../components/layout/Header.jsx";
import Sidebar from "../components/layout/Sidebar.jsx";
import { riskLevelTextClass } from "../utils/clinicalDisplay.js";

function TabButton({ active, onClick, children }) {
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

function Badge({ tone = "slate", children }) {
  const map = {
    emerald: "border-emerald-800/60 bg-emerald-950/30 text-emerald-200",
    amber: "border-amber-900/60 bg-amber-950/30 text-amber-200",
    rose: "border-rose-900/60 bg-rose-950/30 text-rose-200",
    slate: "border-slate-800/80 bg-clinical-850/40 text-slate-300",
  };
  return <span className={`rounded-full border px-2 py-0.5 text-[10px] ${map[tone] || map.slate}`}>{children}</span>;
}

export default function ECGStudio() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [analysisId, setAnalysisId] = useState(null);
  const [studio, setStudio] = useState(null);
  const [studioRisk, setStudioRisk] = useState(null);
  const [explain, setExplain] = useState(null);
  const [explainBusy, setExplainBusy] = useState(false);
  const [tab, setTab] = useState("raw");

  const quality = studio?.signal_quality;
  const qualityTone =
    quality?.label === "good" ? "emerald" : quality?.label === "ok" ? "amber" : quality?.label ? "rose" : "slate";

  const rawSeries = useMemo(() => studio?.raw_series || [], [studio]);
  const processedSeries = useMemo(() => studio?.processed_series || [], [studio]);
  const segments = useMemo(() => studio?.beat_segments || [], [studio]);

  useEffect(() => {
    if (studio && tab === "segments" && segments.length === 0) {
      setTab("result");
    }
  }, [studio, tab, segments.length]);

  useEffect(() => {
    if (!analysisId || (tab !== "result" && tab !== "explain")) {
      if (tab !== "result" && tab !== "explain") setExplain(null);
      return;
    }
    let cancelled = false;
    setExplainBusy(true);
    client
      .get(`/ecg/explain/${analysisId}`)
      .then(({ data }) => {
        if (!cancelled) setExplain(data);
      })
      .catch(() => {
        if (!cancelled) setExplain(null);
      })
      .finally(() => {
        if (!cancelled) setExplainBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, tab]);

  async function onUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setMsg("");
      setStudio(null);
      setStudioRisk(null);
      setExplain(null);
      setAnalysisId(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await client.post("/ecg/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setAnalysisId(data.analysis_id);
      if (data?.file_type && data.file_type !== "csv") {
        setMsg(`Uploaded ${data.file_type.toUpperCase()}. ECG Studio beat segmentation requires CSV raw signal. View details in Reports.`);
        window.dispatchEvent(new Event("cardiosynth-data-changed"));
        return;
      }
      setMsg("Upload complete. Running ECG Studio analysis…");
      const { data: res } = await client.post(`/ecg/analyze/${data.analysis_id}`);
      setStudio(res.studio);
      setStudioRisk(res.risk || null);
      setTab("raw");
      setMsg("Analysis complete.");
      window.dispatchEvent(new Event("cardiosynth-data-changed"));
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "ECG Studio analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  const summary = studio?.summary;

  return (
    <div className="flex min-h-screen bg-clinical-950 bg-grid">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Header />
        <main className="flex flex-1 gap-4 overflow-hidden p-4">
          <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
            <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="font-display text-sm font-semibold text-white">ECG Studio</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Upload CSV → parse ECG column → bandpass → beat windows (187) → TensorFlow classifier.
                  </p>
                </div>
                <label className="cursor-pointer rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-slate-800/50">
                  {busy ? "Processing…" : "Upload file"}
                  <input type="file" accept=".csv,.pdf,image/png,image/jpeg,image/jpg" className="hidden" onChange={onUpload} disabled={busy} />
                </label>
              </div>
              {msg && <p className="mt-3 text-xs text-cyan-200/90">{msg}</p>}
            </div>

            {studio && (
              <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="slate">column: {studio.selected_signal_column}</Badge>
                    <Badge tone="slate">samples: {studio.n_samples}</Badge>
                    <Badge tone={qualityTone}>quality: {quality?.label || "—"}</Badge>
                    <Badge tone="slate">beats: {studio.beats_analyzed}</Badge>
                    <Badge tone="slate">fs used: {studio.sampling_rate_hz_used}</Badge>
                    {studio.sampling_rate_hz_inferred && <Badge tone="slate">fs inferred: {studio.sampling_rate_hz_inferred.toFixed(2)}</Badge>}
                  </div>
                  {analysisId && <span className="text-[10px] text-slate-600">analysis #{analysisId}</span>}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <TabButton active={tab === "raw"} onClick={() => setTab("raw")}>
                    Raw Signal
                  </TabButton>
                  <TabButton active={tab === "processed"} onClick={() => setTab("processed")}>
                    Processed Signal
                  </TabButton>
                  <TabButton active={tab === "segments"} onClick={() => setTab("segments")}>
                    Beat Segments
                  </TabButton>
                  <TabButton active={tab === "result"} onClick={() => setTab("result")}>
                    Classification Result
                  </TabButton>
                  <TabButton active={tab === "notes"} onClick={() => setTab("notes")}>
                    Clinical Notes
                  </TabButton>
                  <TabButton active={tab === "explain"} onClick={() => setTab("explain")}>
                    Interpretability
                  </TabButton>
                </div>

                <div className="mt-4">
                  {tab === "raw" && <LiveECGPanel series={rawSeries} />}
                  {tab === "processed" && <LiveECGPanel series={processedSeries} />}
                  {tab === "segments" && (
                    <div className="grid gap-3 md:grid-cols-2">
                      {segments.length === 0 && (
                        <div className="rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 p-4 text-sm text-slate-500">
                          No segments extracted.
                        </div>
                      )}
                      {segments.map((seg, idx) => (
                        <div key={idx} className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-3">
                          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                            Beat #{idx + 1}
                          </p>
                          <ECGChart series={seg} />
                        </div>
                      ))}
                    </div>
                  )}
                  {tab === "result" && (
                    <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="rounded-lg border border-slate-800/80 bg-clinical-900/30 p-3">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Predicted class</p>
                          <p className="mt-1 font-display text-2xl font-semibold text-white">
                            {summary?.predicted_class ?? "—"}
                          </p>
                        </div>
                        <div className="rounded-lg border border-slate-800/80 bg-clinical-900/30 p-3">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Mean confidence</p>
                          <p className="mt-1 font-display text-2xl font-semibold text-white">
                            {summary ? `${(summary.confidence_mean * 100).toFixed(1)}%` : "—"}
                          </p>
                        </div>
                      </div>
                      {studioRisk?.risk_level && (
                        <p className="mt-3 text-xs text-slate-400">
                          Risk:{" "}
                          <span className={`font-semibold ${riskLevelTextClass(studioRisk.risk_level)}`}>
                            {String(studioRisk.risk_level).toUpperCase()}
                            {studioRisk.risk_score != null ? ` (${studioRisk.risk_score})` : ""}
                            {studioRisk.risk_level === "high" ? " ⚠" : ""}
                          </span>
                        </p>
                      )}
                      {studioRisk?.recommendation && (
                        <p className="mt-2 text-xs text-slate-500">{studioRisk.recommendation}</p>
                      )}
                      <p className="mt-3 text-xs text-slate-400">
                        Beats analyzed: <span className="text-slate-200">{studio.beats_analyzed}</span>
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Research use only — not a medical diagnosis.
                      </p>
                    </div>
                  )}
                  {tab === "explain" && (
                    <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                      <p className="text-sm font-semibold text-white">Model interpretability</p>
                      <p className="mt-1 text-xs text-slate-500">
                        Gradient saliency on the 187-sample classifier window. {explainBusy ? "Loading…" : ""}
                      </p>
                      {explain?.explanation_summary && (
                        <p className="mt-2 text-xs text-slate-400">{explain.explanation_summary}</p>
                      )}
                      {!explainBusy && !explain && (
                        <p className="mt-2 text-xs text-amber-200/80">Unavailable — ensure the classifier is loaded.</p>
                      )}
                      <div className="mt-3">
                        <ECGExplainChart
                          waveform={explain?.window_waveform}
                          importance={explain?.importance_normalized}
                          regions={explain?.important_regions}
                        />
                      </div>
                    </div>
                  )}
                  {tab === "notes" && (
                    <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4 text-sm text-slate-300">
                      {studio.clinical_notes}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

