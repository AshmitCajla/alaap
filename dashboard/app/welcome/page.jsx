"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight, BellRing, Bot, CalendarCheck, Camera, Check, Handshake, IndianRupee, Languages, MessageCircle, Phone,
  QrCode, Repeat, ShieldCheck, Sparkles, Store, Wand2,
} from "lucide-react";
import { API } from "../../lib/api";

const DEMOS = [["glow-salon", "Salon"], ["sharma-kirana", "Kirana"], ["vidya-coaching", "Coaching"]];
const FEATURES = [
  [Phone, "Answers every call", "Phone, WhatsApp, voice notes and your website, 24×7 — even when you're busy or closed."],
  [Languages, "Speaks like your customers", "Hindi, Punjabi, English and the mix people really speak, in a warm human voice."],
  [CalendarCheck, "Books and takes orders", "Checks real free slots and stock, reads it back, and saves only after a clear yes."],
  [IndianRupee, "Collects UPI payments", "Sends a payment link on WhatsApp and tells you the moment it's paid."],
  [Repeat, "Follows up for you", "Reminders, feedback requests, reorder nudges and win-back offers go out on their own."],
  [BellRing, "You stay in charge", "Hot leads and complaints reach your WhatsApp instantly. Every conversation is saved."],
];
const PLANS = [
  ["Starter", 999, "Salons, clinics, solo shops", ["Calls, WhatsApp & web chat", "Appointments & reminders", "100 call minutes"]],
  ["Pro", 2499, "Kirana, restaurants, busy clinics", ["Everything in Starter", "Orders + UPI payment links", "500 call minutes"]],
  ["Business", 5999, "Coaching, real estate, chains", ["Everything in Pro", "Lead scoring & follow-ups", "1,500 call minutes"]],
];
const FAQ = [
  ["Do my customers know it's an AI?", "Yes. Your assistant says so if asked and never pretends to be a person. Callers also hear that calls are recorded."],
  ["Will it make up prices or book wrong slots?", "No. It only quotes prices you gave it, checks real free slots and stock, reads everything back and saves only after the customer says yes."],
  ["What if it can't help?", "It takes the customer's number and sends you a WhatsApp right away, so you can call back."],
  ["Do I need to change my number?", "No. Keep your shop number and forward missed calls to Alaap with a one-time code. Or we give you a new number."],
  ["How do I change prices or timings?", "Just message it: \"Facial 900 kar do\" or \"kal shop band hai\". It updates itself."],
];

export default function Welcome() {
  const [demo, setDemo] = useState(DEMOS[0][0]);
  return (
    <div style={{ background: "var(--bg)" }}>
      <style>{`
        .lp { max-width: 1160px; margin: 0 auto; padding: 0 20px; }
        .lp-nav { display: flex; justify-content: space-between; align-items: center; padding: 16px 0; }
        .lp-top { background: radial-gradient(900px 500px at 10% -10%, var(--brand-soft), transparent 70%),
                  radial-gradient(700px 400px at 100% 0%, var(--accent-soft), transparent 65%); }
        .lp-hero { display: grid; grid-template-columns: 1.08fr .92fr; gap: 44px; align-items: center; padding: 30px 0 64px; }
        .lp-hero h1 { font-size: 54px; line-height: 1.06; margin: 14px 0 18px; letter-spacing: -.035em; font-weight: 800; }
        .lp-hero h1 em { font-style: normal; color: var(--brand); }
        .lp-hero p.lead { font-size: 19px; line-height: 1.6; color: var(--muted); margin: 0 0 26px; max-width: 560px; }
        .lp-trust { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 22px; font-size: 13.5px; color: var(--muted); }
        .lp-trust span { display: inline-flex; gap: 6px; align-items: center; }
        .lp-phone { background: var(--panel); border: 1px solid var(--line); border-radius: 28px; padding: 10px; box-shadow: var(--shadow-lg); }
        .lp-sec { padding: 72px 0; }
        .lp-sec h2 { font-size: 34px; margin: 0 0 10px; letter-spacing: -.025em; font-weight: 780; }
        .lp-sec .kicker { color: var(--brand); font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }
        .lp-sec p.intro { color: var(--muted); font-size: 17px; max-width: 640px; margin: 0 0 32px; }
        .lp-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .lp-feat .ico { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; background: var(--brand-soft); color: var(--brand); margin-bottom: 14px; }
        .lp-feat b { font-size: 16.5px; }
        .lp-step { display: flex; gap: 14px; }
        .lp-step .n { width: 36px; height: 36px; border-radius: 12px; background: var(--brand); color: #fff; display: grid; place-items: center; font-weight: 800; flex: none; }
        .lp-band { background: linear-gradient(135deg, #0b5f56, var(--brand) 55%, #17a593); color: #eafaf6; border-radius: 24px; padding: 44px; }
        .lp-band h2 { color: #fff; }
        .lp-faq details { border-bottom: 1px solid var(--line); padding: 16px 0; }
        .lp-faq summary { cursor: pointer; font-weight: 650; font-size: 16px; list-style: none; display: flex; justify-content: space-between; }
        .lp-faq summary::after { content: "+"; color: var(--brand); font-size: 20px; line-height: 1; }
        .lp-faq details[open] summary::after { content: "–"; }
        .lp-faq p { color: var(--muted); margin: 10px 0 0; }
        @media (max-width: 900px) {
          .lp-hero, .lp-3 { grid-template-columns: 1fr; } .lp-hero h1 { font-size: 38px; } .lp-sec { padding: 52px 0; }
          .lp-sec h2 { font-size: 27px; } .lp-band { padding: 28px 22px; } .lp-nav .hide-sm { display: none; }
        }
      `}</style>

      <div className="lp-top">
        <div className="lp">
          <nav className="lp-nav">
            <div className="row" style={{ gap: 9, fontWeight: 800, fontSize: 20 }}><span className="logo"><Bot size={18} /></span>Alaap</div>
            <div className="row" style={{ gap: 18 }}>
              <a href="#how" className="hide-sm" style={{ color: "var(--muted)" }}>How it works</a>
              <a href="#pricing" className="hide-sm" style={{ color: "var(--muted)" }}>Pricing</a>
              <Link href="/login" style={{ color: "var(--text)", fontWeight: 600 }}>Sign in</Link>
              <Link className="btn" href="/login?signup=1">Start free</Link>
            </div>
          </nav>

          <section className="lp-hero">
            <div>
              <span className="badge"><Sparkles size={13} />AI front desk for Indian shops</span>
              <h1>Har call ka jawab.<br /><em>Har customer ki booking.</em></h1>
              <p className="lead">Alaap answers your shop's calls and WhatsApp in Hindi, Punjabi and English — books appointments, takes orders,
                sends UPI links and follows up. For less than a day's wages a month.</p>
              <div className="row" style={{ gap: 12 }}>
                <Link className="btn big" href="/login?signup=1">Set up in 5 minutes <ArrowRight size={18} /></Link>
                <a className="btn big ghost" href="#done-for-you">We'll set it up for you</a>
              </div>
              <div className="lp-trust">
                <span><Check size={15} color="var(--good)" />14-day free trial</span>
                <span><Check size={15} color="var(--good)" />No card needed</span>
                <span><Check size={15} color="var(--good)" />Keep your number</span>
              </div>
            </div>
            <div>
              <div className="row" style={{ justifyContent: "center", marginBottom: 12 }}>
                <span className="small muted">Live demo — press <b>Call</b> and talk:</span>
                <div className="seg" style={{ margin: 0 }}>{DEMOS.map(([s, l]) => <button key={s} className={demo === s ? "on" : ""} onClick={() => setDemo(s)}>{l}</button>)}</div>
              </div>
              <div className="lp-phone">
                <iframe key={demo} title="Live demo" src={`${API}/c/${demo}?embed=1`} allow="microphone; autoplay"
                  style={{ width: "100%", height: 580, border: 0, borderRadius: 20, display: "block" }} />
              </div>
            </div>
          </section>
        </div>
      </div>

      <div className="lp">
        <section className="lp-sec" id="how">
          <div className="kicker">How it works</div>
          <h2>Live in five minutes</h2>
          <p className="intro">No app to install for you or your customers.</p>
          <div className="lp-3">
            {[[Camera, "Snap your rate card", "Take a photo of your menu or price list. Alaap reads the services, prices and timings — you just check them."],
              [Wand2, "Pick a voice and name", "Choose from natural Indian voices. Customers talk to \"Riya from Glow Salon\", not a robot."],
              [QrCode, "Share and go live", "Print the QR poster for your counter, forward missed calls, and add the link to WhatsApp and Google."]].map(([I, t, d], i) => (
              <div key={t} className="card lp-step"><div className="n">{i + 1}</div><div><b>{t}</b><p className="small muted" style={{ margin: "6px 0 0" }}>{d}</p></div></div>
            ))}
          </div>
        </section>

        <section className="lp-sec" style={{ paddingTop: 0 }}>
          <div className="kicker">What it does</div>
          <h2>Everything a good receptionist does</h2>
          <p className="intro">Without breaks, sick days or missed calls during rush hour.</p>
          <div className="lp-3 lp-feat">
            {FEATURES.map(([I, t, d]) => <div key={t} className="card"><div className="ico"><I size={21} /></div><b>{t}</b>
              <p className="small muted" style={{ margin: "6px 0 0" }}>{d}</p></div>)}
          </div>
        </section>

        <section className="lp-sec" id="done-for-you" style={{ paddingTop: 0 }}>
          <div className="lp-band">
            <div className="lp-3" style={{ gridTemplateColumns: "1.3fr 1fr", alignItems: "center" }}>
              <div>
                <span className="badge" style={{ background: "rgba(255,255,255,.16)", color: "#fff" }}><Handshake size={13} />Done for you</span>
                <h2 style={{ marginTop: 12 }}>Too busy? Send us your menu. We do the rest.</h2>
                <p style={{ fontSize: 17, opacity: .9, margin: 0 }}>WhatsApp a photo of your rate card. Our team sets up your assistant, gives you a phone number and sends you a
                  poster — usually the same day. You never open a dashboard unless you want to.</p>
              </div>
              <div className="stack" style={{ gap: 10 }}>
                {["Your own Alaap phone number", "Menu and prices set up by our team", "QR poster for your counter", "Change anything by just messaging us"].map((x) =>
                  <div key={x} className="row" style={{ gap: 10, fontWeight: 600 }}><Check size={18} />{x}</div>)}
              </div>
            </div>
          </div>
        </section>

        <section className="lp-sec" id="pricing" style={{ paddingTop: 0 }}>
          <div className="kicker">Pricing</div>
          <h2>Simple monthly plans</h2>
          <p className="intro">Every plan starts with a 14-day free trial. Pay by UPI, card or netbanking. Cancel any time.</p>
          <div className="lp-3">
            {PLANS.map(([n, p, who, what], i) => (
              <div key={n} className={"card" + (i === 1 ? " hl" : "")} style={{ display: "flex", flexDirection: "column" }}>
                <div className="row between"><b style={{ fontSize: 18 }}>{n}</b>{i === 1 && <span className="badge warn">Most popular</span>}</div>
                <div className="small muted">{who}</div>
                <div style={{ margin: "16px 0 14px" }}><span style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-.03em" }}>₹{p.toLocaleString("en-IN")}</span><span className="muted">/month</span></div>
                <div className="stack" style={{ gap: 8, flex: 1, marginBottom: 20 }}>
                  {what.map((x) => <div key={x} className="row small" style={{ gap: 8 }}><Check size={16} color="var(--good)" />{x}</div>)}</div>
                <Link className={"btn block" + (i === 1 ? "" : " ghost")} href="/login?signup=1">Start free trial</Link>
              </div>
            ))}
          </div>
        </section>

        <section className="lp-sec lp-faq" style={{ paddingTop: 0, maxWidth: 780 }}>
          <div className="kicker">Questions</div>
          <h2>Owners usually ask</h2>
          {FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}
        </section>

        <section className="lp-sec" style={{ textAlign: "center", paddingTop: 0 }}>
          <div className="card hl" style={{ padding: "44px 24px" }}>
            <Store size={30} color="var(--brand)" />
            <h2 style={{ margin: "10px 0 8px" }}>Stop losing customers to missed calls</h2>
            <p className="muted" style={{ marginBottom: 22 }}>Set it up yourself in five minutes, or let us do it for you.</p>
            <div className="row" style={{ justifyContent: "center", gap: 12 }}>
              <Link className="btn big" href="/login?signup=1">Start your free trial <ArrowRight size={18} /></Link>
            </div>
          </div>
        </section>

        <footer className="row between small muted" style={{ padding: "26px 0 40px", borderTop: "1px solid var(--line)" }}>
          <div className="row" style={{ gap: 8 }}><span className="logo" style={{ width: 24, height: 24 }}><Bot size={14} /></span>Alaap · Made in Patiala</div>
          <div className="row" style={{ gap: 6 }}><ShieldCheck size={14} />Voice by Gnani AI · Callers are told it's an AI assistant and that calls are recorded.</div>
        </footer>
      </div>
    </div>
  );
}
