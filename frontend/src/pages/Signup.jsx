import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function Signup() {
  const { signup } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [err, setErr] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setErr("");
    if (password.length < 8) {
      setErr("Password must be at least 8 characters.");
      return;
    }
    try {
      await signup(email, password, fullName);
      nav("/");
    } catch (ex) {
      const msg = ex?.response?.data?.detail;
      setErr(typeof msg === "string" ? msg : "Could not create account.");
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-clinical-950 bg-grid px-4">
      <div className="absolute inset-0 bg-gradient-to-br from-cyan-950/20 via-transparent to-slate-950" />
      <div className="relative w-full max-w-md rounded-2xl border border-slate-800/80 bg-clinical-900/90 p-8 shadow-2xl shadow-cyan-950/40 backdrop-blur">
        <div className="mb-8 text-center">
          <p className="font-display text-2xl font-semibold tracking-tight text-white">Create account</p>
          <p className="mt-1 text-sm text-clinical-muted">CardioSynth AI — research & demo use</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          {err && (
            <p className="rounded-lg border border-rose-900/50 bg-rose-950/30 px-3 py-2 text-sm text-rose-200">
              {err}
            </p>
          )}
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">
              Full name
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2.5 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2.5 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">
              Password (min 8)
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2.5 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
            />
          </div>
          <button
            type="submit"
            className="w-full rounded-lg bg-gradient-to-r from-cyan-600 to-cyan-500 py-2.5 text-sm font-semibold text-clinical-950 shadow-lg shadow-cyan-900/30 transition hover:from-cyan-500 hover:to-cyan-400"
          >
            Sign up
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-500">
          Already registered?{" "}
          <Link to="/login" className="font-medium text-cyan-400 hover:text-cyan-300">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
