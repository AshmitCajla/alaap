"use client";

import { Pill, useData } from "../../../lib/Shell";

export default function Outbox() {
  const { data, error } = useData("/api/outbox");
  if (error) return <div className="err">{error}</div>;
  return (
    <>
      <h1>WhatsApp outbox</h1>
      <p className="sub">Confirmations, reminders, payment links, follow-ups and your alerts. “logged” means WhatsApp isn't connected yet
        (Settings → Channels), so the message was kept here instead of sent.</p>
      {!data ? <div className="muted">Loading…</div> : data.length === 0 ? <div className="card muted">Nothing yet.</div> : (
        <div className="scroll"><table>
          <thead><tr><th>Send at</th><th>To</th><th>Kind</th><th>Message</th><th>Status</th></tr></thead>
          <tbody>{data.map((o) => (
            <tr key={o.id}>
              <td className="small">{o.send_after}</td><td className="small">{o.to}</td>
              <td><span className="pill grey">{o.kind.replaceAll("_", " ")}</span>{o.has_audio && <div className="small muted">+ voice note</div>}</td>
              <td style={{ whiteSpace: "pre-wrap" }}>{o.body}{o.error && <div className="small err">{o.error}</div>}</td>
              <td><Pill value={o.status} /></td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </>
  );
}
