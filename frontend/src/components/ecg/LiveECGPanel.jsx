import { useLiveECGSimulation } from "../../hooks/useLiveECGSimulation.js";
import ECGChart from "./ECGChart.jsx";

const SPEED_OPTIONS = [0.25, 0.5, 1, 2];

/**
 * Full signal preview plus optional live scrolling-window simulation (same chart styling).
 */
export default function LiveECGPanel({ series }) {
  const src = series || [];
  const {
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
  } = useLiveECGSimulation(src);

  const chartSeries = liveEnabled ? displaySeries : src;
  const canLive = hasSignal;
  const liveDisabledTitle = canLive ? undefined : "Upload or generate a signal first";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <label
          className={`inline-flex cursor-pointer items-center gap-1.5 text-[10px] font-medium ${
            canLive ? "text-slate-400" : "cursor-not-allowed text-slate-600"
          }`}
          title={liveDisabledTitle}
        >
          <input
            type="checkbox"
            className="rounded border-slate-600 bg-clinical-850 text-cyan-500 focus:ring-cyan-500/40 disabled:opacity-40"
            checked={liveEnabled}
            disabled={!canLive}
            onChange={(e) => setLiveEnabled(e.target.checked)}
          />
          Live simulation
        </label>
        {liveEnabled && (
          <>
            <button
              type="button"
              disabled={!canLive}
              onClick={() => setPlaying((p) => !p)}
              className="rounded-lg border border-slate-700 bg-clinical-850 px-2 py-1 text-[10px] font-semibold text-slate-200 transition hover:bg-slate-800/50 disabled:opacity-40"
              aria-pressed={playing}
            >
              {playing ? "Pause" : "Play"}
            </button>
            <label className="flex items-center gap-1 text-[10px] text-slate-500">
              <span className="sr-only">Speed</span>
              <span aria-hidden>Speed</span>
              <select
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="rounded border border-slate-700 bg-clinical-850 py-0.5 pl-1 pr-6 text-[10px] text-slate-200"
              >
                {SPEED_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}×
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-flex cursor-pointer items-center gap-1.5 text-[10px] text-slate-400">
              <input
                type="checkbox"
                className="rounded border-slate-600 bg-clinical-850 text-cyan-500 focus:ring-cyan-500/40"
                checked={loop}
                onChange={(e) => setLoop(e.target.checked)}
              />
              Loop
            </label>
          </>
        )}
      </div>
      <ECGChart series={chartSeries} />
    </div>
  );
}
