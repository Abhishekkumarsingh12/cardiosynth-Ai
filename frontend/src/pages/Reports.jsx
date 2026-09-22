import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client.js";
import ECGChart from "../components/ecg/ECGChart.jsx";
import ECGExplainChart from "../components/ecg/ECGExplainChart.jsx";
import Header from "../components/layout/Header.jsx";
import Sidebar from "../components/layout/Sidebar.jsx";
import { formatAllProbabilities, riskLevelTextClass } from "../utils/clinicalDisplay.js";

function Spinner() {
  return (
    <span
      className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-cyan-500/30 border-t-cyan-400"
      aria-hidden
    />
  );
}

function shortAnalysisId(id) {
  const s = String(id ?? "");
  if (s.length <= 8) return s;
  return `${s.slice(0, 8)}…`;
}

function StatusBadge({ status }) {
  const s = (status || "unknown").toLowerCase();
  const map = {
    success: "border-emerald-800/60 bg-emerald-950/30 text-emerald-200",
    failed: "border-rose-900/60 bg-rose-950/30 text-rose-200",
    partial: "border-amber-900/60 bg-amber-950/30 text-amber-200",
    unknown: "border-slate-800/80 bg-clinical-850/40 text-slate-300",
  };
  return <span className={`rounded-full border px-2 py-0.5 text-[10px] ${map[s] || map.unknown}`}>{s}</span>;
}

export default function Reports() {
  const [rows, setRows] = useState([]);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatUrgency, setChatUrgency] = useState(null);
  const [listLoading, setListLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [explain, setExplain] = useState(null);
  const [explainBusy, setExplainBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [copiedAnalysisId, setCopiedAnalysisId] = useState(null);

  useEffect(() => {
    if (copiedAnalysisId == null) return undefined;
    const t = setTimeout(() => setCopiedAnalysisId(null), 2000);
    return () => clearTimeout(t);
  }, [copiedAnalysisId]);

  async function copyAnalysisId(id) {
    const text = String(id);
    try {
      await navigator.clipboard.writeText(text);
      setCopiedAnalysisId(id);
    } catch {
      setMsg("Could not copy analysis ID.");
    }
  }

  const refresh = useCallback(async () => {
    setListLoading(true);
    try {
      const { data } = await client.get("/reports");
      setRows(data);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  useEffect(() => {
    if (!detail?.analysis_id) {
      setExplain(null);
      return;
    }
    let cancelled = false;
    setExplainBusy(true);
    client
      .get(`/ecg/explain/${detail.analysis_id}`)
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
  }, [detail?.analysis_id]);

  async function openReport(id) {
    setBusy(true);
    setMsg("");
    setSuccessMsg("");
    try {
      const { data } = await client.get(`/reports/${id}`);
      setDetail(data);
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Failed to load report.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteReport(analysisId) {
    setDeleteBusy(true);
    setMsg("");
    setSuccessMsg("");
    try {
      await client.delete(`/reports/${analysisId}`);
      setConfirmDelete(null);
      setSuccessMsg("Report deleted.");
      if (detail?.analysis_id === analysisId) {
        setDetail(null);
        setChatMessages([]);
        setChatUrgency(null);
      }
      await refresh();
      window.dispatchEvent(new Event("cardiosynth-data-changed"));
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Delete failed.");
    } finally {
      setDeleteBusy(false);
    }
  }

  async function downloadPdf(id) {
    setPdfBusy(true);
    setMsg("");
    try {
      const res = await client.get(`/reports/${id}/export-pdf`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cardiosynth_report_${id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setMsg("PDF export failed.");
    } finally {
      setPdfBusy(false);
    }
  }

  async function exportJson(id) {
    setBusy(true);
    setMsg("");
    try {
      const res = await client.get(`/reports/${id}/export`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cardiosynth_report_${id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  const pred = detail?.prediction_result || {};
  const meta = detail?.preprocess_metadata || {};
  const canChat = !!detail;

  const quickPrompts = [
    "Explain my ECG result",
    "Is this serious?",
    "When should I see a doctor?",
    "What symptoms are dangerous?",
  ];

  async function sendGuidance(text) {
    if (!detail) return;
    const t = (text ?? "").trim();
    if (!t) return;
    setChatMessages((m) => [...m, { role: "user", text: t }]);
    setChatInput("");
    try {
      const { data } = await client.post("/assistant/report-guidance", {
        message: t,
        prediction_result: pred,
        preprocess_metadata: meta,
        analysis_id: detail.analysis_id,
        session_id: String(detail.analysis_id),
        include_history: true,
      });
      setChatUrgency(data.urgency);
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
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setChatMessages((m) => [
        ...m,
        { role: "assistant", text: typeof d === "string" ? d : "Guidance assistant unavailable." },
      ]);
    }
  }

  return (
    <div className="flex min-h-screen bg-clinical-950 bg-grid">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Header />
        <main className="flex flex-1 gap-4 overflow-hidden p-4">
          {confirmDelete && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
              <div className="w-full max-w-md rounded-xl border border-slate-800/80 bg-clinical-900 p-4 shadow-xl">
                <p className="text-sm font-semibold text-white">Delete this report?</p>
                <p className="mt-2 text-xs text-slate-400">
                  This removes the analysis, uploaded CSV, and any synthetic CSV files for{" "}
                  <span className="text-slate-200">{confirmDelete.filename}</span>. This cannot be undone.
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  <button
                    type="button"
                    disabled={deleteBusy}
                    onClick={() => setConfirmDelete(null)}
                    className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800/50 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={deleteBusy}
                    onClick={() => deleteReport(confirmDelete.analysis_id)}
                    className="flex items-center gap-2 rounded-lg border border-rose-900/60 bg-rose-950/40 px-3 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-900/30 disabled:opacity-50"
                  >
                    {deleteBusy && <Spinner />}
                    Delete
                  </button>
                </div>
              </div>
            </div>
          )}
          <div className="flex min-w-0 flex-1 gap-4 overflow-hidden">
            <div className="w-[360px] shrink-0 overflow-y-auto rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <h2 className="font-display text-sm font-semibold text-white">Reports</h2>
              <p className="mt-1 text-xs text-slate-500">Saved analyses. Click a row to view details.</p>
              {successMsg && (
                <p className="mt-3 text-xs text-emerald-200/90">{successMsg}</p>
              )}
              {msg && <p className="mt-3 text-xs text-amber-200/90">{msg}</p>}
              <div className="mt-4 space-y-2">
                {listLoading && (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Spinner />
                    Loading reports…
                  </div>
                )}
                {!listLoading && rows.length === 0 && (
                  <div className="rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 p-4 text-sm text-slate-500">
                    No reports yet. Upload a CSV in Dashboard or ECG Studio.
                  </div>
                )}
                {rows.map((r) => (
                  <div
                    key={r.analysis_id}
                    className="w-full rounded-xl border border-slate-800/80 bg-clinical-850/30 px-3 py-2 transition hover:bg-slate-800/40"
                  >
                    <button type="button" onClick={() => openReport(r.analysis_id)} className="w-full text-left">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium text-slate-200">{r.filename}</p>
                        <StatusBadge status={r.status} />
                      </div>
                      <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
                        <span>{(r.label || "—").replace(/_/g, " ")}</span>
                        <span>{typeof r.confidence === "number" ? `${(r.confidence * 100).toFixed(1)}%` : "—"}</span>
                      </div>
                    </button>
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/60 pt-2">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <span
                          className="text-[10px] text-slate-500"
                          title={`Full analysis ID: ${r.analysis_id}`}
                        >
                          ID{" "}
                          <span className="font-mono text-slate-400">{shortAnalysisId(r.analysis_id)}</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => copyAnalysisId(r.analysis_id)}
                          className="rounded border border-slate-700 bg-clinical-850 px-2 py-0.5 text-[10px] font-semibold text-cyan-300/90 transition hover:bg-slate-800/50"
                        >
                          {copiedAnalysisId === r.analysis_id ? "Copied" : "Copy ID"}
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() => setConfirmDelete({ analysis_id: r.analysis_id, filename: r.filename })}
                        className="rounded border border-rose-900/50 bg-rose-950/20 px-2 py-1 text-[10px] font-semibold text-rose-200/90 hover:bg-rose-900/20"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="min-w-0 flex-1 overflow-y-auto rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div>
                    <h2 className="font-display text-sm font-semibold text-white">Report detail</h2>
                    <p className="mt-1 text-xs text-slate-500">
                      {busy ? "Loading…" : detail ? "Includes plots, metadata, and prediction summary." : "Select a report."}
                    </p>
                  </div>
                  {busy && <Spinner />}
                </div>
                {detail && (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => downloadPdf(detail.analysis_id)}
                      disabled={busy || pdfBusy}
                      className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-800/50 disabled:opacity-50"
                    >
                      {pdfBusy ? "PDF…" : "Download PDF"}
                    </button>
                    <button
                      type="button"
                      onClick={() => exportJson(detail.analysis_id)}
                      disabled={busy}
                      className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-slate-800/50 disabled:opacity-50"
                    >
                      Export JSON
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setConfirmDelete({
                          analysis_id: detail.analysis_id,
                          filename: detail.upload?.original_name,
                        })
                      }
                      disabled={busy || deleteBusy}
                      className="rounded-lg border border-rose-900/50 bg-rose-950/20 px-3 py-2 text-xs font-semibold text-rose-200/90 transition hover:bg-rose-900/25 disabled:opacity-50"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>

              {!detail ? (
                <div className="mt-6 rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 p-6 text-sm text-slate-500">
                  Pick a report from the list.
                </div>
              ) : (
                <div className="mt-4 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800/80 bg-clinical-850/30 p-3">
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Analysis ID</p>
                      <p className="mt-1 font-mono text-sm text-slate-200" title={`Full analysis ID: ${detail.analysis_id}`}>
                        {detail.analysis_id}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => copyAnalysisId(detail.analysis_id)}
                        className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-slate-800/50"
                      >
                        {copiedAnalysisId === detail.analysis_id ? "Copied" : "Copy ID"}
                      </button>
                      <Link
                        to={`/synthetic?analysis_id=${detail.analysis_id}`}
                        className="rounded-lg border border-violet-700/60 bg-violet-950/40 px-3 py-1.5 text-xs font-semibold text-violet-200 transition hover:bg-violet-900/40"
                      >
                        Synthetic
                      </Link>
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="rounded-lg border border-slate-800/80 bg-clinical-850/30 p-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">File</p>
                      <p className="mt-1 truncate text-sm text-slate-200">{detail.upload?.original_name}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800/80 bg-clinical-850/30 p-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Signal column</p>
                      <p className="mt-1 text-sm text-slate-200">{meta.selected_signal_column || meta.source_column || "—"}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800/80 bg-clinical-850/30 p-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Status</p>
                      <p className="mt-1 text-sm text-slate-200">{pred.status || "—"}</p>
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                    <h3 className="text-sm font-semibold text-white">Waveform preview</h3>
                    <p className="mt-1 text-xs text-slate-500">From stored analysis chart series.</p>
                    <div className="mt-3">
                      <ECGChart series={detail.chart_series} />
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                    <h3 className="text-sm font-semibold text-white">Prediction summary</h3>
                    <dl className="mt-3 space-y-2 text-sm">
                      <div className="flex justify-between border-b border-slate-800/80 py-2">
                        <dt className="text-slate-500">Predicted condition</dt>
                        <dd className="font-medium text-cyan-100">{pred.predicted_class || pred.label}</dd>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/80 py-2">
                        <dt className="text-slate-500">Confidence</dt>
                        <dd className="text-slate-200">
                          {typeof pred.confidence === "number" ? `${(pred.confidence * 100).toFixed(1)}%` : "—"}
                        </dd>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/80 py-2">
                        <dt className="text-slate-500">Beats analyzed</dt>
                        <dd className="text-slate-200">{pred.beats_analyzed ?? pred?.studio_summary?.beats_analyzed ?? "—"}</dd>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/80 py-2">
                        <dt className="text-slate-500">Risk</dt>
                        <dd className={`font-semibold ${riskLevelTextClass(pred.risk_level)}`}>
                          {pred.risk_level
                            ? `${String(pred.risk_level).toUpperCase()}${pred.risk_score != null ? ` (${pred.risk_score})` : ""}`
                            : "—"}
                          {pred.risk_level === "high" ? " ⚠" : ""}
                        </dd>
                      </div>
                      {pred.recommendation && (
                        <div className="border-b border-slate-800/80 py-2">
                          <dt className="text-slate-500">Recommendation</dt>
                          <dd className="mt-1 text-xs text-slate-300">{pred.recommendation}</dd>
                        </div>
                      )}
                      {formatAllProbabilities(pred.all_probabilities) && (
                        <div className="border-b border-slate-800/80 py-2">
                          <dt className="text-slate-500">Class probabilities</dt>
                          <dd className="mt-1 text-[10px] leading-snug text-slate-400">
                            {formatAllProbabilities(pred.all_probabilities)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </div>

                  <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                    <h3 className="text-sm font-semibold text-white">Model interpretability</h3>
                    <p className="mt-1 text-xs text-slate-500">
                      Input-gradient saliency on the classifier window (not clinical localization).{" "}
                      {explainBusy ? "Loading…" : ""}
                    </p>
                    {explain?.explanation_summary && (
                      <p className="mt-2 text-xs text-slate-400">{explain.explanation_summary}</p>
                    )}
                    {!explainBusy && !explain && (
                      <p className="mt-2 text-xs text-amber-200/80">Explainability unavailable (check classifier / server).</p>
                    )}
                    <div className="mt-3">
                      <ECGExplainChart
                        waveform={explain?.window_waveform}
                        importance={explain?.importance_normalized}
                        regions={explain?.important_regions}
                      />
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-800/80 bg-clinical-850/30 p-4">
                    <h3 className="text-sm font-semibold text-white">Guidance assistant</h3>
                    <p className="mt-1 text-xs text-slate-500">
                      Rule-based, context-aware support summary. Not a medical diagnosis.
                    </p>
                    {chatUrgency && (
                      <p className="mt-2 text-xs text-slate-400">
                        Urgency: <span className="text-slate-200">{String(chatUrgency).replace(/_/g, " ")}</span>
                      </p>
                    )}

                    <div className="mt-3 flex flex-wrap gap-2">
                      {quickPrompts.map((p) => (
                        <button
                          key={p}
                          type="button"
                          onClick={() => sendGuidance(p)}
                          disabled={!canChat || busy}
                          className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-1 text-xs font-medium text-slate-200 transition hover:bg-slate-800/50 disabled:opacity-50"
                        >
                          {p}
                        </button>
                      ))}
                    </div>

                    <div className="mt-4 max-h-56 space-y-2 overflow-y-auto rounded-xl border border-slate-800 bg-clinical-900/30 p-3 text-sm">
                      {chatMessages.length === 0 ? (
                        <p className="text-xs text-slate-500">Ask a question about this report to get a safe support summary.</p>
                      ) : (
                        chatMessages.map((m, idx) => (
                          <div
                            key={idx}
                            className={`max-w-[90%] rounded-xl border px-3 py-2 text-xs leading-relaxed ${
                              m.role === "user"
                                ? "ml-auto border-cyan-900/60 bg-cyan-950/20 text-cyan-100"
                                : "mr-auto border-slate-800/80 bg-clinical-850/30 text-slate-200"
                            }`}
                          >
                            <span className="whitespace-pre-wrap">{m.text}</span>
                            {m.role === "assistant" && (m.summary || m.condition_explanation) && (
                              <div className="mt-2 space-y-1 border-t border-slate-800/60 pt-2 text-[10px] text-slate-500">
                                {m.summary && <p>{m.summary}</p>}
                                {m.condition_explanation && <p>{m.condition_explanation}</p>}
                                {m.risk_explanation && <p>{m.risk_explanation}</p>}
                                {m.recommendation && <p className="text-slate-400">{m.recommendation}</p>}
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>

                    <form
                      className="mt-3 flex items-center gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        sendGuidance(chatInput);
                      }}
                    >
                      <input
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        disabled={!canChat || busy}
                        placeholder="Ask about this report…"
                        className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2 disabled:opacity-50"
                      />
                      <button
                        type="submit"
                        disabled={!canChat || busy || !chatInput.trim()}
                        className="rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-slate-800/50 disabled:opacity-50"
                      >
                        Send
                      </button>
                    </form>
                  </div>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

