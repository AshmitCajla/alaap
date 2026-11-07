"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { rupees } from "../../lib/api";
import { opsApi } from "../../lib/ops";

const STAGE = { setup: "warn", review: "", live: "good" };
const KINDS = ["salon", "clinic", "kirana", "restaurant", "pharmacy", "coaching", "real_estate", "gym", "home_services"];

function NewShop({ onDone, prefill }) {
  const [f, setF] = useState({ kind: "salon", assign_number: true, ...prefill });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [made, setMade] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { setMade(await opsApi("/shops", { method: "POST", body: f })); onDone(); } catch (x) { setErr(x.message); }
    setBusy(false);
  }
  if (made) return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Shop created</h2>
      <p>Shop code <b>{made.code}</b>{made.number ? <> · number <b>{made.number}</b></> : null}</p>
      {made.note && <p className="err">{made.note}</p>}
      {made.password && <p className="small">Owner dashboard password (shown once): <code>{made.password}</code></p>}
      <div className="row"><Link className="btn" href={`/ops/shops/${made.id}`}>Set it up →</Link>
        <button className="btn ghost" onClick={() => { setMade(null); setF({ kind: "salon", assign_number: true }); }}>Add another</button></div>
    </div>
  );
  return (
    <form className="card" onSubmit={submit}>
      <h2 style={{ marginTop: 0 }}>Add a shop</h2>
      <div className="grid">
        <label>Shop name<input required value={f.name || ""} onChange={set("name")} /></label>
        <label>Type<select value={f.kind} onChange={set("kind")}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label>City<input value={f.city || ""} onChange={set("city")} /></label>
        <label>Owner name<input required value={f.owner_name || ""} onChange={set("owner_name")} /></label>
        <label>Owner mobile (WhatsApp)<input required value={f.owner_phone || ""} onChange={set("owner_phone")} /></label>
        <label>Owner email (optional login)<input type="email" value={f.email || ""} onChange={set("email")} /></label>
      </div>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" style={{ width: "auto" }} checked={f.assign_number} onChange={set("assign_number")} />
        Give it a phone number from the pool
      </label>
      {err && <div className="err">{err}</div>}
      <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create shop"}</button>
    </form>
  );
}

export default function Shops() {
  const [data, setData] = useState(null);
  const [ov, setOv] = useState(null);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState("");
  const [prefill, setPrefill] = useState(null);
  const load = () => { opsApi("/shops").then(setData); opsApi("/overview").then(setOv); };
  useEffect(() => {
    load();
    const p = new URLSearchParams(window.location.search);
    if (p.get("new")) { setPrefill({ owner_phone: p.get("phone") || "", intake_id: Number(p.get("intake")) || undefined }); setAdding(true); }
  }, []);
  if (!data || !ov) return <div className="muted">Loading…</div>;
  const shops = data.shops.filter((s) => !q || (s.name + s.code + s.owner_phone + s.city).toLowerCase().includes(q.toLowerCase()));
  const ch = ov.channels;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div><h1>Shops</h1><p className="sub">Every shop Alaap answers for. Managed shops are set up by the team.</p></div>
        <button className="btn" onClick={() => setAdding(!adding)}>{adding ? "Close" : "+ Add shop"}</button>
      </div>
      {adding && <div style={{ marginBottom: 16 }}><NewShop prefill={prefill} onDone={load} /></div>}

      <div className="grid" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="label">Live shops</div><div className="value">{ov.stages.live || 0}</div>
          <div className="hint">{ov.stages.setup || 0} in setup · {ov.stages.review || 0} to review</div></div>
        <div className="card kpi"><div className="label">Inbox</div><div className="value">{ov.new_intakes}</div>
          <div className="hint"><Link href="/ops/intakes">menus & join requests</Link></div></div>
        <div className="card kpi"><div className="label">Free numbers</div><div className="value">{ov.numbers_free}</div>
          <div className="hint">of {ov.numbers_total} in the pool</div></div>
        <div className="card kpi"><div className="label">This month</div><div className="value">{ov.month.call_minutes} min</div>
          <div className="hint">{ov.month.calls} calls · {ov.month.chats} chats · cost {rupees(Math.round(ov.month.cost_inr))}</div></div>
      </div>

      <div className="card small" style={{ marginBottom: 16 }}>
        <b>Channels:</b>{" "}
        <span className={`pill ${ch.exotel_socket ? "good" : "bad"}`}>Exotel calls {ch.exotel_socket ? "ready" : "off"}</span>{" "}
        <span className={`pill ${ch.exotel_api ? "good" : "grey"}`}>Exotel API {ch.exotel_api ? "connected" : "needs SID"}</span>{" "}
        <span className={`pill ${ch.whatsapp ? "good" : "grey"}`}>WhatsApp {ch.whatsapp ? "on" : "not connected"}</span>{" "}
        <span className={`pill ${ch.shared_whatsapp ? "good" : "grey"}`}>Shared WhatsApp {ch.shared_whatsapp ? "on" : "off"}</span>
        <div className="muted" style={{ marginTop: 6 }}>One Exotel flow for all shops: Voicebot URL <code>{ch.voicebot_url}</code> (calls are routed by the number dialled).</div>
      </div>

      <input placeholder="Search name, code, phone, city…" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: 10 }} />
      <div className="scroll"><table>
        <thead><tr><th>Shop</th><th>Stage</th><th>Code</th><th>Number</th><th>Owner</th><th>This month</th><th>Plan</th><th>Last activity</th></tr></thead>
        <tbody>{shops.map((s) => (
          <tr key={s.id}>
            <td><Link href={`/ops/shops/${s.id}`}><b>{s.name}</b></Link><div className="small muted">{s.kind} · {s.city || "—"}{s.managed ? " · managed" : " · self-serve"}</div></td>
            <td><span className={`pill ${STAGE[s.stage] || ""}`}>{s.stage}</span>{!s.active && <span className="pill bad">off</span>}</td>
            <td><code>{s.code || "—"}</code></td>
            <td>{s.number || <span className="muted">—</span>}</td>
            <td>{s.owner_name}<div className="small muted">{s.owner_phone}</div></td>
            <td className="small">{s.usage.calls} calls · {s.usage.call_minutes} min<br />{s.usage.chats} chats · {rupees(Math.round(s.usage.cost_inr))}</td>
            <td><span className="pill grey">{s.plan}</span><div className="small muted">{s.billing}</div></td>
            <td className="small muted">{s.last_activity?.replace("T", " ") || "—"}</td>
          </tr>))}
        </tbody>
      </table></div>
    </>
  );
}
