"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { rupees } from "../../../lib/api";
import { opsApi } from "../../../lib/ops";

export default function Usage() {
  const [month, setMonth] = useState("");
  const [d, setD] = useState(null);
  useEffect(() => { opsApi(`/usage${month ? `?month=${month}` : ""}`).then(setD); }, [month]);
  if (!d) return <div className="muted">Loading…</div>;
  const rows = [...d.shops].sort((a, b) => b.cost_inr - a.cost_inr);
  const sum = (k) => rows.reduce((t, r) => t + (r[k] || 0), 0);
  const revenue = sum("price_inr"), cost = sum("cost_inr");

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div><h1>Usage & cost</h1>
          <p className="sub">Rough running cost per shop against its plan price, so no shop costs more than it pays.</p></div>
        <input type="month" value={month || d.month} onChange={(e) => setMonth(e.target.value)} style={{ width: 180 }} />
      </div>
      <div className="grid" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="label">Call minutes</div><div className="value">{Math.round(sum("call_minutes"))}</div></div>
        <div className="card kpi"><div className="label">Plan revenue (list)</div><div className="value">{rupees(revenue)}</div></div>
        <div className="card kpi"><div className="label">Running cost</div><div className="value">{rupees(Math.round(cost))}</div></div>
        <div className={`card kpi ${revenue && (revenue - cost) / revenue >= 0.6 ? "star" : ""}`}><div className="label">Gross margin</div>
          <div className="value">{revenue ? Math.round(((revenue - cost) / revenue) * 100) + "%" : "—"}</div><div className="hint">target 60%+</div></div>
      </div>
      <div className="scroll"><table>
        <thead><tr><th>Shop</th><th>Plan</th><th>Calls</th><th>Minutes</th><th>Chats</th><th>WhatsApp sent</th><th>Number rent</th><th>Cost</th><th>Margin</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.id}>
            <td><Link href={`/ops/shops/${r.id}`}>{r.name}</Link></td>
            <td><span className="pill grey">{r.plan}</span> <span className="small muted">{rupees(r.price_inr)}</span></td>
            <td>{r.calls}</td>
            <td>{r.call_minutes}{r.call_minutes > r.included_minutes && <span className="pill bad" style={{ marginLeft: 4 }}>over {r.included_minutes}</span>}</td>
            <td>{r.chats}</td><td>{r.messages_sent}</td><td>{r.number_rent_inr ? rupees(r.number_rent_inr) : "—"}</td>
            <td>{rupees(Math.round(r.cost_inr))}</td>
            <td><span className={`pill ${r.margin_inr < 0 ? "bad" : r.margin_inr < r.price_inr * 0.6 ? "warn" : "good"}`}>{rupees(r.margin_inr)}</span></td>
          </tr>))}</tbody>
      </table></div>
      <p className="small muted">Rates used: ₹{d.rates.call_min}/call minute, ₹{d.rates.wa_msg}/WhatsApp message, ₹{d.rates.chat_turn}/chat message
        (set COST_* in .env to your real Gnani, Gemini, Exotel and Meta rates).</p>
    </>
  );
}
