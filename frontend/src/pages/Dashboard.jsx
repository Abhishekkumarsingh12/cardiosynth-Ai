import { useCallback, useEffect, useState } from "react";
import client from "../api/client.js";
import LiveECGPanel from "../components/ecg/LiveECGPanel.jsx";
import Header from "../components/layout/Header.jsx";
import Sidebar from "../components/layout/Sidebar.jsx";
import { formatAllProbabilities, riskLevelTextClass } from "../utils/clinicalDisplay.js";

/** FastAPI HTTPException detail: string, object, or validation error array */
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

const UNRELIABLE_LABELS = new Set([
  "model_unavailable",
  "classifier_not_trained",
  "inference_error",
  "unknown",
  "insufficient_data",
]);

function Spinner() {
  return (
    <span
      className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-cyan-500/30 border-t-cyan-400"
      aria-hidden
    />
  );
}

function StatCard({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-slate-800/80 bg-gradient-to-br from-clinical-850 to-clinical-900 p-4 shadow-lg shadow-black/20">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold text-white">{value}</p>
      {hint && <p className="mt-2 text-xs text-clinical-muted">{hint}</p>}
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [recent, setRecent] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [busy, setBusy] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [uploadPreview, setUploadPreview] = useState(null); // { url, kind, name }
  const [uploadDetected, setUploadDetected] = useState(null); // { file_type, content_type }
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [confirmUploadDelete, setConfirmUploadDelete] = useState(null);
  const [deleteUploadBusy, setDeleteUploadBusy] = useState(false);
  const [recentFeedback, setRecentFeedback] = useState({ kind: "", text: "" });

  const refresh = useCallback(async () => {
    const [s, r] = await Promise.all([
      client.get("/dashboard/summary"),
      client.get("/dashboard/recent-analyses"),
    ]);
    setSummary(s.data);
    setRecent(r.data);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  useEffect(() => {
    const handler = () => {
      refresh().catch(() => {});
    };
    window.addEventListener("cardiosynth-data-changed", handler);
    const onVis = () => {
      if (document.visibilityState === "visible") handler();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("cardiosynth-data-changed", handler);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [refresh]);

  async function onUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setUploadMsg("");
    setUploadDetected(null);
    if (uploadPreview?.url) URL.revokeObjectURL(uploadPreview.url);
    const kind = file.type?.startsWith("image/") ? "image" : file.type === "application/pdf" ? "pdf" : "csv";
    setUploadPreview({ url: URL.createObjectURL(file), kind, name: file.name });
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await client.post("/ecg/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadMsg(data.message || "Uploaded.");
      if (data?.file_type || data?.content_type) setUploadDetected({ file_type: data.file_type, content_type: data.content_type });
      const { data: detail } = await client.get(`/ecg/analysis/${data.analysis_id}`);
      setAnalysis(detail);
      await refresh();
      window.dispatchEvent(new Event("cardiosynth-data-changed"));
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      const msg = formatApiDetail(d) || "Upload failed.";
      setUploadMsg(msg);
    } finally {
      setBusy(false);
    }
  }

  async function loadAnalysis(id) {
    setBusy(true);
    try {
      const { data } = await client.get(`/ecg/analysis/${id}`);
      setAnalysis(data);
    } finally {
      setBusy(false);
    }
  }

  async function deleteUploadConfirmed() {
    const row = confirmUploadDelete;
    if (!row) return;
    setDeleteUploadBusy(true);
    setRecentFeedback({ kind: "", text: "" });
    try {
      await client.delete(`/uploads/${row.upload_id}`);
      setConfirmUploadDelete(null);
      if (analysis?.analysis_id === row.analysis_id) setAnalysis(null);
      await refresh();
      window.dispatchEvent(new Event("cardiosynth-data-changed"));
      setRecentFeedback({ kind: "ok", text: "Upload and linked analyses removed." });
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setRecentFeedback({ kind: "err", text: formatApiDetail(d) || "Delete failed." });
    } finally {
      setDeleteUploadBusy(false);
    }
  }

  async function generateSynthetic() {
    if (!analysis) return;
    setBusy(true);
    try {
      await client.post(`/ecg/generate-synthetic/${analysis.analysis_id}`, {
        num_samples: 360,
        noise_scale: 0.08,
      });
      const { data } = await client.get(`/ecg/analysis/${analysis.analysis_id}`);
      setAnalysis(data);
      window.dispatchEvent(new Event("cardiosynth-data-changed"));
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      alert(formatApiDetail(d) || "Synthetic generation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function submitManual(e) {
    e.preventDefault();
    if (!analysis) return;
    const fd = new FormData(e.currentTarget);
    const payload = {
      heart_rate: fd.get("heart_rate") ? Number(fd.get("heart_rate")) : null,
      pr_interval: fd.get("pr_interval") ? Number(fd.get("pr_interval")) : null,
      qrs_duration: fd.get("qrs_duration") ? Number(fd.get("qrs_duration")) : null,
      qtc: fd.get("qtc") ? Number(fd.get("qtc")) : null,
      symptoms: String(fd.get("symptoms") || "").trim() || null,
    };
    setBusy(true);
    setUploadMsg("");
    try {
      await client.post(`/ecg/manual/${analysis.analysis_id}`, payload);
      const { data: detail } = await client.get(`/ecg/analysis/${analysis.analysis_id}`);
      setAnalysis(detail);
      window.dispatchEvent(new Event("cardiosynth-data-changed"));
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setUploadMsg(formatApiDetail(d) || "Manual input submit failed.");
    } finally {
      setBusy(false);
    }
  }

  async function sendChat(e) {
    e.preventDefault();
    const text = chatInput.trim();
    if (!text) return;
    setChatInput("");
    setChatMessages((m) => [...m, { role: "user", text }]);
    try {
      const ctx =
        analysis?.prediction_result != null
          ? {
              last_prediction: analysis.prediction_result,
              preprocess_metadata: analysis.preprocess_metadata,
            }
          : {};
      const { data } = await client.post("/assistant/chat", {
        message: text,
        context: ctx,
        analysis_id: analysis?.analysis_id ?? null,
        session_id: analysis?.analysis_id != null ? `dash-${analysis.analysis_id}` : "dash-default",
        include_history: true,
      });
      setChatMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: data.reply,
          summary: data.summary,
          condition_explanation: data.condition_explanation,
          risk_explanation: data.risk_explanation,
          recommendation: data.recommendation,
        },
      ]);
    } catch {
      setChatMessages((m) => [...m, { role: "assistant", text: "Could not reach assistant." }]);
    }
  }

  const pred = analysis?.prediction_result;
  const ingestion = analysis?.preprocess_metadata?.ingestion || {};
  const reliability = analysis?.preprocess_metadata?.reliability || pred || {};
  const reportFields = analysis?.preprocess_metadata?.report_text?.fields || null;
  const lastLabel = summary?.last_prediction_label;
  const lastRhythmHint =
    !lastLabel || UNRELIABLE_LABELS.has(lastLabel)
      ? "Upload a new CSV after classifier training, or if the label is a placeholder from insufficient data."
      : "From your most recent stored analysis.";

  return (
    <div className="flex min-h-screen bg-clinical-950 bg-grid">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Header />
        <main className="flex flex-1 gap-4 overflow-hidden p-4">
          {confirmUploadDelete && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
              <div className="w-full max-w-md rounded-xl border border-slate-800/80 bg-clinical-900 p-4 shadow-xl">
                <p className="text-sm font-semibold text-white">Delete this upload?</p>
                <p className="mt-2 text-xs text-slate-400">
                  Removes the CSV, analysis record, and any synthetic files for{" "}
                  <span className="text-slate-200">{confirmUploadDelete.filename}</span>.
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  <button
                    type="button"
                    disabled={deleteUploadBusy}
                    onClick={() => setConfirmUploadDelete(null)}
                    className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800/50 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={deleteUploadBusy}
                    onClick={deleteUploadConfirmed}
                    className="flex items-center gap-2 rounded-lg border border-rose-900/60 bg-rose-950/40 px-3 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-900/30 disabled:opacity-50"
                  >
                    {deleteUploadBusy && <Spinner />}
                    Delete
                  </button>
                </div>
              </div>
            </div>
          )}
          <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Total uploads" value={summary != null ? summary.total_uploads : "—"} />
              <StatCard label="Analyses" value={summary != null ? summary.total_analyses : "—"} />
              <StatCard
                label="Last rhythm"
                value={
                  summary?.last_prediction_label ? summary.last_prediction_label.replace(/_/g, " ") : summary != null ? "N/A" : "—"
                }
                hint={lastRhythmHint}
              />
              <StatCard label="Status" value={busy ? "Processing…" : "Ready"} hint="JWT-secured API" />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4 lg:col-span-1">
                <h2 className="font-display text-sm font-semibold text-white">Upload ECG (CSV, Image, PDF)</h2>
                <p className="mt-1 text-xs text-slate-500">
                  CSV runs raw-signal analysis. Images/PDFs prioritize report text extraction; waveform extraction is approximate. Max 50MB.
                </p>
                <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-700 bg-clinical-850/50 px-4 py-8 transition hover:border-cyan-600/50">
                  <span className="text-sm font-medium text-cyan-400">Choose file</span>
                  <span className="mt-1 text-xs text-slate-500">or drag workflow via file picker</span>
                  <input
                    type="file"
                    accept=".csv,.pdf,image/png,image/jpeg,image/jpg"
                    className="hidden"
                    onChange={onUpload}
                    disabled={busy}
                  />
                </label>
                {(uploadDetected?.file_type || ingestion?.file_type) && (
                  <div className="mt-3 rounded-lg border border-slate-800/80 bg-clinical-850/40 p-3 text-xs text-slate-300">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Detected</p>
                    <p className="mt-1">
                      File type: <span className="text-cyan-200/90">{uploadDetected?.file_type || ingestion?.file_type || "—"}</span>{" "}
                      · Content: <span className="text-cyan-200/90">{uploadDetected?.content_type || ingestion?.content_type || "—"}</span>
                    </p>
                  </div>
                )}
                {uploadMsg && <p className="mt-3 text-xs text-cyan-200/90">{uploadMsg}</p>}
                {uploadPreview && (
                  <div className="mt-4 rounded-xl border border-slate-800/80 bg-clinical-850/30 p-3">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Preview</p>
                    <p className="mt-1 truncate text-xs text-slate-400">{uploadPreview.name}</p>
                    {uploadPreview.kind === "image" && (
                      <img
                        src={uploadPreview.url}
                        alt="Uploaded preview"
                        className="mt-3 max-h-56 w-full rounded-lg border border-slate-800/80 object-contain"
                      />
                    )}
                    {uploadPreview.kind === "pdf" && (
                      <div className="mt-3 rounded-lg border border-slate-800/80 bg-clinical-900/30 p-3 text-xs text-slate-400">
                        PDF preview is not rendered here. The server will extract text when possible.
                      </div>
                    )}
                    {uploadPreview.kind === "csv" && (
                      <div className="mt-3 rounded-lg border border-slate-800/80 bg-clinical-900/30 p-3 text-xs text-slate-400">
                        CSV preview is shown after processing (signal chart at right).
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4 lg:col-span-2">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="font-display text-sm font-semibold text-white">Signal preview</h2>
                  {analysis && (
                    <button
                      type="button"
                      onClick={generateSynthetic}
                      disabled={busy}
                      className="rounded-lg border border-violet-700/60 bg-violet-950/40 px-3 py-1 text-xs font-medium text-violet-200 transition hover:bg-violet-900/40 disabled:opacity-50"
                    >
                      {busy ? "Working…" : "Generate synthetic"}
                    </button>
                  )}
                </div>
                <LiveECGPanel series={analysis?.chart_series} />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
                <h2 className="font-display text-sm font-semibold text-white">Prediction summary</h2>
                {pred?.mock ? (
                  <p className="mt-1 text-xs text-amber-200/80">
                    Mock / fallback prediction (ENABLE_MOCK_INFERENCE). Not a medical diagnosis.
                  </p>
                ) : pred ? (
                  <p className="mt-1 text-xs text-slate-500">
                    TensorFlow beat classifier (research use only — not a medical diagnosis).
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">Upload a CSV to run inference.</p>
                )}
                {(reliability?.reliability_label || reliability?.analysis_label) && (
                  <div className="mt-3 rounded-lg border border-slate-800/80 bg-clinical-850/30 p-3 text-xs text-slate-300">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Reliability</p>
                    <p className="mt-1">
                      <span className="text-cyan-200/90">{reliability.analysis_label || "—"}</span>{" "}
                      {reliability.reliability_label ? `· ${reliability.reliability_label}` : ""}
                    </p>
                    {reliability.disclaimer && <p className="mt-1 text-[10px] text-slate-500">{reliability.disclaimer}</p>}
                  </div>
                )}
                {pred ? (
                  <dl className="mt-4 space-y-2 text-sm">
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">Predicted condition</dt>
                      <dd className="font-medium text-cyan-100">
                        {pred.predicted_class || pred.label}
                      </dd>
                    </div>
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">Confidence</dt>
                      <dd className="text-slate-200">
                        {typeof pred.confidence === "number" ? `${(pred.confidence * 100).toFixed(1)}%` : "—"}
                      </dd>
                    </div>
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">Risk level</dt>
                      <dd className={`font-semibold ${riskLevelTextClass(pred.risk_level)}`}>
                        {pred.risk_level
                          ? `${String(pred.risk_level).toUpperCase()}${pred.risk_score != null ? ` (${pred.risk_score})` : ""}`
                          : "—"}
                      </dd>
                    </div>
                    {pred.recommendation && (
                      <div className="border-b border-slate-800/80 py-2">
                        <dt className="text-slate-500">Recommendation</dt>
                        <dd className="mt-1 text-xs text-slate-300">{pred.recommendation}</dd>
                      </div>
                    )}
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">Rhythm hint</dt>
                      <dd className="text-slate-200">{pred.rhythm_hint}</dd>
                    </div>
                    {formatAllProbabilities(pred.all_probabilities) && (
                      <div className="border-b border-slate-800/80 py-2">
                        <dt className="text-slate-500">Class probabilities</dt>
                        <dd className="mt-1 text-[10px] leading-snug text-slate-400">
                          {formatAllProbabilities(pred.all_probabilities)}
                        </dd>
                      </div>
                    )}
                    <p className="pt-2 text-xs leading-relaxed text-slate-400">{pred.explanation_stub}</p>
                  </dl>
                ) : (
                  <p className="mt-6 text-sm text-slate-500">Select or upload an analysis to view results.</p>
                )}
              </div>

              <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
                <h2 className="font-display text-sm font-semibold text-white">Extracted report values</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Available for image/PDF uploads when text could be extracted. This is not a medical diagnosis.
                </p>
                {!reportFields ? (
                  <div className="mt-4 rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 p-4 text-sm text-slate-500">
                    No report fields detected for this analysis.
                  </div>
                ) : (
                  <dl className="mt-4 space-y-2 text-sm">
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">Heart rate</dt>
                      <dd className="text-slate-200">{reportFields.heart_rate ?? "—"}</dd>
                    </div>
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">PR interval (ms)</dt>
                      <dd className="text-slate-200">{reportFields.pr_interval ?? "—"}</dd>
                    </div>
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">QRS duration (ms)</dt>
                      <dd className="text-slate-200">{reportFields.qrs_duration ?? "—"}</dd>
                    </div>
                    <div className="flex justify-between border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">QTc (ms)</dt>
                      <dd className="text-slate-200">{reportFields.qtc ?? "—"}</dd>
                    </div>
                    <div className="border-b border-slate-800/80 py-2">
                      <dt className="text-slate-500">Interpretation</dt>
                      <dd className="mt-1 text-xs text-slate-300">{reportFields.interpretation ?? "—"}</dd>
                    </div>
                    {analysis?.preprocess_metadata?.patient_friendly_explanation && (
                      <div className="pt-2">
                        <dt className="text-slate-500">Patient-friendly summary</dt>
                        <dd className="mt-1 text-xs text-slate-300">{analysis.preprocess_metadata.patient_friendly_explanation}</dd>
                      </div>
                    )}
                  </dl>
                )}

                {pred?.manual_input_required && (
                  <form onSubmit={submitManual} className="mt-4 rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Manual fallback</p>
                    <p className="mt-1 text-xs text-slate-400">Enter any values you have to continue analysis.</p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        Heart rate (bpm)
                        <input name="heart_rate" type="number" min={10} max={260} className="mt-1 w-full rounded-lg border border-slate-700 bg-clinical-900/40 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2" />
                      </label>
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        PR (ms)
                        <input name="pr_interval" type="number" min={40} max={400} className="mt-1 w-full rounded-lg border border-slate-700 bg-clinical-900/40 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2" />
                      </label>
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        QRS (ms)
                        <input name="qrs_duration" type="number" min={40} max={300} className="mt-1 w-full rounded-lg border border-slate-700 bg-clinical-900/40 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2" />
                      </label>
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        QTc (ms)
                        <input name="qtc" type="number" min={200} max={700} className="mt-1 w-full rounded-lg border border-slate-700 bg-clinical-900/40 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2" />
                      </label>
                    </div>
                    <label className="mt-3 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Symptoms (optional)
                      <textarea name="symptoms" rows={2} className="mt-1 w-full resize-none rounded-lg border border-slate-700 bg-clinical-900/40 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2" />
                    </label>
                    <button type="submit" disabled={busy} className="mt-3 rounded-lg bg-cyan-600 px-3 py-2 text-xs font-semibold text-clinical-950 hover:bg-cyan-500 disabled:opacity-50">
                      {busy ? "Saving…" : "Save manual inputs"}
                    </button>
                  </form>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <h2 className="font-display text-sm font-semibold text-white">Recent reports</h2>
              {recentFeedback.text && (
                <p
                  className={
                    recentFeedback.kind === "ok"
                      ? "mt-2 text-xs text-emerald-200/90"
                      : "mt-2 text-xs text-amber-200/90"
                  }
                >
                  {recentFeedback.text}
                </p>
              )}
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
                      <th className="pb-2 pr-4">File</th>
                      <th className="pb-2 pr-4">Label</th>
                      <th className="pb-2 pr-4">Confidence</th>
                      <th className="pb-2 pr-4">When</th>
                      <th className="pb-2 text-right"> </th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((row) => (
                      <tr
                        key={row.analysis_id}
                        className="cursor-pointer border-b border-slate-800/60 hover:bg-slate-800/40"
                        onClick={() => loadAnalysis(row.analysis_id)}
                      >
                        <td className="py-2 pr-4 text-slate-200">{row.filename}</td>
                        <td className="py-2 pr-4 text-cyan-200/90">{row.label}</td>
                        <td className="py-2 pr-4 text-slate-400">
                          {row.confidence != null ? `${(row.confidence * 100).toFixed(0)}%` : "—"}
                        </td>
                        <td className="py-2 pr-4 text-xs text-slate-500">
                          {new Date(row.created_at).toLocaleString()}
                        </td>
                        <td className="py-2 text-right">
                          <button
                            type="button"
                            title="Delete upload"
                            onClick={(e) => {
                              e.stopPropagation();
                              setRecentFeedback({ kind: "", text: "" });
                              setConfirmUploadDelete({
                                upload_id: row.upload_id,
                                analysis_id: row.analysis_id,
                                filename: row.filename,
                              });
                            }}
                            className="rounded border border-rose-900/50 bg-rose-950/20 px-2 py-0.5 text-[10px] font-semibold text-rose-200/90 hover:bg-rose-900/20"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                    {recent.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-slate-500">
                          No uploads yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <aside className="hidden w-80 shrink-0 flex-col rounded-xl border border-slate-800/80 bg-clinical-900/60 lg:flex">
            <div className="border-b border-slate-800/80 p-4">
              <h2 className="font-display text-sm font-semibold text-white">AI assistant</h2>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                Rule-based wellness hints. Not a final medical diagnosis — always consult your clinician.
              </p>
            </div>
            <div className="flex flex-1 flex-col overflow-hidden">
              <div className="flex-1 space-y-3 overflow-y-auto p-4 text-sm">
                {chatMessages.length === 0 && (
                  <p className="text-slate-500">
                    Ask about your latest result, exercise, sleep, or diet. I will include a safety disclaimer.
                  </p>
                )}
                {chatMessages.map((m, i) => (
                  <div
                    key={i}
                    className={`rounded-lg px-3 py-2 ${
                      m.role === "user"
                        ? "ml-4 bg-cyan-950/50 text-cyan-100"
                        : "mr-4 border border-slate-800 bg-clinical-850/80 text-slate-300"
                    }`}
                  >
                    <p className="whitespace-pre-wrap text-xs leading-relaxed">{m.text}</p>
                    {m.role === "assistant" && (m.summary || m.condition_explanation) && (
                      <div className="mt-2 space-y-1 border-t border-slate-800/80 pt-2 text-[10px] leading-relaxed text-slate-500">
                        {m.summary && <p>{m.summary}</p>}
                        {m.condition_explanation && <p>{m.condition_explanation}</p>}
                        {m.risk_explanation && <p>{m.risk_explanation}</p>}
                        {m.recommendation && <p className="text-slate-400">{m.recommendation}</p>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <form onSubmit={sendChat} className="border-t border-slate-800/80 p-3">
                <textarea
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  rows={2}
                  placeholder="Type a message…"
                  className="mb-2 w-full resize-none rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs text-white outline-none ring-cyan-500/30 focus:ring-1"
                />
                <button
                  type="submit"
                  className="w-full rounded-lg bg-cyan-600 py-2 text-xs font-semibold text-clinical-950 hover:bg-cyan-500"
                >
                  Send
                </button>
              </form>
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}
