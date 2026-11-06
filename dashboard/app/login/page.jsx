"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, setToken } from "../../lib/api";

const KINDS = [
  ["salon", "Salon / parlour"], ["clinic", "Clinic / dentist / physio"], ["kirana", "Kirana store"],
  ["restaurant", "Restaurant / cloud kitchen"], ["pharmacy", "Pharmacy"], ["coaching", "Coaching centre"],
  ["real_estate", "Real estate"], ["gym", "Gym"], ["home_services", "Home services (AC, plumbing…)"],
];

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState("login");
  useEffect(() => { if (new URLSearchParams(window.location.search).get("signup")) { setMode("signup"); setForm((f) => ({ ...f, email: "", password: "" })); } }, []);
  const [form, setForm] = useState({ email: "owner@glow.demo", password: "demo1234", kind: "salon" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await api(mode === "login" ? "/api/auth/login" : "/api/auth/signup", { method: "POST", body: form });
      setToken(r.token);
      router.replace(mode === "login" ? "/" : "/setup");
    } catch (err) { setError(err.message); }
    setBusy(false);
  }

  return (
    <div className="login">
      <h1 style={{ color: "var(--brand)" }}><a href="/welcome">Alaap</a></h1>
      <p className="sub">A front desk that never misses a call.</p>
      <div className="tabs">
        <button className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Sign in</button>
        <button className={mode === "signup" ? "on" : ""} onClick={() => setMode("signup")}>New business</button>
      </div>
      <form className="card" onSubmit={submit}>
        {mode === "signup" && (
          <>
            <label>Business name<input required value={form.business_name || ""} onChange={set("business_name")} /></label>
            <label>Type of business
              <select value={form.kind} onChange={set("kind")}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            </label>
            <label>City<input required value={form.city || ""} onChange={set("city")} /></label>
            <label>Your name<input required value={form.owner_name || ""} onChange={set("owner_name")} /></label>
            <label>Your mobile (gets WhatsApp alerts)<input required value={form.owner_phone || ""} onChange={set("owner_phone")} /></label>
          </>
        )}
        <label>Email<input type="email" required value={form.email} onChange={set("email")} /></label>
        <label>Password<input type="password" required value={form.password} onChange={set("password")} /></label>
        {error && <div className="err">{error}</div>}
        <button className="btn" disabled={busy}>{mode === "login" ? "Sign in" : "Create my front desk"}</button>
        {mode === "login" && (
          <p className="muted small">Demo logins (password demo1234): owner@glow.demo, owner@kirana.demo, owner@coaching.demo</p>
        )}
      </form>
    </div>
  );
}
