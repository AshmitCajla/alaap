"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bot, Check } from "lucide-react";
import { api, setToken } from "../../lib/api";

const KINDS = [
  ["salon", "Salon / parlour"], ["clinic", "Clinic / dentist / physio"], ["kirana", "Kirana store"],
  ["restaurant", "Restaurant / cloud kitchen"], ["pharmacy", "Pharmacy"], ["coaching", "Coaching centre"],
  ["real_estate", "Real estate"], ["gym", "Gym"], ["home_services", "Home services (AC, plumbing…)"],
];

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState("login");
  const [dev, setDev] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", kind: "salon" });
  useEffect(() => {
    const local = window.location.hostname === "localhost";
    setDev(local);
    if (new URLSearchParams(window.location.search).get("signup")) setMode("signup");
    else if (local) setForm((f) => ({ ...f, email: "owner@glow.demo", password: "demo1234" }));
  }, []);
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
    <div className="auth">
      <div className="art">
        <Link href="/welcome" className="row" style={{ gap: 10, color: "#fff", fontWeight: 800, fontSize: 20 }}>
          <span className="logo" style={{ background: "rgba(255,255,255,.18)" }}><Bot size={18} /></span>Alaap</Link>
        <div>
          <h2>Your front desk that never misses a call.</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 16 }}>
            {["Answers calls & WhatsApp in Hindi, Punjabi and English", "Books, takes orders and sends UPI links",
              "Sends you hot leads and complaints instantly"].map((x) => (
              <li key={x} className="row" style={{ gap: 10, flexWrap: "nowrap" }}><Check size={18} style={{ flex: "none" }} />{x}</li>))}
          </ul>
        </div>
        <div className="small" style={{ opacity: .8 }}>14-day free trial · No card needed · Cancel any time</div>
      </div>

      <div className="form">
        <div>
          <Link href="/welcome" className="row show-sm" style={{ gap: 9, fontWeight: 800, fontSize: 20, color: "var(--text)", marginBottom: 20 }}>
            <span className="logo"><Bot size={18} /></span>Alaap</Link>
          <h1 style={{ marginBottom: 6 }}>{mode === "login" ? "Welcome back" : "Start your free trial"}</h1>
          <p className="sub" style={{ marginBottom: 22 }}>{mode === "login" ? "Sign in to see your bookings, orders and conversations." : "Your assistant is ready in about five minutes."}</p>
          <div className="seg" style={{ marginBottom: 18 }}>
            <button className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Sign in</button>
            <button className={mode === "signup" ? "on" : ""} onClick={() => setMode("signup")}>New business</button>
          </div>
          <form onSubmit={submit}>
            {mode === "signup" && (
              <>
                <label>Business name<input required value={form.business_name || ""} onChange={set("business_name")} placeholder="e.g. Glow Unisex Salon" /></label>
                <div className="grid-2" style={{ gap: 12 }}>
                  <label>Type of business
                    <select value={form.kind} onChange={set("kind")}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                  </label>
                  <label>City<input required value={form.city || ""} onChange={set("city")} placeholder="Patiala" /></label>
                </div>
                <div className="grid-2" style={{ gap: 12 }}>
                  <label>Your name<input required value={form.owner_name || ""} onChange={set("owner_name")} /></label>
                  <label>Your mobile<input required inputMode="numeric" value={form.owner_phone || ""} onChange={set("owner_phone")} placeholder="98xxxxxxxx" />
                    <div className="field-hint">Bookings and alerts come here on WhatsApp</div></label>
                </div>
              </>
            )}
            <label>Email<input type="email" autoComplete="email" required value={form.email} onChange={set("email")} /></label>
            <label>Password<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required value={form.password} onChange={set("password")} />
              {mode === "signup" && <div className="field-hint">At least 8 characters</div>}</label>
            {error && <div className="callout bad" style={{ marginBottom: 12 }}>{error}</div>}
            <button className="btn block big" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create my front desk"}</button>
          </form>
          {mode === "login" && <p className="small muted" style={{ marginTop: 16 }}>Forgot your password? Message the Alaap team on WhatsApp and we'll reset it.</p>}
          {dev && mode === "login" && <p className="tiny faint">Demo logins (password demo1234): owner@glow.demo · owner@kirana.demo · owner@coaching.demo</p>}
        </div>
      </div>
    </div>
  );
}
