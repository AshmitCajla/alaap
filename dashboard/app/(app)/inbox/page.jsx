"use client";

import { api } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";

export default function Inbox() {
  const { data, error, reload } = useData("/api/tickets");
  const set = (id, status) => api(`/api/tickets/${id}`, { method: "PATCH", body: { status } }).then(reload);
  if (error) return <div className="err">{error}</div>;
  return (
    <>
      <h1>Callbacks & complaints</h1>
      <p className="sub">Things Alaap couldn't finish and handed to you. Each one was also sent to your WhatsApp.</p>
      {!data ? <div className="muted">Loading…</div> : data.length === 0 ? <div className="card muted">Nothing waiting. 🎉</div> : (
        <div className="scroll"><table>
          <thead><tr><th>When</th><th>Type</th><th>Who</th><th>What</th><th>Status</th><th></th></tr></thead>
          <tbody>{data.map((t) => (
            <tr key={t.id}>
              <td className="small">{t.created}</td>
              <td><Pill value={t.kind} /> {t.urgency === "urgent" && <Pill value="urgent" />}</td>
              <td>{t.name || "—"}<div className="muted small"><a href={`tel:${t.phone}`}>{t.phone}</a></div></td>
              <td>{t.issue}{t.conversation_id && <div><a className="small" href={`/conversations?id=${t.conversation_id}`}>transcript</a></div>}</td>
              <td><Pill value={t.status} /></td>
              <td>{t.status === "open"
                ? <button className="btn small" onClick={() => set(t.id, "closed")}>Mark done</button>
                : <button className="btn ghost small" onClick={() => set(t.id, "open")}>Reopen</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </>
  );
}
