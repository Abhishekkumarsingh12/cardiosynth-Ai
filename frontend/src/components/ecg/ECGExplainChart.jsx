import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Classifier window + normalized saliency overlay (importance 0–1 on right axis). */
export default function ECGExplainChart({ waveform, importance, regions }) {
  const w = waveform || [];
  const imp = importance || [];
  const n = Math.min(w.length, imp.length, 2000);
  const data = [];
  for (let i = 0; i < n; i++) {
    data.push({ i, v: w[i], imp: imp[i] ?? 0 });
  }
  const regs = Array.isArray(regions) ? regions : [];

  if (!data.length) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 text-sm text-slate-500">
        No explainability data
      </div>
    );
  }

  return (
    <div className="h-64 w-full rounded-xl border border-slate-800 bg-clinical-850/40 p-2">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="i" hide />
          <YAxis yAxisId="left" domain={["auto", "auto"]} stroke="#64748b" tick={{ fontSize: 10 }} width={36} />
          <YAxis yAxisId="right" orientation="right" domain={[0, 1]} hide />
          {regs.map((r, idx) => {
            const x1 = Number(r?.start);
            const x2 = Number(r?.end);
            if (!Number.isFinite(x1) || !Number.isFinite(x2)) return null;
            return (
              <ReferenceArea
                key={idx}
                x1={Math.max(0, Math.min(x1, n - 1))}
                x2={Math.max(0, Math.min(x2, n - 1))}
                yAxisId="left"
                fill="#f97316"
                fillOpacity={0.08}
                strokeOpacity={0}
              />
            );
          })}
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f172a",
              border: "1px solid #334155",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            formatter={(value, name) => [typeof value === "number" ? value.toFixed(4) : value, name === "imp" ? "Saliency" : "Signal"]}
            labelFormatter={() => "Sample"}
          />
          <Area
            yAxisId="right"
            type="monotone"
            dataKey="imp"
            stroke="#fb923c"
            fill="#fb923c"
            fillOpacity={0.22}
            isAnimationActive={false}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="v"
            stroke="#22d3ee"
            strokeWidth={1.2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
