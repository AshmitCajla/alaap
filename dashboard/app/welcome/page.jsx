"use client";

import Link from "next/link";
import { useState } from "react";
import { API } from "../../lib/api";

const DEMOS = [["glow-salon", "Salon"], ["sharma-kirana", "Kirana"], ["vidya-coaching", "Coaching"]];
const FEATURES = [
  ["📞", "Answers every call", "Phone, WhatsApp voice notes, chat and your website — 24×7, even when you're busy or closed."],
  ["🗣️", "Speaks like your customers", "Hindi, Punjabi, English and the mix people actually speak, in a warm human voice."],
  ["📅", "Books and takes orders", "Checks real free slots and stock, reads everything back, and saves only after a clear yes."],
  ["💸", "Collects UPI payments", "Sends a payment link on WhatsApp and tells you when it's paid."],
  ["🔁", "Follows up for you", "Reminders, feedback, reorder nudges and win-back messages go out on their own."],
  ["🎙️", "You stay in charge", "Every call has a transcript. Change prices or timings by just telling Alaap."],
];
const PLANS = [["Starter", 999, "Salons, clinics", "Appointments, enquiries, complaints · 100 call min"],
  ["Pro", 2499, "Kirana, restaurants, busy clinics", "+ Orders, UPI payments, order status, follow-ups · 500 min"],
  ["Business", 5999, "Coaching, real estate, chains", "+ Lead scoring, everything else · 1,500 min"]];

export default function Welcome() {
  const [demo, setDemo] = useState(DEMOS[0][0]);
  return (
    <div style={{ background: "var(--bg)" }}>
      <style>{`
        .lp { max-width: 1120px; margin: 0 auto; padding: 0 20px; }
        .lp-nav { display: flex; justify-content: space-between; align-items: center; padding: 18px 0; }
        .lp-hero { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 36px; align-items: center; padding: 28px 0 56px; }
        .lp-hero h1 { font-size: 46px; line-height: 1.1; margin: 0 0 14px; letter-spacing: -0.5px; }
        .lp-hero p.lead { font-size: 19px; color: var(--muted); margin: 0 0 22px; }
        .lp-sec { padding: 46px 0; border-top: 1px solid var(--line); }
        .lp-sec h2 { font-size: 28px; margin: 0 0 18px; }
        .lp-feat { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
        .lp-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; counter-reset: s; }
        .lp-steps .card::before { counter-increment: s; content: counter(s); display: inline-grid; place-items: center; width: 30px;
          height: 30px; border-radius: 50%; background: var(--brand); color: #fff; font-weight: 700; margin-bottom: 8px; }
        @media (max-width: 860px) { .lp-hero, .lp-feat, .lp-steps { grid-template-columns: 1fr; } .lp-hero h1 { font-size: 34px; } }
      `}</style>
      <div className="lp">
        <nav className="lp-nav">
          <b style={{ fontSize: 22, color: "var(--brand)" }}>Alaap</b>
          <div className="row"><Link href="/login">Sign in</Link><Link className="btn" href="/login?signup=1">Start free trial</Link></div>
        </nav>

        <section className="lp-hero">
          <div>
            <div className="pill" style={{ marginBottom: 12 }}>AI front desk for Indian businesses</div>
            <h1>Har call ka jawab.<br />Har customer ki booking.</h1>
            <p className="lead">Alaap answers your shop's calls and WhatsApp in Hindi, Punjabi and English — books appointments,
              takes orders, sends UPI links and follows up. For less than a day's wages a month.</p>
            <div className="row">
              <Link className="btn" href="/login?signup=1" style={{ padding: "12px 20px", fontSize: 16 }}>Set up in 5 minutes →</Link>
              <span className="small muted">14-day free trial · no card needed</span>
            </div>
            <p className="small muted" style={{ marginTop: 18 }}>Try the live demo → press <b>📞 Call</b> and talk like a customer.</p>
          </div>
          <div>
            <div className="tabs" style={{ justifyContent: "center" }}>
              {DEMOS.map(([s, l]) => <button key={s} className={demo === s ? "on" : ""} onClick={() => setDemo(s)}>{l}</button>)}
            </div>
            <iframe key={demo} title="Live demo" src={`${API}/c/${demo}?embed=1`} allow="microphone; autoplay"
              style={{ width: "100%", height: 600, border: 0, borderRadius: 20, boxShadow: "0 18px 50px rgba(0,0,0,.18)" }} />
          </div>
        </section>

        <section className="lp-sec">
          <h2>Live in five minutes</h2>
          <div className="lp-steps">
            <div className="card"><b>Snap your rate card</b><p className="small muted">Alaap reads your menu or price list photo —
              services, prices, timings — and you just check it.</p></div>
            <div className="card"><b>Pick a voice</b><p className="small muted">Choose from 13 natural Indian voices and give your
              assistant a name.</p></div>
            <div className="card"><b>Share and go live</b><p className="small muted">Print the QR poster for your counter, forward
              missed calls, add it to WhatsApp and Google.</p></div>
          </div>
        </section>

        <section className="lp-sec">
          <h2>Everything a good receptionist does</h2>
          <div className="lp-feat">
            {FEATURES.map(([i, t, d]) => <div key={t} className="card"><div style={{ fontSize: 26 }}>{i}</div><b>{t}</b>
              <p className="small muted" style={{ marginBottom: 0 }}>{d}</p></div>)}
          </div>
        </section>

        <section className="lp-sec">
          <h2>Simple monthly pricing</h2>
          <div className="lp-feat">
            {PLANS.map(([n, p, who, what], i) => (
              <div key={n} className={"card" + (i === 1 ? " kpi star" : "")}>
                <b style={{ fontSize: 18 }}>{n}</b>
                <div style={{ fontSize: 30, fontWeight: 700, margin: "6px 0" }}>₹{p.toLocaleString("en-IN")}<span className="small muted">/month</span></div>
                <div className="small"><b>{who}</b></div>
                <p className="small muted">{what}</p>
                <Link className="btn" href="/login?signup=1">Start free</Link>
              </div>
            ))}
          </div>
        </section>

        <section className="lp-sec" style={{ textAlign: "center" }}>
          <h2>Stop losing customers to missed calls</h2>
          <Link className="btn" href="/login?signup=1" style={{ padding: "12px 22px", fontSize: 16 }}>Start your free trial</Link>
          <p className="small muted" style={{ marginTop: 28 }}>Voice by Gnani AI (Prisma speech recognition, Timbre voices). Alaap always tells
            callers it's an AI assistant, and calls are recorded with notice.</p>
        </section>
      </div>
    </div>
  );
}
