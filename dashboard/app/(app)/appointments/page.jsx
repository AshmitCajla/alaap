"use client";

import { api } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";

export default function Appointments() {
  const { data, error, reload } = useData("/api/appointments?days_back=7&days_ahead=30");
  const set = (id, status) => api(`/api/appointments/${id}`, { method: "PATCH", body: { status } }).then(reload);
  if (error) return <div className="err">{error}</div>;
  let lastDay = null;
  return (
    <>
      <h1>Appointments</h1>
      <p className="sub">Last week and the next 30 days. Customers get WhatsApp confirmations and a reminder 2 hours before.</p>
      {!data ? <div className="muted">Loading…</div> : data.length === 0 ? <div className="card muted">No appointments yet.</div> : (
        <div className="scroll"><table>
          <thead><tr><th>Time</th><th>Service</th><th>Staff</th><th>Customer</th><th>Ref</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {data.map((a) => {
              const day = a.start.slice(0, 10);
              const header = day !== lastDay; lastDay = day;
              return [
                header && <tr key={day}><td colSpan={7} style={{ background: "var(--bg)", fontWeight: 600 }}>
                  {new Date(day).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" })}</td></tr>,
                <tr key={a.id}>
                  <td>{a.start.slice(11)}</td><td>{a.service}</td><td>{a.staff}</td>
                  <td>{a.customer}<div className="muted small">{a.phone}</div></td>
                  <td>{a.ref}<div className="muted small">{a.channel}</div></td><td><Pill value={a.status} /></td>
                  <td className="row">
                    {a.status === "booked" && <>
                      <button className="btn ghost small" onClick={() => set(a.id, "done")}>Done</button>
                      <button className="btn ghost small" onClick={() => set(a.id, "no_show")}>No-show</button>
                    </>}
                    {a.conversation_id && <a className="small" href={`/conversations?id=${a.conversation_id}`}>transcript</a>}
                  </td>
                </tr>,
              ];
            })}
          </tbody>
        </table></div>
      )}
    </>
  );
}
