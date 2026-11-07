"use client";

import { useState } from "react";
import { Check, ShieldCheck } from "lucide-react";
import { api, rupees } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";
import { ErrorBox, PageHead, Seg, Skeleton, useToast } from "../../../lib/ui";

const PLAN = {
  starter: { blurb: "For salons, clinics and solo shops", points: ["Answers calls, WhatsApp & web 24×7", "Books, moves & cancels appointments", "Reminders and feedback on WhatsApp"] },
  pro: { blurb: "For kirana, restaurants and busy clinics", points: ["Everything in Starter", "Takes orders with UPI payment links", "Order updates, reorder reminders, win-back offers"], popular: true },
  business: { blurb: "For coaching, real estate and chains", points: ["Everything in Pro", "Qualifies and scores leads", "Most call minutes"] },
};

export default function Billing() {
  const toast = useToast();
  const { data, error, reload } = useData("/api/billing");
  const [months, setMonths] = useState(1);
  const [busy, setBusy] = useState(null);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Skeleton rows={2} height={140} />;
  const st = data.status;

  async function pay(plan) {
    setBusy(plan);
    try {
      const r = await api("/api/billing/checkout", { method: "POST", body: { plan, months } });
      window.open(r.url, "_blank");
      toast("Payment page opened in a new tab");
      setTimeout(reload, 4000);
    } catch (e) { toast(e.message, "bad"); }
    setBusy(null);
  }

  return (
    <>
      <PageHead title="Plan & billing" sub="Pay by UPI, card or netbanking. No setup fee, cancel any time." />
      <div className={"callout " + (st.state === "expired" ? "bad" : st.state === "trial" ? "info" : "good")} style={{ marginBottom: 22, alignItems: "center" }}>
        <ShieldCheck size={20} />
        <div style={{ flex: 1 }}>
          <b style={{ textTransform: "capitalize" }}>{st.plan} plan</b> · {st.state === "trial" ? "free trial" : st.state === "expired" ? "ended" : "active"}
          {st.until && <span className="muted"> · {st.state === "expired" ? "ended" : "until"} {st.until}{st.days_left != null && st.state !== "expired" ? ` (${st.days_left} days left)` : ""}</span>}
          {st.state === "expired" && <div className="small">{data.enforced ? "Your assistant has stopped answering customers until you renew." : "Renew to keep your assistant answering."}</div>}
        </div>
      </div>

      <div className="section-head"><h2>Choose a plan</h2>
        <Seg value={months} onChange={setMonths} options={[[1, "1 month"], [3, "3 months"], [6, "6 months"], [12, "12 months"]]} /></div>
      <div className="grid-3">
        {Object.entries(data.plans).map(([k, p]) => {
          const info = PLAN[k] || { blurb: "", points: [] };
          const current = k === st.plan;
          return (
            <div key={k} className={"card" + (info.popular ? " hl" : "")} style={{ display: "flex", flexDirection: "column" }}>
              <div className="row between"><b style={{ textTransform: "capitalize", fontSize: 18 }}>{k}</b>
                {current ? <span className="badge">Your plan</span> : info.popular && <span className="badge warn">Most popular</span>}</div>
              <div className="small muted">{info.blurb}</div>
              <div style={{ margin: "14px 0 4px" }}><span style={{ fontSize: 32, fontWeight: 750, letterSpacing: "-.02em" }}>{rupees(p.price_inr)}</span><span className="muted">/month</span></div>
              <div className="small muted" style={{ marginBottom: 12 }}>{p.minutes} call minutes included</div>
              <div className="stack" style={{ gap: 7, marginBottom: 18, flex: 1 }}>
                {info.points.map((x) => <div key={x} className="row small" style={{ gap: 8, flexWrap: "nowrap", alignItems: "flex-start" }}>
                  <Check size={16} color="var(--good)" style={{ flex: "none", marginTop: 1 }} />{x}</div>)}
              </div>
              <button className={"btn block" + (info.popular || current ? "" : " ghost")} disabled={busy === k} onClick={() => pay(k)}>
                {busy === k ? "Opening…" : `${current ? "Renew" : "Choose"} · ${rupees(p.price_inr * months)}`}</button>
            </div>
          );
        })}
      </div>

      {data.payments.length > 0 && (
        <div className="section">
          <div className="section-head"><h2>Payment history</h2></div>
          <div className="scroll"><table>
            <thead><tr><th>Date</th><th>Plan</th><th>Months</th><th>Amount</th><th>Status</th><th /></tr></thead>
            <tbody>{data.payments.map((p, i) => (
              <tr key={i}><td className="small">{p.created}</td><td style={{ textTransform: "capitalize" }}>{p.plan}</td><td>{p.months}</td>
                <td className="num">{rupees(p.amount_inr)}</td><td><Pill value={p.status === "paid" ? "paid" : "pending"} /></td>
                <td>{p.url && p.status !== "paid" && <a className="btn plain small" href={p.url} target="_blank">Pay now</a>}</td></tr>
            ))}</tbody>
          </table></div>
        </div>
      )}
    </>
  );
}
