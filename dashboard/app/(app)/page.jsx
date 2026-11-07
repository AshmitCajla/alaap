"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight, CalendarCheck, CheckCircle2, Clock, Gauge, Hand, IndianRupee, Inbox, MessagesSquare, Rocket, Send, ShoppingBag, Target, Zap,
} from "lucide-react";
import { api, pct, rupees } from "../../lib/api";
import { Pill, useData, useMe } from "../../lib/Shell";
import { ChannelIcon, Empty, ErrorBox, PageHead, Seg, Skeleton, Stat, dayLabel, time12, useToast, when } from "../../lib/ui";

function hello() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function Home() {
  const me = useMe();
  const toast = useToast();
  const [days, setDays] = useState(7);
  const { data: o, error } = useData(`/api/overview?days=${days}`, [days]);
  const { data: setup } = useData("/api/setup/status");
  const skills = new Set(me.business.skills);
  const appts = useData(skills.has("appointments") ? "/api/appointments?days_back=0&days_ahead=2" : "/api/me");
  const orders = useData(skills.has("orders") ? "/api/orders" : "/api/me");
  const convs = useData("/api/conversations?limit=6");

  if (error) return <ErrorBox error={error} />;
  const first = (me.user.name || "").split(" ")[0];
  const upcoming = skills.has("appointments") && Array.isArray(appts.data)
    ? appts.data.filter((a) => a.status === "booked" && new Date(a.start.replace(" ", "T")) >= new Date(Date.now() - 30 * 60000)).slice(0, 5) : null;
  const openOrders = skills.has("orders") && Array.isArray(orders.data)
    ? orders.data.filter((x) => ["placed", "preparing", "out_for_delivery"].includes(x.status)).slice(0, 5) : null;
  const nextStep = setup?.items.find((i) => !i.done);

  return (
    <>
      <PageHead title={`${hello()}${first && !me.user.support ? `, ${first}` : ""}`}
                sub={`Here's what your assistant did for ${me.business.name}.`}>
        <Seg value={days} onChange={setDays} options={[[1, "Today"], [7, "7 days"], [30, "30 days"]]} />
      </PageHead>

      {setup && setup.done < setup.total && nextStep && (
        <div className="card hl" style={{ marginBottom: 18 }}>
          <div className="row between" style={{ alignItems: "flex-start", gap: 16 }}>
            <div style={{ flex: 1, minWidth: 240 }}>
              <div className="row" style={{ gap: 8, marginBottom: 6 }}><Rocket size={18} color="var(--brand)" />
                <b>Finish setting up</b><span className="badge">{setup.done} of {setup.total} done</span></div>
              <div className="progress" style={{ margin: "8px 0 10px", maxWidth: 420 }}><div style={{ width: `${(setup.done / setup.total) * 100}%` }} /></div>
              <div className="small">Next: <b>{nextStep.label}</b> <span className="muted">— {nextStep.hint}</span></div>
            </div>
            <Link className="btn" href="/setup">Continue <ArrowRight size={16} /></Link>
          </div>
        </div>
      )}

      {!o ? <Skeleton rows={2} height={110} /> : (<>
        <div className="grid-4">
          <Stat star icon={CalendarCheck} label="Booked by Alaap" value={o.north_star}
                hint={`${o.bookings_by_alaap} appointment${o.bookings_by_alaap === 1 ? "" : "s"}${skills.has("orders") ? ` · ${o.orders_by_alaap} orders` : ""}`} />
          <Stat icon={IndianRupee} label="Business brought in" value={rupees(o.value_inr)} hint="at your listed prices" />
          <Stat icon={MessagesSquare} label="Customers answered" value={o.conversations}
                hint={Object.entries(o.channels).map(([k, v]) => `${v} ${k === "web" ? "web chat" : k}`).join(" · ") || "none yet"} />
          <Stat icon={Inbox} label="Waiting for you" value={o.open_tickets + (o.new_leads || 0)}
                hint={<><Link href="/inbox">{o.open_tickets} callback{o.open_tickets === 1 ? "" : "s"}</Link>{skills.has("leads") && <> · <Link href="/leads">{o.new_leads} new leads</Link></>}</>} />
        </div>

        <div className="grid-2 section">
          <div className="card pad-0">
            <div className="card-head">
              <h2>{upcoming ? "Coming up" : openOrders ? "Orders to deliver" : "Latest conversations"}</h2>
              <Link className="btn plain small" href={upcoming ? "/appointments" : openOrders ? "/orders" : "/conversations"}>See all <ArrowRight size={14} /></Link>
            </div>
            {upcoming ? (upcoming.length ? <div className="list">{upcoming.map((a) => (
              <div key={a.id} className="list-row">
                <div className="timebox"><b>{time12(a.start).replace(" ", "")}</b><span>{dayLabel(a.start)}</span></div>
                <div style={{ flex: 1, minWidth: 0 }}><b>{a.customer}</b> · {a.service}<div className="small muted">with {a.staff} · booked by {a.channel === "web" ? "web chat" : a.channel}</div></div>
              </div>))}</div>
              : <Empty icon={CalendarCheck} title="Nothing booked for today or tomorrow">New bookings show up here the moment a customer confirms.</Empty>)
            : openOrders ? (openOrders.length ? <div className="list">{openOrders.map((x) => (
              <div key={x.id} className="list-row">
                <div className="avatar"><ShoppingBag size={16} /></div>
                <div style={{ flex: 1, minWidth: 0 }}><b>{x.customer}</b> · {rupees(x.total_inr)}<div className="small muted">{x.items.length} items · {x.slot}</div></div>
                <Pill value={x.status} />
              </div>))}</div> : <Empty icon={ShoppingBag} title="No orders waiting">New orders appear here with the delivery slot.</Empty>)
            : <ConvList convs={convs.data} />}
          </div>

          <div className="card pad-0">
            <div className="card-head"><h2>{upcoming || openOrders ? "Latest conversations" : "Busiest days"}</h2>
              <Link className="btn plain small" href="/conversations">All <ArrowRight size={14} /></Link></div>
            {upcoming || openOrders ? <ConvList convs={convs.data} /> : <Chart o={o} />}
          </div>
        </div>

        {(upcoming || openOrders) && (
          <div className="card section">
            <div className="section-head"><h2>Customers per day</h2>
              <div className="legend"><span><i style={{ background: "var(--brand)" }} />conversations</span><span><i style={{ background: "var(--accent)" }} />booked / ordered</span></div></div>
            <Chart o={o} bare />
          </div>
        )}

        <div className="section">
          <div className="section-head"><h2>How well it's working</h2></div>
          <div className="grid-4">
            <Stat icon={CheckCircle2} label="Finished the job" value={pct(o.task_completion_rate)} hint="booked, ordered or answered fully · aim for 80%+" />
            <Stat icon={Hand} label="Handled without you" value={o.handoff_rate == null ? "—" : pct(1 - o.handoff_rate)} hint="calls not passed to you · aim for 85%+" />
            <Stat icon={Zap} label="Reply speed" value={o.latency_p95_ms == null ? "—" : (o.latency_p95_ms / 1000).toFixed(1) + "s"} hint="slowest typical reply" />
            <Stat icon={Gauge} label="Call minutes used" value={`${o.usage.used_minutes}`} hint={`of ${o.usage.included_minutes} on your ${o.usage.plan} plan`}>
              <div className="progress" style={{ marginTop: 10 }}><div style={{ width: `${Math.min(100, (o.usage.used_minutes / Math.max(1, o.usage.included_minutes)) * 100)}%` }} /></div>
            </Stat>
          </div>
        </div>

        <div className="card section row between">
          <div className="row" style={{ gap: 12 }}><div className="avatar"><Send size={16} /></div>
            <div><b>Daily summary on WhatsApp</b><div className="small muted">Every night at 9 pm you get a voice note of the day. Want today's now?</div></div></div>
          <button className="btn ghost" onClick={() => api("/api/jobs/daily-summary", { method: "POST" })
            .then(() => toast("Summary queued — see Messages sent")).catch((e) => toast(e.message, "bad"))}>Send now</button>
        </div>
      </>)}
    </>
  );
}

function ConvList({ convs }) {
  if (!convs) return <div className="card-body"><Skeleton rows={3} height={40} /></div>;
  if (!convs.length) return <Empty icon={MessagesSquare} title="No conversations yet">Share your link or QR poster and your first customer chats appear here.</Empty>;
  return (
    <div className="list">{convs.map((c) => (
      <Link key={c.id} href={`/conversations?id=${c.id}`} className="list-row" style={{ color: "inherit" }}>
        <div className={"avatar " + c.channel}><ChannelIcon channel={c.channel} /></div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="small muted">{when(c.started)}</div>
          <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.first || "—"}</div>
        </div>
        {c.handoff ? <Pill value="handoff" /> : c.outcome && <Pill value={c.outcome} />}
      </Link>))}
    </div>
  );
}

function Chart({ o, bare }) {
  const max = Math.max(1, ...o.series.map((d) => d.conversations));
  const step = o.series.length > 14 ? 5 : 1;
  const bars = (
    <div className="bars">
      {o.series.map((d, i) => (
        <div key={d.date} className="bar" title={`${d.date}: ${d.conversations} conversations, ${d.completed} booked/ordered`}>
          <div className="fill" style={{ height: `${(d.conversations / max) * 100}%` }}>
            <div className="done" style={{ height: d.conversations ? `${(d.completed / d.conversations) * 100}%` : 0 }} />
          </div>
          <div className="x">{i % step === 0 ? (o.series.length <= 7 ? new Date(d.date).toLocaleDateString("en-IN", { weekday: "short" }) : d.date.slice(8)) : " "}</div>
        </div>
      ))}
    </div>
  );
  return bare ? bars : <div className="card-body">{bars}</div>;
}
