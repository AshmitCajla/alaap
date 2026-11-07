"use client";

import Link from "next/link";
import { useState } from "react";
import { MapPin, MessageSquareText, Phone, ShoppingBag, Truck } from "lucide-react";
import { api, rupees } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";
import { Empty, ErrorBox, PageHead, Seg, Skeleton, phoneFmt, useToast, when } from "../../../lib/ui";

const NEXT = { placed: "preparing", preparing: "out_for_delivery", out_for_delivery: "delivered" };
const ACTION = { preparing: "Start packing", out_for_delivery: "Send for delivery", delivered: "Mark delivered" };

export default function Orders() {
  const toast = useToast();
  const [view, setView] = useState("open");
  const { data, error, reload } = useData("/api/orders");
  const set = (o, status) => api(`/api/orders/${o.id}`, { method: "PATCH", body: { status } })
    .then(() => { toast(`Order ${o.ref}: customer told on WhatsApp`); reload(); }).catch((e) => toast(e.message, "bad"));
  if (error) return <ErrorBox error={error} />;
  const open = ["placed", "preparing", "out_for_delivery"];
  const rows = (data || []).filter((o) => view === "all" || (view === "open" ? open.includes(o.status) : !open.includes(o.status)));

  return (
    <>
      <PageHead title="Orders" sub="Moving an order along sends the customer a WhatsApp update automatically.">
        <Seg value={view} onChange={setView} options={[["open", "To do"], ["closed", "Finished"], ["all", "All"]]} />
      </PageHead>
      {!data ? <Skeleton rows={3} height={120} /> : !rows.length ? (
        <div className="card"><Empty icon={ShoppingBag} title={view === "open" ? "No orders waiting" : "Nothing here"}>
          Orders placed on calls, WhatsApp or your link appear here with the items, address and slot.</Empty></div>
      ) : (
        <div className="grid-2">{rows.map((o) => (
          <div key={o.id} className="card">
            <div className="row between" style={{ marginBottom: 10 }}>
              <div><b style={{ fontSize: 16 }}>#{o.ref}</b> <span className="muted small">· {when(o.created)}</span></div>
              <Pill value={o.status} />
            </div>
            <div className="row between" style={{ alignItems: "flex-start" }}>
              <div><b>{o.customer}</b>
                <div className="small"><a href={`tel:${o.phone}`} className="row" style={{ gap: 4 }}><Phone size={13} />{phoneFmt(o.phone)}</a></div></div>
              <div style={{ textAlign: "right" }}><b style={{ fontSize: 18 }}>{rupees(o.total_inr)}</b>
                <div className="small"><Pill value={o.payment_status} /> <span className="muted">{o.payment_method.toUpperCase()}</span></div></div>
            </div>
            <div style={{ margin: "12px 0", padding: "10px 12px", background: "var(--panel-2)", borderRadius: 10, border: "1px solid var(--line-2)" }}>
              {o.items.map((i) => <div key={i.name} className="row between small"><span>{i.qty} × {i.name}</span></div>)}
            </div>
            <div className="small muted row" style={{ gap: 6, alignItems: "flex-start", flexWrap: "nowrap" }}><MapPin size={14} style={{ flex: "none", marginTop: 2 }} />
              <span>{o.address}{o.landmark ? `, near ${o.landmark}` : ""}, {o.pincode}</span></div>
            <div className="small muted row" style={{ gap: 6, marginTop: 4 }}><Truck size={14} />{o.slot}</div>
            <div className="row" style={{ marginTop: 14 }}>
              {NEXT[o.status] && <button className="btn" onClick={() => set(o, NEXT[o.status])}>{ACTION[NEXT[o.status]]}</button>}
              {["placed", "preparing"].includes(o.status) &&
                <button className="btn danger small" onClick={() => confirm(`Cancel order ${o.ref}? The customer will be told.`) && set(o, "cancelled")}>Cancel</button>}
              {o.conversation_id && <Link className="btn plain small" href={`/conversations?id=${o.conversation_id}`}><MessageSquareText size={14} />Conversation</Link>}
            </div>
          </div>
        ))}</div>
      )}
    </>
  );
}
