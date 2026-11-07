"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { setToken } from "../../../../lib/api";
import { opsApi } from "../../../../lib/ops";
import Review from "../../../../lib/Review";

function Copy({ text }) {
  const [done, setDone] = useState(false);
  return <button className="btn ghost small" onClick={() => navigator.clipboard.writeText(text).then(() => {
    setDone(true); setTimeout(() => setDone(false), 1500); })}>{done ? "Copied ✓" : "Copy"}</button>;
}

const STEPS = [["setup", "1. Collect menu"], ["review", "2. Review & test"], ["live", "3. Live"]];

export default function ShopPage() {
  const { id } = useParams();
  const [s, setS] = useState(null);
  const [numbers, setNumbers] = useState([]);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [reviewing, setReviewing] = useState(null); // intake being reviewed
  const [notes, setNotes] = useState("");

  const load = () => opsApi(`/shops/${id}`).then((d) => { setS(d); setNotes(d.ops_notes || ""); });
  useEffect(() => { load(); opsApi("/numbers").then((n) => setNumbers(n.numbers)); }, [id]); // eslint-disable-line

  async function run(fn, ok) {
    setBusy(true); setErr(null); setMsg(null);
    try { const r = await fn(); if (ok) setMsg(typeof ok === "function" ? ok(r) : ok); await load(); return r; }
    catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  if (!s) return <div className="muted">Loading…</div>;

  const importText = () => run(async () => {
    const item = await opsApi(`/shops/${id}/import`, { method: "POST", body: { text: text || null, url: url || null } });
    setReviewing(item); setText(""); setUrl("");
  });
  const importPhoto = (file) => run(async () => {
    const form = new FormData(); form.append("photo", file);
    setReviewing(await opsApi(`/shops/${id}/import-photo`, { method: "POST", form }));
  });
  const readIntake = (i) => run(async () => setReviewing(await opsApi(`/intakes/${i.id}/read`, { method: "POST" })));
  const apply = (data) => run(async () => {
    const r = await opsApi(`/intakes/${reviewing.id}/apply`, { method: "POST", body: { data } });
    setReviewing(null); return r;
  }, (r) => `Saved: ${Object.entries(r.saved).filter(([, v]) => v).map(([k, v]) => `${v} ${k}`).join(", ") || "nothing new"}.`);
  const openDashboard = () => run(async () => {
    const r = await opsApi(`/shops/${id}/open`, { method: "POST" });
    setToken(r.token); window.open("/", "_blank");
  });
  const free = numbers.filter((n) => !n.business_id);
  const stageIdx = STEPS.findIndex(([k]) => k === s.stage);

  return (
    <>
      <p className="small"><Link href="/ops">← All shops</Link></p>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1>{s.name} <span className="pill grey" style={{ verticalAlign: "middle" }}>{s.code}</span></h1>
          <p className="sub">{s.kind} · {s.city || "—"} · owner {s.owner_name} ({s.owner_phone}){s.owner_login ? ` · login ${s.owner_login}` : ""}</p>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={openDashboard}>Open shop dashboard ↗</button>
          <a className="btn ghost" href={s.links.customer_page} target="_blank">Test call / chat ↗</a>
        </div>
      </div>

      <div className="row" style={{ gap: 6, marginBottom: 16 }}>
        {STEPS.map(([k, label], i) => (
          <span key={k} className={`pill ${i < stageIdx ? "good" : i === stageIdx ? "" : "grey"}`} style={{ fontSize: 13, padding: "4px 12px" }}>
            {i < stageIdx ? "✓ " : ""}{label}</span>))}
      </div>
      {msg && <div className="card" style={{ background: "var(--good-soft)", borderColor: "var(--good)", marginBottom: 12 }}>{msg}</div>}
      {err && <div className="card" style={{ background: "var(--bad-soft)", borderColor: "var(--bad)", marginBottom: 12 }}>{err}</div>}

      <div className="split" style={{ gridTemplateColumns: "1fr 360px", alignItems: "start" }}>
        <div>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>Menu, prices & hours</h2>
            <p className="small">
              Now: {s.counts.services} services · {s.counts.products} items · {s.counts.staff} staff · {s.counts.hours} days of hours
              {s.counts.samples > 0 && <span className="pill warn" style={{ marginLeft: 6 }}>{s.counts.samples} sample prices still in</span>}
            </p>
            {reviewing ? (
              reviewing.extracted ? (<>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <b>Check what Alaap read</b><button className="btn ghost small" onClick={() => setReviewing(null)}>Cancel</button></div>
                <Review key={reviewing.id} data={reviewing.extracted} busy={busy} onApply={apply} />
              </>) : <p className="muted">Nothing read yet.</p>
            ) : (<>
              <label>Paste the price list / menu (any language)
                <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Haircut 150, Beard 80, Facial 800… Open 10 to 8, Monday closed" /></label>
              <label>…or their website / Google listing link<input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" /></label>
              <div className="row">
                <button className="btn" disabled={busy || (!text && !url)} onClick={importText}>{busy ? "Reading…" : "Read it"}</button>
                <label className="btn ghost" style={{ margin: 0, color: "var(--brand)" }}>
                  {busy ? "Reading…" : "Upload photo of rate card"}
                  <input type="file" accept="image/*" hidden onChange={(e) => e.target.files[0] && importPhoto(e.target.files[0])} />
                </label>
              </div>
            </>)}
          </div>

          {s.intakes.length > 0 && (
            <div className="card" style={{ marginTop: 12 }}>
              <h2 style={{ marginTop: 0 }}>Sent by the owner & past imports</h2>
              <table><tbody>{s.intakes.map((i) => (
                <tr key={i.id}>
                  <td className="small muted">{i.created_at.replace("T", " ")}</td>
                  <td>{i.kind === "join" ? "Asked to join" : i.kind === "photo" ? "📷 Photo" : "Text"} <span className="small muted">via {i.source}</span>
                    {i.text && <div className="small muted">{i.text.slice(0, 120)}</div>}</td>
                  <td><span className={`pill ${i.status === "new" ? "warn" : i.status === "applied" ? "good" : "grey"}`}>{i.status}</span></td>
                  <td>{i.kind !== "join" && (i.extracted
                    ? <button className="btn ghost small" onClick={() => setReviewing(i)}>Review</button>
                    : <button className="btn ghost small" disabled={busy} onClick={() => readIntake(i)}>Read</button>)}</td>
                </tr>))}</tbody></table>
            </div>
          )}

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>Welcome message to the owner</h2>
            <p className="small muted">Sent on WhatsApp when the shop goes live.</p>
            <pre>{s.welcome_text}</pre>
          </div>
        </div>

        <div>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>Go live</h2>
            {s.stage === "live" ? (
              <p className="small">Live{s.active ? "" : " but turned off"}. Customers are being answered.</p>
            ) : (
              <p className="small">Check the prices, make a test call, then go live. The owner gets the welcome message.</p>
            )}
            <div className="row">
              {s.stage !== "live" && <button className="btn" disabled={busy || s.counts.samples > 0}
                onClick={() => run(() => opsApi(`/shops/${id}/go-live`, { method: "POST" }), "Live! Welcome message queued to the owner.")}>Go live</button>}
              <button className="btn ghost small" disabled={busy}
                onClick={() => run(() => opsApi(`/shops/${id}`, { method: "PATCH", body: { active: !s.active } }), s.active ? "Turned off." : "Turned on.")}>
                {s.active ? "Turn off" : "Turn on"}</button>
              {s.stage === "live" && <button className="btn ghost small" disabled={busy}
                onClick={() => run(() => opsApi(`/shops/${id}`, { method: "PATCH", body: { stage: "review" } }))}>Back to review</button>}
            </div>
            {s.counts.samples > 0 && s.stage !== "live" && <p className="small muted">Replace the sample prices first.</p>}
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>Phone number</h2>
            {s.number ? (<>
              <p style={{ fontSize: 20, margin: "4px 0" }}><b>{s.number}</b></p>
              <p className="small muted">Owner forwards missed calls to it:</p>
              <table><tbody>{s.links.forwarding.map(([label, code]) => (
                <tr key={code}><td className="small">{label}</td><td><code>{code}</code></td></tr>))}</tbody></table>
              <button className="btn ghost small" style={{ marginTop: 8 }} disabled={busy}
                onClick={() => run(() => opsApi(`/shops/${id}/number`, { method: "DELETE" }), "Number released to the pool.")}>Release number</button>
            </>) : (<>
              <p className="small">No number yet. {free.length} free in the pool.</p>
              <div className="row">
                <select id="num" defaultValue="">{[<option key="" value="">Oldest free</option>,
                  ...free.map((n) => <option key={n.id} value={n.id}>{n.number}</option>)]}</select>
                <button className="btn small" disabled={busy || !free.length} onClick={() => {
                  const v = document.getElementById("num").value;
                  run(() => opsApi(`/shops/${id}/number`, { method: "POST", body: { number_id: v ? Number(v) : null } }), (r) => `Assigned ${r.number}.`);
                }}>Assign</button>
              </div>
              {!free.length && <p className="small"><Link href="/ops/numbers">Add numbers to the pool →</Link></p>}
            </>)}
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>WhatsApp</h2>
            {s.whatsapp === "own" ? <p className="small">Uses the shop's own WhatsApp number.</p>
              : s.links.whatsapp ? (<>
                <p className="small">On Alaap's shared number with code <b>{s.code}</b>. The QR poster opens:</p>
                <div className="row" style={{ flexWrap: "nowrap" }}><input readOnly value={s.links.whatsapp} /><Copy text={s.links.whatsapp} /></div>
              </>) : <p className="small muted">Shared WhatsApp isn't connected yet (WHATSAPP_SHARED_NUMBER_ID). Customers can still use the web link and calls.</p>}
            <p className="small" style={{ marginTop: 10 }}>Customer page:</p>
            <div className="row" style={{ flexWrap: "nowrap" }}><input readOnly value={s.links.customer_page} /><Copy text={s.links.customer_page} /></div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>Team notes</h2>
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. owner prefers calls after 2 pm" />
            <button className="btn ghost small" style={{ marginTop: 6 }} disabled={busy}
              onClick={() => run(() => opsApi(`/shops/${id}`, { method: "PATCH", body: { ops_notes: notes } }), "Notes saved.")}>Save notes</button>
            <p className="small muted" style={{ marginTop: 10 }}>This month: {s.usage.calls} calls ({s.usage.call_minutes} min) · {s.usage.chats} chats · ~₹{Math.round(s.usage.cost_inr)} cost · plan {s.plan} ({s.billing})</p>
          </div>
        </div>
      </div>
    </>
  );
}
