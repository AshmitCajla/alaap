"use client";

import { useState } from "react";
import { API, api, pct, rupees } from "../../lib/api";
import { useData, useMe } from "../../lib/Shell";

export default function Overview() {
  const me = useMe();
  const [days, setDays] = useState(7);
  const { data: o, error } = useData(`/api/overview?days=${days}`, [days]);
  const { data: setup } = useData("/api/setup/status");
  const [sent, setSent] = useState(false);
  if (error) return <div className="err">{error}</div>;
  if (!o) return <div className="muted">Loading…</div>;
  const max = Math.max(1, ...o.series.map((d) => d.conversations));
  const used = o.usage.included_minutes ? Math.min(1, o.usage.used_minutes / o.usage.included_minutes) : 0;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Overview</h1>
          <p className="sub">What Alaap did for {me.business.name}.</p>
        </div>
        <div className="tabs">
          {[1, 7, 30].map((d) => (
            <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{d === 1 ? "Today" : `${d} days`}</button>
          ))}
        </div>
      </div>

      {setup && setup.done < setup.total && (
        <div className="card" style={{ marginBottom: 16, borderColor: "var(--brand)" }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b>Finish setting up · {setup.done} of {setup.total} done</b>
            <a className="btn small" href="/setup">Continue setup</a>
          </div>
          <div className="meter" style={{ margin: "10px 0" }}><div style={{ width: `${(setup.done / setup.total) * 100}%` }} /></div>
          {setup.items.map((i) => (
            <div key={i.key} className="small" style={{ padding: "3px 0", opacity: i.done ? 0.6 : 1 }}>
              {i.done ? "✅" : "⬜"} {i.label}{!i.done && <span className="muted"> — {i.hint}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="grid">
        <div className="card kpi star">
          <div className="label">Bookings + orders by Alaap</div>
          <div className="value">{o.north_star}</div>
          <div className="hint">{o.bookings_by_alaap} bookings · {o.orders_by_alaap} orders</div>
        </div>
        <div className="card kpi"><div className="label">Value handled</div><div className="value">{rupees(o.value_inr)}</div>
          <div className="hint">bookings at list price + orders</div></div>
        <div className="card kpi"><div className="label">Conversations</div><div className="value">{o.conversations}</div>
          <div className="hint">{Object.entries(o.channels).map(([k, v]) => `${k} ${v}`).join(" · ") || "none yet"}</div></div>
        <div className="card kpi"><div className="label">Task completion</div><div className="value">{pct(o.task_completion_rate)}</div>
          <div className="hint">target 80%+</div></div>
        <div className="card kpi"><div className="label">Handed to you</div><div className="value">{pct(o.handoff_rate)}</div>
          <div className="hint">target under 15%</div></div>
        <div className="card kpi"><div className="label">Reply time (p95)</div>
          <div className="value">{o.latency_p95_ms == null ? "—" : (o.latency_p95_ms / 1000).toFixed(1) + "s"}</div>
          <div className="hint">target under 1.5s</div></div>
        <div className="card kpi"><div className="label">Open callbacks</div><div className="value">{o.open_tickets}</div>
          <div className="hint"><a href="/inbox">see inbox</a></div></div>
        <div className="card kpi"><div className="label">New leads</div><div className="value">{o.new_leads}</div></div>
      </div>

      <h2>Conversations per day</h2>
      <div className="card">
        <div className="bars">
          {o.series.map((d) => (
            <div key={d.date} className="bar" title={`${d.date}: ${d.conversations} conversations, ${d.completed} bookings/orders/leads`}>
              <div className="fill" style={{ height: `${(d.conversations / max) * 100}%` }} />
              <div className="x">{d.date.slice(8)}</div>
            </div>
          ))}
        </div>
      </div>

      <h2>Plan and usage</h2>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div><b style={{ textTransform: "capitalize" }}>{o.usage.plan}</b> plan · {rupees(o.usage.price_inr)}/month</div>
          <div className="muted small">{o.usage.used_minutes} of {o.usage.included_minutes} call minutes this month</div>
        </div>
        <div className="meter" style={{ marginTop: 8 }}><div style={{ width: `${used * 100}%` }} /></div>
      </div>

      <h2>Share your front desk</h2>
      <div className="card">
        <p className="small" style={{ marginTop: 0 }}>Demo page for walk-ins and your website: <a href={`${API}/demo/${me.business.slug}`} target="_blank">{API}/demo/{me.business.slug}</a></p>
        <div className="row">
          <button className="btn ghost small" disabled={sent} onClick={() => api("/api/jobs/daily-summary", { method: "POST" }).then(() => setSent(true))}>
            {sent ? "Daily summary queued (see outbox)" : "Send today's voice summary now"}
          </button>
        </div>
      </div>
    </>
  );
}
