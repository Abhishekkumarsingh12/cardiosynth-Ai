import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * Renders normalized ECG samples from the API (mock pipeline).
 */
export default function ECGChart({ series }) {
  const data = (series || []).map((v, i) => ({ i, v }));

  if (!data.length) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-clinical-850/50 text-sm text-slate-500">
        Upload a CSV to visualize the first numeric column
      </div>
    );
  }

  return (
    <div className="h-64 w-full rounded-xl border border-slate-800 bg-clinical-850/40 p-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="i" hide />
          <YAxis domain={["auto", "auto"]} stroke="#64748b" tick={{ fontSize: 10 }} width={36} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f172a",
              border: "1px solid #334155",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            labelFormatter={() => "Sample"}
          />
          <Line
            type="monotone"
            dataKey="v"
            stroke="#22d3ee"
            strokeWidth={1.2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
