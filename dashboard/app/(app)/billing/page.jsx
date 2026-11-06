"use client";

import { useState } from "react";
import { api, rupees } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";

const BLURB = {
  starter: "Solo salons and clinics: appointments, enquiries, complaints.",
  pro: "Restaurants, kirana, busy clinics: orders, UPI payments, order status, follow-ups.",
  business: "Coaching, real estate, chains: leads, everything in Pro, more minutes.",
};

export default function Billing() {
  const { data, error, reload } = useData("/api/billing");
  const [months, setMonths] = useState(1);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  if (error) return <div className="err">{error}</div>;
  if (!data) return <div className="muted">Loading…</div>;
  const st = data.status;

  async function pay(plan) {
    setBusy(plan); setErr(null);
    try {
      const r = await api("/api/billing/checkout", { method: "POST", body: { plan, months } });
      window.open(r.url, "_blank");
      setTimeout(reload, 4000);
    } catch (e) { setErr(e.message); }
    setBusy(null);
  }

  return (
    <>
      <h1>Plan & billing</h1>
      <p className="sub">Pay by UPI, card or netbanking. Prices include the call minutes shown; no setup fee.</p>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <b style={{ textTransform: "capitalize" }}>{st.plan}</b> plan · <Pill value={st.state === "expired" ? "failed" : st.state === "trial" ? "pending" : "paid"} />{" "}
            <span className="muted small">{st.state === "trial" ? "free trial" : st.state}</span>
          </div>
          <div className="small">
            {st.until ? <>{st.state === "expired" ? "Ended" : "Till"} <b>{st.until}</b>{st.days_left != null && st.state !== "expired" && ` · ${st.days_left} days left`}</> : "No end date"}
          </div>
        </div>
        {st.state === "expired" && <p className="err" style={{ marginBottom: 0 }}>
          Your plan has ended. {data.enforced ? "Alaap has stopped answering customers until you renew." : "Renew to keep Alaap answering."}</p>}
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <span className="small muted">Pay for</span>
        <div className="tabs" style={{ margin: 0 }}>
          {[1, 3, 6, 12].map((m) => <button key={m} className={months === m ? "on" : ""} onClick={() => setMonths(m)}>{m} month{m > 1 ? "s" : ""}</button>)}
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {Object.entries(data.plans).map(([k, p]) => (
          <div key={k} className={"card" + (k === st.plan ? " kpi star" : "")}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <b style={{ textTransform: "capitalize", fontSize: 18 }}>{k}</b>{k === st.plan && <span className="pill">current</span>}
            </div>
            <div style={{ fontSize: 26, fontWeight: 650, margin: "6px 0" }}>{rupees(p.price_inr)}<span className="small muted">/month</span></div>
            <div className="small muted">{BLURB[k]}</div>
            <div className="small" style={{ margin: "8px 0" }}>{p.minutes} call minutes · {p.skills.join(", ")}</div>
            <button className="btn" disabled={busy === k} onClick={() => pay(k)}>
              {busy === k ? "Opening…" : `Pay ${rupees(p.price_inr * months)}`}</button>
          </div>
        ))}
      </div>
      {err && <div className="err">{err}</div>}

      {data.payments.length > 0 && (<>
        <h2>Payments</h2>
        <div className="scroll"><table>
          <thead><tr><th>Date</th><th>Plan</th><th>Months</th><th>Amount</th><th>Status</th><th /></tr></thead>
          <tbody>{data.payments.map((p, i) => (
            <tr key={i}><td className="small">{p.created}</td><td style={{ textTransform: "capitalize" }}>{p.plan}</td><td>{p.months}</td>
              <td>{rupees(p.amount_inr)}</td><td><Pill value={p.status === "paid" ? "paid" : "pending"} /></td>
              <td>{p.url && <a className="small" href={p.url} target="_blank">pay now</a>}</td></tr>
          ))}</tbody>
        </table></div>
      </>)}
    </>
  );
}
