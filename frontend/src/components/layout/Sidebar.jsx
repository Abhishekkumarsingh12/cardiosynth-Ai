import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }) =>
  `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
    isActive ? "bg-cyan-500/15 text-cyan-300" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
  }`;

export default function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-800/80 bg-clinical-900/50">
      <div className="border-b border-slate-800/80 px-4 py-5">
        <p className="font-display text-lg font-semibold tracking-tight text-white">CardioSynth</p>
        <p className="text-[10px] font-medium uppercase tracking-widest text-cyan-500/80">Clinical AI</p>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3">
        <NavLink to="/" end className={linkClass}>
          <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
          Dashboard
        </NavLink>
        <div className="mt-6 px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
          Modules
        </div>
        <NavLink to="/monitor" className={linkClass}>
          <span className="h-2 w-2 rounded-full bg-cyan-400/80 shadow-[0_0_8px_rgba(34,211,238,0.6)]" />
          Monitor
        </NavLink>
        <NavLink to="/history" className={linkClass}>
          <span className="h-2 w-2 rounded-full bg-amber-400/80 shadow-[0_0_8px_rgba(251,191,36,0.55)]" />
          History
        </NavLink>
        <NavLink to="/studio" className={linkClass}>
          <span className="h-2 w-2 rounded-full bg-emerald-400/80 shadow-[0_0_8px_rgba(52,211,153,0.7)]" />
          ECG Studio
        </NavLink>
        <NavLink to="/reports" className={linkClass}>
          <span className="h-2 w-2 rounded-full bg-slate-400/70 shadow-[0_0_8px_rgba(148,163,184,0.5)]" />
          Reports
        </NavLink>
        <NavLink to="/synthetic" className={linkClass}>
          <span className="h-2 w-2 rounded-full bg-violet-400/80 shadow-[0_0_8px_rgba(167,139,250,0.6)]" />
          Synthetic
        </NavLink>
      </nav>
      <div className="border-t border-slate-800/80 p-4">
        <p className="text-[10px] leading-relaxed text-slate-600">
          Research use only. Not a medical diagnosis.
        </p>
      </div>
    </aside>
  );
}
