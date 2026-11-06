"use client";

import { useEffect, useRef, useState } from "react";
import { API, api, getToken } from "../../../lib/api";
import { useMe } from "../../../lib/Shell";
import VoicePicker from "../../../lib/VoicePicker";

const STEPS = ["Teach", "Check", "Voice", "Try it", "Go live"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function Stepper({ step, setStep }) {
  return (
    <div className="tabs" style={{ marginBottom: 20 }}>
      {STEPS.map((s, i) => (
        <button key={s} className={step === i ? "on" : ""} onClick={() => setStep(i)}>{i + 1}. {s}</button>
      ))}
    </div>
  );
}

/* Step 1: photo / paste / website -> extracted data */
function Teach({ onData }) {
  const [mode, setMode] = useState("photo");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const file = useRef(null);

  async function readPhoto(f) {
    setBusy(true); setErr(null);
    try {
      const fd = new FormData(); fd.append("photo", f);
      const r = await fetch(API + "/api/setup/import-photo", { method: "POST", body: fd,
        headers: { Authorization: `Bearer ${getToken()}` } });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || r.statusText);
      onData(data);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  async function readText() {
    setBusy(true); setErr(null);
    try { onData(await api("/api/setup/import", { method: "POST", body: mode === "url" ? { url } : { text } })); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  }

  return (
    <div className="card" style={{ maxWidth: 680 }}>
      <h2 style={{ marginTop: 0 }}>Teach Alaap your business in one minute</h2>
      <p className="small muted">Alaap reads your rate card, menu or price list and fills in services, prices, timings and
        common questions. You check everything on the next step before it's saved.</p>
      <div className="tabs">
        <button className={mode === "photo" ? "on" : ""} onClick={() => setMode("photo")}>📷 Photo of rate card / menu</button>
        <button className={mode === "text" ? "on" : ""} onClick={() => setMode("text")}>📝 Paste price list</button>
        <button className={mode === "url" ? "on" : ""} onClick={() => setMode("url")}>🌐 Website</button>
      </div>
      {mode === "photo" && (
        <div className="card" style={{ textAlign: "center", borderStyle: "dashed", padding: 28, cursor: "pointer" }}
          onClick={() => file.current?.click()}
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); e.dataTransfer.files[0] && readPhoto(e.dataTransfer.files[0]); }}>
          <div style={{ fontSize: 36 }}>📷</div>
          <b>{busy ? "Reading your photo…" : "Tap to take or upload a photo"}</b>
          <div className="small muted">Rate card on the wall, printed menu, handwritten price list — all fine.</div>
          <input ref={file} type="file" accept="image/*" capture="environment" style={{ display: "none" }}
            onChange={(e) => e.target.files[0] && readPhoto(e.target.files[0])} />
        </div>
      )}
      {mode === "text" && (
        <>
          <textarea rows={9} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={"Paste anything, e.g.\nCutting 150, Shave 80, Facial 400-900\nTiming subah 9 se raat 9, Tuesday band\nStaff: Sunny (cutting), Bunty (facial)\nGPay/Paytm chalta hai"} />
          <button className="btn" style={{ marginTop: 10 }} disabled={busy || !text.trim()} onClick={readText}>
            {busy ? "Reading…" : "Read it"}</button>
        </>
      )}
      {mode === "url" && (
        <>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="yourshop.com or a menu page link" />
          <button className="btn" style={{ marginTop: 10 }} disabled={busy || !url.trim()} onClick={readText}>
            {busy ? "Reading the website…" : "Read website"}</button>
        </>
      )}
      {err && <div className="err">{err}</div>}
    </div>
  );
}

/* Step 2: review what was understood */
function Check({ data, setData, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  if (!data) return <div className="card muted">Nothing read yet. Go back to step 1, or skip: Alaap already has sample
    data for your kind of business that you can edit in Settings.</div>;
  const upd = (key, i, field, v) => setData({ ...data, [key]: data[key].map((x, j) => j === i ? { ...x, [field]: v } : x) });
  const del = (key, i) => setData({ ...data, [key]: data[key].filter((_, j) => j !== i) });
  const num = (v) => (v === "" ? "" : Number(v));

  async function save() {
    setBusy(true); setErr(null);
    try { await api("/api/setup/apply", { method: "POST", body: data }); onSaved(); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  }

  return (
    <div style={{ maxWidth: 820 }}>
      <p className="sub">Here's what Alaap understood. Fix anything that's off, then save. Prices here are what Alaap will
        tell customers.</p>
      {data.services.length > 0 && (<>
        <h2>Services (bookable)</h2>
        <div className="scroll"><table><thead><tr><th>Service</th><th>Price ₹</th><th>Minutes</th><th /></tr></thead><tbody>
          {data.services.map((x, i) => <tr key={i}>
            <td><input value={x.name} onChange={(e) => upd("services", i, "name", e.target.value)} /></td>
            <td style={{ width: 110 }}><input type="number" value={x.price_inr} onChange={(e) => upd("services", i, "price_inr", num(e.target.value))} /></td>
            <td style={{ width: 100 }}><input type="number" value={x.duration_min} onChange={(e) => upd("services", i, "duration_min", num(e.target.value))} /></td>
            <td><button className="btn ghost small" onClick={() => del("services", i)}>Remove</button></td></tr>)}
        </tbody></table></div></>)}
      {data.products.length > 0 && (<>
        <h2>Items (orderable)</h2>
        <div className="scroll"><table><thead><tr><th>Item</th><th>Price ₹</th><th>Unit</th><th>Other names customers say</th><th /></tr></thead><tbody>
          {data.products.map((x, i) => <tr key={i}>
            <td><input value={x.name} onChange={(e) => upd("products", i, "name", e.target.value)} /></td>
            <td style={{ width: 100 }}><input type="number" value={x.price_inr} onChange={(e) => upd("products", i, "price_inr", num(e.target.value))} /></td>
            <td style={{ width: 110 }}><input value={x.unit} onChange={(e) => upd("products", i, "unit", e.target.value)} /></td>
            <td><input value={x.aliases || ""} onChange={(e) => upd("products", i, "aliases", e.target.value)} /></td>
            <td><button className="btn ghost small" onClick={() => del("products", i)}>Remove</button></td></tr>)}
        </tbody></table></div></>)}
      {data.staff.length > 0 && (<>
        <h2>Staff</h2>
        <div className="row">{data.staff.map((x, i) => <span key={i} className="pill" style={{ fontSize: 14 }}>{x.name}
          {x.services.length ? ` · ${x.services.join(", ")}` : ""} <a href="#" onClick={(e) => { e.preventDefault(); del("staff", i); }}>✕</a></span>)}</div></>)}
      {data.hours.length > 0 && (<>
        <h2>Timings</h2>
        <div className="row">{DAYS.map((d, i) => { const h = data.hours.find((x) => x.weekday === i);
          return <span key={d} className={"pill " + (h ? "" : "grey")} style={{ fontSize: 14 }}>{d} {h ? `${h.opens}–${h.closes}` : "closed"}</span>; })}</div></>)}
      {data.faqs.length > 0 && (<>
        <h2>Things Alaap will tell customers</h2>
        {data.faqs.map((x, i) => <div key={i} className="row" style={{ marginBottom: 6, flexWrap: "nowrap" }}>
          <input style={{ width: 200 }} value={x.question} onChange={(e) => upd("faqs", i, "question", e.target.value)} />
          <input value={x.answer} onChange={(e) => upd("faqs", i, "answer", e.target.value)} />
          <button className="btn ghost small" onClick={() => del("faqs", i)}>✕</button></div>)}</>)}
      {data.about && <p className="small"><b>About:</b> {data.about}</p>}
      {err && <div className="err">{err}</div>}
      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn" disabled={busy} onClick={save}>{busy ? "Saving…" : "Looks right — save"}</button>
        <span className="small muted">Sample items from signup are switched off when you save.</span>
      </div>
    </div>
  );
}

function Voice({ onDone }) {
  const [v, setV] = useState(null);
  useEffect(() => { api("/api/settings").then((s) => setV({ assistant_name: s.business.assistant_name, voice: s.business.voice || "Shivani", speech_speed: s.business.speech_speed || 1 })); }, []);
  if (!v) return <div className="muted">Loading…</div>;
  return (
    <div className="card" style={{ maxWidth: 720 }}>
      <VoicePicker value={v} onChange={setV} />
      <button className="btn" onClick={() => api("/api/settings/business", { method: "PUT", body: v }).then(onDone)}>Save and continue</button>
    </div>
  );
}

function Try({ slug, onDone }) {
  return (
    <div className="split" style={{ gridTemplateColumns: "1fr 440px" }}>
      <div>
        <h2 style={{ marginTop: 0 }}>Call your own front desk</h2>
        <p className="small">Press <b>📞 Call</b> and talk like a customer. Try:</p>
        <ul className="small">
          <li>"Kal shaam ka slot hai kya?" / "Do packet atta bhej do"</li>
          <li>"Rate kitna hai?" / "Parking hai?"</li>
          <li>Interrupt it mid-sentence — it stops and listens.</li>
        </ul>
        <p className="small muted">Something wrong? Fix it in Settings, or just tell Ask Alaap ("Facial ka rate 900 kar do").</p>
        <button className="btn" onClick={onDone}>It works — next</button>
      </div>
      <iframe title="Your assistant" src={`${API}/c/${slug}?embed=1`} allow="microphone; autoplay"
        style={{ width: "100%", height: 660, border: 0, borderRadius: 16 }} />
    </div>
  );
}

export default function Setup() {
  const me = useMe();
  const [step, setStep] = useState(0);
  const [data, setData] = useState(null);
  return (
    <>
      <h1>Set up {me.business.name}</h1>
      <p className="sub">Five quick steps. Alaap already works with sample data, so you can stop anytime.</p>
      <Stepper step={step} setStep={setStep} />
      {step === 0 && <><Teach onData={(d) => { setData(d); setStep(1); }} />
        <p className="small" style={{ marginTop: 12 }}><a href="#" onClick={(e) => { e.preventDefault(); setStep(2); }}>Skip — I'll edit prices later</a></p></>}
      {step === 1 && <Check data={data} setData={setData} onSaved={() => setStep(2)} />}
      {step === 2 && <Voice onDone={() => setStep(3)} />}
      {step === 3 && <Try slug={me.business.slug} onDone={() => setStep(4)} />}
      {step === 4 && (
        <div className="card" style={{ maxWidth: 680 }}>
          <h2 style={{ marginTop: 0 }}>🎉 You're live</h2>
          <p>Customers can now talk to {me.business.name} any time. Put it where they'll find it:</p>
          <ul>
            <li><b>Shop counter:</b> print the QR poster.</li>
            <li><b>Phone:</b> forward missed calls with a one-time code.</li>
            <li><b>WhatsApp / Instagram / Google:</b> share your page link.</li>
          </ul>
          <a className="btn" href="/share" style={{ display: "inline-block" }}>Open the share kit</a>
        </div>
      )}
    </>
  );
}
