"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { opsApi, setOpsToken } from "../../../lib/ops";

export default function OpsLogin() {
  const router = useRouter();
  const dev = typeof window !== "undefined" && window.location.hostname === "localhost";
  const [form, setForm] = useState({ email: dev ? "team@alaap.dev" : "", password: dev ? "demo1234" : "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await opsApi("/auth/login", { method: "POST", body: form });
      setOpsToken(r.token);
      router.replace("/ops");
    } catch (err) { setError(err.message); }
    setBusy(false);
  }

  return (
    <div className="login">
      <h1 style={{ color: "var(--brand)" }}>Alaap</h1>
      <p className="sub">Team console: set up shops, give them numbers, watch usage.</p>
      <form className="card" onSubmit={submit}>
        <label>Email<input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Password<input required type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        {error && <div className="err">{error}</div>}
        <button className="btn" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      <p className="small muted">Team logins are made with <code>python -m alaap.admin create-operator EMAIL</code>.</p>
    </div>
  );
}
