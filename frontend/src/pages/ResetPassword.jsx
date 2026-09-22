import { useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client.js";

function formatApiDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((x) => (typeof x === "string" ? x : x?.msg || JSON.stringify(x))).join(" ");
  }
  return String(detail?.message || JSON.stringify(detail));
}

export default function ResetPassword() {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busyForgot, setBusyForgot] = useState(false);
  const [busyReset, setBusyReset] = useState(false);
  const [info, setInfo] = useState("");
  const [err, setErr] = useState("");

  async function requestReset(e) {
    e.preventDefault();
    setErr("");
    setInfo("");
    if (!email.trim()) {
      setErr("Email is required.");
      return;
    }
    setBusyForgot(true);
    try {
      const { data } = await client.post("/auth/forgot-password", { email: email.trim() });
      setInfo(data?.message || "Request submitted.");
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(formatApiDetail(d) || "Request failed.");
    } finally {
      setBusyForgot(false);
    }
  }

  async function submitNewPassword(e) {
    e.preventDefault();
    setErr("");
    setInfo("");
    setBusyReset(true);
    try {
      const { data } = await client.post("/auth/reset-password", {
        email: email.trim(),
        token: token.trim(),
        new_password: newPassword,
      });
      setInfo(data?.message || "Password updated.");
      setToken("");
      setNewPassword("");
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(formatApiDetail(d) || "Reset failed.");
    } finally {
      setBusyReset(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-clinical-950 bg-grid px-4">
      <div className="absolute inset-0 bg-gradient-to-br from-cyan-950/20 via-transparent to-slate-950" />
      <div className="relative w-full max-w-md rounded-2xl border border-slate-800/80 bg-clinical-900/90 p-8 shadow-2xl shadow-cyan-950/40 backdrop-blur">
        <div className="mb-6 text-center">
          <p className="font-display text-2xl font-semibold tracking-tight text-white">CardioSynth AI</p>
          <p className="mt-1 text-sm text-clinical-muted">Reset your password</p>
        </div>
        {info && (
          <p className="mb-4 rounded-lg border border-emerald-900/50 bg-emerald-950/30 px-3 py-2 text-sm text-emerald-200">
            {info}
          </p>
        )}
        {err && (
          <p className="mb-4 rounded-lg border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-sm text-amber-200">
            {err}
          </p>
        )}
        <form onSubmit={requestReset} className="space-y-4 border-b border-slate-800/80 pb-6">
          <p className="text-xs text-slate-500">
            Enter your email to request a reset code (in development, the code is printed in the server log).
          </p>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2.5 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
            />
          </div>
          <button
            type="submit"
            disabled={busyForgot}
            className="w-full rounded-lg border border-slate-600 bg-clinical-850 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-slate-800/80 disabled:opacity-50"
          >
            {busyForgot ? "Sending…" : "Request reset code"}
          </button>
        </form>
        <form onSubmit={submitNewPassword} className="mt-6 space-y-4">
          <p className="text-xs text-slate-500">Paste the token from the server log and choose a new password.</p>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">Token</label>
            <input
              type="text"
              autoComplete="one-time-code"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2.5 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
              placeholder="From server log"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">
              New password
            </label>
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-clinical-850 px-3 py-2.5 text-sm text-white outline-none ring-cyan-500/40 focus:ring-2"
            />
          </div>
          <button
            type="submit"
            disabled={busyReset || !email.trim() || !token.trim() || newPassword.length < 8}
            className="w-full rounded-lg bg-gradient-to-r from-cyan-600 to-cyan-500 py-2.5 text-sm font-semibold text-clinical-950 shadow-lg shadow-cyan-900/30 transition hover:from-cyan-500 hover:to-cyan-400 disabled:opacity-50"
          >
            {busyReset ? "Updating…" : "Set new password"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-500">
          <Link to="/login" className="font-medium text-cyan-400 hover:text-cyan-300">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
