import { useAuth } from "../../context/AuthContext.jsx";

export default function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800/80 bg-clinical-900/30 px-6 backdrop-blur">
      <div>
        <h1 className="font-display text-sm font-semibold text-white">ECG Command Center</h1>
        <p className="text-xs text-clinical-muted">Live signal review · encrypted session</p>
      </div>
      <div className="flex items-center gap-4">
        <div className="hidden text-right sm:block">
          <p className="text-sm font-medium text-slate-200">{user?.full_name || user?.email}</p>
          <p className="text-[10px] uppercase tracking-wider text-slate-500">{user?.email}</p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-500 hover:bg-slate-800/50"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
