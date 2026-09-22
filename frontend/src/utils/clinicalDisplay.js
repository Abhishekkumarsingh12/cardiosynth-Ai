/** Tailwind text classes for automated risk tier (education only). */
export function riskLevelTextClass(level) {
  const l = String(level || "").toLowerCase();
  if (l === "low") return "text-emerald-300";
  if (l === "medium") return "text-amber-300";
  if (l === "high") return "text-rose-300";
  return "text-slate-400";
}

export const CLINICAL_CLASS_ORDER = ["Normal", "AFib", "PVC", "Tachycardia", "Bradycardia"];

export function formatAllProbabilities(arr) {
  if (!Array.isArray(arr) || arr.length === 0) return null;
  const names = CLINICAL_CLASS_ORDER;
  return arr
    .map((p, i) => `${names[i] || i}: ${(Number(p) * 100).toFixed(1)}%`)
    .join(" · ");
}
