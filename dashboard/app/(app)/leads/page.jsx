"use client";

import { api } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";

const STATUSES = ["new", "contacted", "visit_booked", "won", "lost"];

export default function Leads() {
  const { data, error, reload } = useData("/api/leads");
  const set = (id, status) => api(`/api/leads/${id}`, { method: "PATCH", body: { status } }).then(reload);
  if (error) return <div className="err">{error}</div>;
  return (
    <>
      <h1>Leads</h1>
      <p className="sub">Scored 0–100 on how complete and how soon. 70+ gets a WhatsApp alert to you right away.</p>
      {!data ? <div className="muted">Loading…</div> : data.length === 0 ? <div className="card muted">No leads yet.</div> : (
        <div className="scroll"><table>
          <thead><tr><th>Score</th><th>Who</th><th>Needs</th><th>Budget</th><th>Where / when</th><th>Status</th></tr></thead>
          <tbody>{data.map((l) => (
            <tr key={l.id}>
              <td><span className={"pill " + (l.score >= 70 ? "good" : l.score >= 40 ? "warn" : "grey")}>{l.score}</span></td>
              <td>{l.name || "—"}<div className="muted small">{l.phone} · {l.created}</div></td>
              <td>{l.need}{l.conversation_id && <div><a className="small" href={`/conversations?id=${l.conversation_id}`}>transcript</a></div>}</td>
              <td>{l.budget || "—"}</td>
              <td>{l.location || "—"}<div className="muted small">{l.preferred_time}</div></td>
              <td><select value={l.status} onChange={(e) => set(l.id, e.target.value)}>
                {STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</select></td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </>
  );
}
