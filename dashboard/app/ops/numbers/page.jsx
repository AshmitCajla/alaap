"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { opsApi } from "../../../lib/ops";

export default function Numbers() {
  const [d, setD] = useState(null);
  const [text, setText] = useState("");
  const [cost, setCost] = useState("");
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => opsApi("/numbers").then(setD);
  useEffect(() => { load(); }, []);

  async function run(fn, ok) {
    setBusy(true); setErr(null); setMsg(null);
    try { const r = await fn(); setMsg(ok(r)); load(); } catch (x) { setErr(x.message); }
    setBusy(false);
  }
  if (!d) return <div className="muted">Loading…</div>;
  const free = d.numbers.filter((n) => !n.business_id).length;

  return (
    <>
      <h1>Phone numbers</h1>
      <p className="sub">Numbers Alaap rents from Exotel and lends to shops. {free} free of {d.numbers.length}.</p>
      {msg && <div className="card" style={{ background: "var(--good-soft)", marginBottom: 12 }}>{msg}</div>}
      {err && <div className="card" style={{ background: "var(--bad-soft)", marginBottom: 12 }}>{err}</div>}

      <div className="split" style={{ gridTemplateColumns: "1fr 340px", alignItems: "start" }}>
        <div className="scroll"><table>
          <thead><tr><th>Number</th><th>Shop</th><th>Since</th><th>₹/month</th><th>Notes</th><th /></tr></thead>
          <tbody>{d.numbers.length ? d.numbers.map((n) => (
            <tr key={n.id}>
              <td><b>{n.number}</b></td>
              <td>{n.shop ? <Link href={`/ops/shops/${n.business_id}`}>{n.shop}</Link> : <span className="pill good">free</span>}</td>
              <td className="small muted">{n.assigned_at?.replace("T", " ") || "—"}</td>
              <td>{n.monthly_cost_inr || "—"}</td>
              <td className="small muted">{n.notes || ""}</td>
              <td>{!n.business_id && <button className="btn ghost small" disabled={busy}
                onClick={() => run(() => opsApi(`/numbers/${n.id}`, { method: "DELETE" }), () => `Removed ${n.number}.`)}>Remove</button>}</td>
            </tr>)) : <tr><td colSpan={6} className="muted">No numbers yet. Add the ExoPhones you rent.</td></tr>}
          </tbody>
        </table></div>

        <div>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>Add numbers</h2>
            <label>Numbers (one per line or comma separated)
              <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"080-4711-2345\n+91 80471 12346"} /></label>
            <label>Rent per number, ₹/month<input type="number" value={cost} onChange={(e) => setCost(e.target.value)} /></label>
            <button className="btn" disabled={busy || !text.trim()} onClick={() => run(
              () => opsApi("/numbers", { method: "POST", body: { numbers: text.split(/[\n,]+/), monthly_cost_inr: Number(cost) || 0 } }),
              (r) => { setText(""); return `Added ${r.added.length}: ${r.added.join(", ")}`; })}>Add to pool</button>
          </div>
          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>From Exotel</h2>
            <p className="small">Pull every ExoPhone on Alaap's Exotel account into the pool.</p>
            <button className="btn ghost" disabled={busy || !d.exotel_api} onClick={() => run(
              () => opsApi("/numbers/sync-exotel", { method: "POST" }), (r) => `Exotel has ${r.found}; added ${r.added.length} new.`)}>Sync from Exotel</button>
            {!d.exotel_api && <p className="small muted">Needs EXOTEL_SID, EXOTEL_API_KEY and EXOTEL_API_TOKEN in the server's .env.</p>}
            <p className="small muted" style={{ marginTop: 10 }}>In Exotel, point every number at one flow: a Voicebot applet with
              <code>wss://YOUR-API/ws/exotel?token=EXOTEL_WS_TOKEN</code> (no shop in the URL; Alaap routes by the number dialled), then a Connect applet to the owner for handoffs.</p>
          </div>
        </div>
      </div>
    </>
  );
}
