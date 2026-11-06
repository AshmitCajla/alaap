"use client";

import { useEffect, useState } from "react";
import { API, api } from "../../../lib/api";
import { useMe } from "../../../lib/Shell";
import VoicePicker from "../../../lib/VoicePicker";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const TABS = ["Business", "Voice & assistant", "Skills", "Hours", "Services & staff", "Catalog & delivery", "FAQs", "Channels", "Account & privacy"];

function AccountTab() {
  const [pw, setPw] = useState({ current: "", new: "" });
  const [msg, setMsg] = useState(null);
  const change = () => api("/api/me/password", { method: "PUT", body: pw })
    .then(() => { setMsg("Password changed ✓"); setPw({ current: "", new: "" }); }).catch((e) => setMsg(e.message));
  const wipe = () => {
    if (!confirm("Delete every call and chat transcript for your business? Bookings and orders stay. This can't be undone.")) return;
    api("/api/data/conversations", { method: "DELETE" }).then((r) => setMsg(`Deleted ${r.deleted} conversations ✓`)).catch((e) => setMsg(e.message));
  };
  return (
    <div className="card" style={{ maxWidth: 640 }}>
      <h2 style={{ marginTop: 0 }}>Change password</h2>
      <label>Current password<input type="password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></label>
      <label>New password (8+ characters)<input type="password" value={pw.new} onChange={(e) => setPw({ ...pw, new: e.target.value })} /></label>
      <button className="btn" disabled={!pw.current || pw.new.length < 8} onClick={change}>Change password</button>
      <h2>Privacy</h2>
      <p className="small">Callers hear that the call is recorded. Transcripts are deleted automatically after the retention period
        set by your Alaap provider. You can also delete all of them now.</p>
      <button className="btn ghost" style={{ color: "var(--bad)" }} onClick={wipe}>Delete all transcripts</button>
      {msg && <p className="small">{msg}</p>}
    </div>
  );
}
const LANGS = [["hi-IN", "Hindi"], ["pa-IN", "Punjabi"], ["en-IN", "English"], ["ta-IN", "Tamil"], ["te-IN", "Telugu"],
  ["bn-IN", "Bengali"], ["mr-IN", "Marathi"], ["gu-IN", "Gujarati"], ["kn-IN", "Kannada"], ["ml-IN", "Malayalam"]];
function VoiceTab({ b, setS, s, save }) {
  const value = { assistant_name: b.assistant_name, voice: b.voice, speech_speed: b.speech_speed };
  return (
    <div className="card" style={{ maxWidth: 720 }}>
      <VoicePicker value={value} onChange={(v) => setS({ ...s, business: { ...b, ...v } })} />
      <button className="btn" onClick={() => save("/api/settings/business", value)}>Save</button>
    </div>
  );
}

export default function Settings() {
  const me = useMe();
  const [s, setS] = useState(null);
  const [tab, setTab] = useState("Business");
  const [msg, setMsg] = useState(null);

  useEffect(() => { api("/api/settings").then(setS); }, []);
  if (!s) return <div className="muted">Loading…</div>;

  const save = async (path, body) => {
    setMsg("Saving…");
    try { setS(await api(path, { method: "PUT", body })); setMsg("Saved ✓"); }
    catch (e) { setMsg("Error: " + e.message); }
    setTimeout(() => setMsg(null), 2500);
  };
  const b = s.business;
  const setB = (k) => (e) => setS({ ...s, business: { ...b, [k]: e.target.value } });
  const setList = (k) => (rows) => setS({ ...s, [k]: rows });
  const skills = new Set(b.skills.split(","));
  const planSkills = new Set(me.plans[b.plan]?.skills || []);

  return (
    <>
      <h1>Settings</h1>
      <p className="sub">Alaap answers only from what's here, so keep prices and hours up to date.</p>
      <div className="tabs">{TABS.map((t) => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t}</button>)}</div>
      {msg && <div className="pill" style={{ marginBottom: 12 }}>{msg}</div>}

      {tab === "Business" && (
        <div className="card" style={{ maxWidth: 640 }}>
          {[["name", "Business name"], ["phone", "Public phone"], ["address", "Address"], ["city", "City"],
            ["languages", "Languages spoken (first one sets the greeting)"], ["owner_name", "Owner name"],
            ["owner_phone", "Owner mobile (WhatsApp alerts and owner commands)"]].map(([k, l]) => (
            <label key={k}>{l}<input value={b[k] || ""} onChange={setB(k)} /></label>
          ))}
          <label>About (Alaap uses this to answer questions)<textarea rows={3} value={b.about || ""} onChange={setB("about")} /></label>
          <label>Owner's language (daily voice summary)
            <select value={b.owner_language} onChange={setB("owner_language")}>{LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <button className="btn" onClick={() => save("/api/settings/business", b)}>Save</button>
        </div>
      )}

      {tab === "Voice & assistant" && <VoiceTab b={b} s={s} setS={setS} save={save} />}

      {tab === "Account & privacy" && <AccountTab />}

      {tab === "Skills" && (
        <div className="card" style={{ maxWidth: 640 }}>
          <p className="small muted" style={{ marginTop: 0 }}>Your plan: <b style={{ textTransform: "capitalize" }}>{b.plan}</b>. Skills outside the plan stay off.</p>
          {Object.entries(me.all_skills).map(([k, label]) => (
            <label key={k} className="row" style={{ color: "var(--text)", fontSize: 15 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={skills.has(k)} disabled={!planSkills.has(k)}
                onChange={(e) => { const n = new Set(skills); e.target.checked ? n.add(k) : n.delete(k); setS({ ...s, business: { ...b, skills: [...n].join(",") } }); }} />
              {label} {!planSkills.has(k) && <span className="pill grey">upgrade</span>}
            </label>
          ))}
          <button className="btn" onClick={() => save("/api/settings/business", { skills: b.skills })}>Save</button>
        </div>
      )}

      {tab === "Hours" && (
        <>
          <div className="card" style={{ maxWidth: 640 }}>
            {DAYS.map((d, i) => {
              const h = s.hours.find((x) => x.weekday === i);
              const put = (v) => setS({ ...s, hours: [...s.hours.filter((x) => x.weekday !== i), ...(v ? [{ weekday: i, ...v }] : [])] });
              return (
                <div key={d} className="row" style={{ marginBottom: 8, flexWrap: "nowrap" }}>
                  <label className="row" style={{ width: 150, margin: 0, color: "var(--text)" }}>
                    <input type="checkbox" style={{ width: "auto" }} checked={!!h} onChange={(e) => put(e.target.checked ? { opens: "10:00", closes: "20:00" } : null)} />{d}</label>
                  {h ? <>
                    <input type="time" value={h.opens} onChange={(e) => put({ ...h, opens: e.target.value })} />
                    <input type="time" value={h.closes} onChange={(e) => put({ ...h, closes: e.target.value })} />
                  </> : <span className="muted">Closed</span>}
                </div>
              );
            })}
            <button className="btn" onClick={() => save("/api/settings/hours", s.hours)}>Save hours</button>
          </div>
          <h2>Closed days (holidays)</h2>
          <EditTable rows={s.closures} setRows={setList("closures")} blank={{ day: "", note: "" }}
            columns={[{ key: "day", label: "Date", type: "date", width: 180 }, { key: "note", label: "Note" }]} />
          <button className="btn" style={{ marginTop: 8 }} onClick={() => save("/api/settings/closures", s.closures)}>Save closed days</button>
          <p className="small muted">To close a day and move its appointments automatically, tell Alaap in “Ask Alaap”.</p>
        </>
      )}

      {tab === "Services & staff" && (
        <>
          <EditTable rows={s.services} setRows={setList("services")} blank={{ name: "", duration_min: 30, price_inr: 0, active: true }}
            columns={[{ key: "name", label: "Service" }, { key: "duration_min", label: "Minutes", type: "number", width: 100 },
              { key: "price_inr", label: "Price ₹", type: "number", width: 110 }, { key: "notes", label: "Notes" }]} />
          <button className="btn" style={{ marginTop: 8 }} onClick={() => save("/api/settings/services", s.services)}>Save services</button>
          <h2>Staff</h2>
          <EditTable rows={s.staff} setRows={setList("staff")} blank={{ name: "", service_ids: [], active: true }}
            columns={[{ key: "name", label: "Name", width: 180 }, {
              key: "service_ids", label: "Does these services", render: (r, set) => (
                <div className="row">{s.services.filter((x) => x.id && x.active !== false).map((x) => (
                  <label key={x.id} className="row small" style={{ margin: 0, color: "var(--text)" }}>
                    <input type="checkbox" style={{ width: "auto" }} checked={(r.service_ids || []).includes(x.id)}
                      onChange={(e) => set(e.target.checked ? [...(r.service_ids || []), x.id] : r.service_ids.filter((y) => y !== x.id))} />{x.name}</label>
                ))}</div>) }]} />
          <button className="btn" style={{ marginTop: 8 }} onClick={() => save("/api/settings/staff", s.staff)}>Save staff</button>
        </>
      )}

      {tab === "Catalog & delivery" && (
        <>
          <EditTable rows={s.products} setRows={setList("products")} blank={{ name: "", unit: "1 pc", price_inr: 0, active: true }}
            columns={[{ key: "name", label: "Product" }, { key: "aliases", label: "Other names customers say" },
              { key: "unit", label: "Unit", width: 90 }, { key: "price_inr", label: "₹", type: "number", width: 90 },
              { key: "stock", label: "Stock (blank = not tracked)", type: "number", width: 110 },
              { key: "reorder_days", label: "Reorder reminder (days)", type: "number", width: 110 }]} />
          <button className="btn" style={{ marginTop: 8 }} onClick={() => save("/api/settings/products", s.products)}>Save catalog</button>
          <h2>Delivery pincodes</h2>
          <EditTable rows={s.areas} setRows={setList("areas")} blank={{ pincode: "", delivery_fee_inr: 0, min_order_inr: 0 }}
            columns={[{ key: "pincode", label: "Pincode" }, { key: "delivery_fee_inr", label: "Fee ₹", type: "number" },
              { key: "min_order_inr", label: "Minimum order ₹", type: "number" }]} />
          <button className="btn" style={{ marginTop: 8 }} onClick={() => save("/api/settings/areas", s.areas)}>Save pincodes</button>
          <h2>Delivery slots</h2>
          <EditTable rows={s.slots} setRows={setList("slots")} blank={{ start: "10:00", end: "12:00" }}
            columns={[{ key: "start", label: "From", type: "time" }, { key: "end", label: "To", type: "time" }]} />
          <button className="btn" style={{ marginTop: 8 }} onClick={() => save("/api/settings/slots", s.slots)}>Save slots</button>
        </>
      )}

      {tab === "FAQs" && (
        <>
          <EditTable rows={s.faqs} setRows={setList("faqs")} blank={{ question: "", answer: "" }}
            columns={[{ key: "question", label: "Topic", width: 220 }, { key: "answer", label: "Answer" }]} />
          <button className="btn" style={{ marginTop: 8 }} onClick={() => save("/api/settings/faqs", s.faqs)}>Save FAQs</button>
        </>
      )}

      {tab === "Channels" && (
        <div className="card" style={{ maxWidth: 760 }}>
          <h2 style={{ marginTop: 0 }}>Website widget</h2>
          <p className="small">Paste before <code>&lt;/body&gt;</code> on your website:</p>
          <pre>{`<script src="${API}/widget.js" data-business="${b.slug}" defer></script>`}</pre>
          <p className="small">Or share the demo page: <a href={`${API}/demo/${b.slug}`} target="_blank">{API}/demo/{b.slug}</a></p>

          <h2>WhatsApp</h2>
          <label>WhatsApp Cloud API phone number ID<input value={b.whatsapp_phone_number_id || ""} onChange={setB("whatsapp_phone_number_id")} /></label>
          <p className="small muted">Webhook URL: <code>{API}/webhooks/whatsapp</code>. Reminders and follow-ups outside the 24-hour
            window need approved message templates in Meta's console.</p>

          <h2>Phone (Exotel)</h2>
          <label>Your Exotel number (10 digits)<input value={b.exotel_number || ""} onChange={setB("exotel_number")} /></label>
          <p className="small muted">In Exotel App Bazaar add a <b>Voicebot</b> applet with URL
            <code>{API.replace(/^http/, "ws")}/ws/exotel?biz={b.slug}</code>, then a <b>Connect</b> applet to your mobile so
            urgent calls reach you. Forward missed calls from your shop number to the Exotel number.</p>
          <button className="btn" onClick={() => save("/api/settings/business", b)}>Save</button>
        </div>
      )}
    </>
  );
}
