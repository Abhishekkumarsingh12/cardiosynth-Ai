import { useEffect, useMemo, useState } from "react";
import client from "../api/client.js";
import Header from "../components/layout/Header.jsx";
import Sidebar from "../components/layout/Sidebar.jsx";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function toDayKey(dt) {
  try {
    const d = new Date(dt);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch {
    return "";
  }
}

export default function History() {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(true);
  const [labelFilter, setLabelFilter] = useState("");
  const [days, setDays] = useState(30);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    client
      .get("/reports")
      .then(({ data }) => {
        if (!cancelled) setRows(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const now = Date.now();
    const ms = Math.max(1, Number(days) || 30) * 24 * 3600 * 1000;
    return rows.filter((r) => {
      const okLabel = !labelFilter || String(r.label || "").toLowerCase().includes(labelFilter.toLowerCase());
      const t = new Date(r.created_at).getTime();
      const okTime = Number.isFinite(t) ? now - t <= ms : true;
      return okLabel && okTime;
    });
  }, [rows, labelFilter, days]);

  const trend = useMemo(() => {
    const map = new Map();
    for (const r of filtered) {
      const k = toDayKey(r.created_at);
      if (!k) continue;
      const prev = map.get(k) || { day: k, n: 0, conf_sum: 0, risk_sum: 0, risk_n: 0 };
      prev.n += 1;
      if (typeof r.confidence === "number") prev.conf_sum += r.confidence;
      if (typeof r.risk_score === "number") {
        prev.risk_sum += r.risk_score;
        prev.risk_n += 1;
      }
      map.set(k, prev);
    }
    return Array.from(map.values())
      .sort((a, b) => String(a.day).localeCompare(String(b.day)))
      .map((x) => ({
        day: x.day,
        analyses: x.n,
        confidence_mean: x.n ? x.conf_sum / x.n : null,
        risk_mean: x.risk_n ? x.risk_sum / x.risk_n : null,
      }));
  }, [filtered]);

  return (
    <div className="flex min-h-screen bg-clinical-950 bg-grid">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Header />
        <main className="flex flex-1 gap-4 overflow-hidden p-4">
          <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
            <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <h2 className="font-display text-sm font-semibold text-white">Patient History</h2>
              <p className="mt-1 text-xs text-slate-500">Filter and view trends across your saved analyses.</p>
              <div className="mt-4 flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Filter label
                  <input
                    value={labelFilter}
                    onChange={(e) => setLabelFilter(e.target.value)}
                    placeholder="e.g. afib, normal"
                    className="w-44 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                  />
                </label>
                <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Days
                  <input
                    type="number"
                    min={1}
                    max={365}
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                    className="w-24 rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
                  />
                </label>
                <span className="text-xs text-slate-500">{busy ? "Loading…" : `${filtered.length} records`}</span>
              </div>
            </div>

            <div className="rounded-xl border border-slate-800/80 bg-clinical-900/40 p-4">
              <h3 className="text-sm font-semibold text-white">Trends (daily)</h3>
              <p className="mt-1 text-xs text-slate-500">Confidence and risk mean over time.</p>
              <div className="mt-3 h-72 w-full rounded-xl border border-slate-800 bg-clinical-850/30 p-2">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#0f172a",
                        border: "1px solid #334155",
                        borderRadius: "8px",
                        fontSize: "12px",
                      }}
                    />
                    <Line type="monotone" dataKey="confidence_mean" stroke="#22d3ee" dot={false} isAnimationActive={false} />
                    <Line type="monotone" dataKey="risk_mean" stroke="#fb923c" dot={false} isAnimationActive={false} />
                    <Line type="monotone" dataKey="analyses" stroke="#a78bfa" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

