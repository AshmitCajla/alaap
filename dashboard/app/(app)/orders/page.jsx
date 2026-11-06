"use client";

import { api, rupees } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";

const NEXT = { placed: "preparing", preparing: "out_for_delivery", out_for_delivery: "delivered" };
const LABEL = { preparing: "Start packing", out_for_delivery: "Out for delivery", delivered: "Delivered" };

export default function Orders() {
  const { data, error, reload } = useData("/api/orders");
  const set = (id, status) => api(`/api/orders/${id}`, { method: "PATCH", body: { status } }).then(reload);
  if (error) return <div className="err">{error}</div>;
  return (
    <>
      <h1>Orders</h1>
      <p className="sub">Moving an order along sends the customer a WhatsApp update.</p>
      {!data ? <div className="muted">Loading…</div> : data.length === 0 ? <div className="card muted">No orders yet.</div> : (
        <div className="scroll"><table>
          <thead><tr><th>Order</th><th>Items</th><th>Deliver to</th><th>Slot</th><th>Total</th><th>Payment</th><th>Status</th><th></th></tr></thead>
          <tbody>{data.map((o) => (
            <tr key={o.id}>
              <td><b>{o.ref}</b><div className="muted small">{o.created}</div></td>
              <td>{o.items.map((i) => <div key={i.name}>{i.qty} × {i.name}</div>)}</td>
              <td>{o.customer} · {o.phone}<div className="muted small">{o.address}{o.landmark ? `, near ${o.landmark}` : ""}, {o.pincode}</div></td>
              <td>{o.slot}</td>
              <td>{rupees(o.total_inr)}</td>
              <td><Pill value={o.payment_status} /> <span className="muted small">{o.payment_method.toUpperCase()}</span></td>
              <td><Pill value={o.status} /></td>
              <td className="row">
                {NEXT[o.status] && <button className="btn small" onClick={() => set(o.id, NEXT[o.status])}>{LABEL[NEXT[o.status]]}</button>}
                {["placed", "preparing"].includes(o.status) &&
                  <button className="btn ghost small" onClick={() => confirm(`Cancel order ${o.ref}?`) && set(o.id, "cancelled")}>Cancel</button>}
                {o.conversation_id && <a className="small" href={`/conversations?id=${o.conversation_id}`}>transcript</a>}
              </td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </>
  );
}
