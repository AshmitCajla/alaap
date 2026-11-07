"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { opsApi } from "../../../lib/ops";

export default function Intakes() {
  const [status, setStatus] = useState("new");
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const load = () => opsApi(`/intakes?status=${status}`).then((d) => setRows(d.intakes));
  useEffect(() => { load(); }, [status]); // eslint-disable-line
  const mark = async (i, st) => { await opsApi(`/intakes/${i.id}`, { method: "PATCH", body: { status: st } }); load(); };
  const show = async (i) => setOpen(open?.id === i.id ? null : await opsApi(`/intakes/${i.id}`));

  return (
    <>
      <h1>Inbox</h1>
      <p className="sub">Shops asking to join, and menus / rate cards owners sent to Alaap's WhatsApp.</p>
      <div className="tabs">{["new", "applied", "done", "discarded", "all"].map((s) => (
        <button key={s} className={status === s ? "on" : ""} onClick={() => setStatus(s)}>{s}</button>))}</div>
      {!rows ? <div className="muted">Loading…</div> : !rows.length ? <div className="card muted">Nothing here.</div> : (
        <div className="scroll"><table>
          <thead><tr><th>When</th><th>From</th><th>What</th><th>Shop</th><th /></tr></thead>
          <tbody>{rows.map((i) => (<Fragment key={i.id}>
            <tr>
              <td className="small muted">{i.created_at.replace("T", " ")}</td>
              <td>{i.from_phone || <span className="muted">team</span>}</td>
              <td>{i.kind === "join" ? <b>Wants Alaap</b> : i.kind === "photo" ? "📷 Menu / rate card photo" : "Price list text"}
                {i.text && <div className="small muted">{i.text.slice(0, 140)}</div>}
                {i.extracted && <div className="small">Read: {(i.extracted.services || []).length} services, {(i.extracted.products || []).length} items</div>}</td>
              <td>{i.shop ? <Link href={`/ops/shops/${i.business_id}`}>{i.shop}</Link> : <span className="pill warn">no shop yet</span>}</td>
              <td><div className="row" style={{ flexWrap: "nowrap" }}>
                {!i.business_id && <Link className="btn small" href={`/ops?new=1&phone=${i.from_phone || ""}&intake=${i.id}`}>Create shop</Link>}
                {i.business_id && i.kind !== "join" && <Link className="btn small" href={`/ops/shops/${i.business_id}`}>Review</Link>}
                {i.has_media && <button className="btn ghost small" onClick={() => show(i)}>{open?.id === i.id ? "Hide" : "Photo"}</button>}
                {i.status === "new" && <button className="btn ghost small" onClick={() => mark(i, "done")}>Done</button>}
                {i.status === "new" && <button className="btn ghost small" onClick={() => mark(i, "discarded")}>Discard</button>}
              </div></td>
            </tr>
            {open?.id === i.id && open.media && (
              <tr><td colSpan={5}><img src={open.media} alt="sent photo" style={{ maxWidth: "100%", maxHeight: 480, borderRadius: 8 }} /></td></tr>)}
          </Fragment>))}</tbody>
        </table></div>
      )}
    </>
  );
}
