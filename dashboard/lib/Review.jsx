"use client";

import { useState } from "react";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// Shows what the AI read from a menu / rate card so the team can fix it before it goes live.
export default function Review({ data, onApply, busy }) {
  const [d, setD] = useState(() => ({ services: [], products: [], hours: [], staff: [], faqs: [], ...data }));
  const edit = (list, i, k) => (e) => {
    const rows = [...d[list]];
    rows[i] = { ...rows[i], [k]: e.target.type === "number" ? Number(e.target.value) : e.target.value };
    setD({ ...d, [list]: rows });
  };
  const drop = (list, i) => setD({ ...d, [list]: d[list].filter((_, j) => j !== i) });
  const add = (list, row) => setD({ ...d, [list]: [...d[list], row] });

  const table = (list, cols, blank) => (
    <>
      <table style={{ marginBottom: 6 }}>
        <thead><tr>{cols.map(([k, l]) => <th key={k}>{l}</th>)}<th /></tr></thead>
        <tbody>{d[list].map((r, i) => (
          <tr key={i}>{cols.map(([k, , type]) => (
            <td key={k}><input type={type || "text"} value={r[k] ?? ""} onChange={edit(list, i, k)} /></td>))}
            <td><button className="btn ghost small" onClick={() => drop(list, i)}>✕</button></td></tr>))}
        </tbody>
      </table>
      <button className="btn ghost small" onClick={() => add(list, blank)}>+ Add</button>
    </>
  );

  return (
    <div>
      {d.about && <p className="small"><b>About:</b> {d.about}</p>}
      {d.hours.length > 0 && <p className="small"><b>Hours:</b> {d.hours.map((h) => `${DAYS[h.weekday]} ${h.opens}-${h.closes}`).join(" · ")}</p>}
      {(d.services.length > 0 || !d.products.length) && (<>
        <h2>Services ({d.services.length})</h2>
        {table("services", [["name", "Name"], ["price_inr", "₹", "number"], ["duration_min", "Minutes", "number"]],
          { name: "", price_inr: 0, duration_min: 30 })}
      </>)}
      {d.products.length > 0 && (<>
        <h2>Items ({d.products.length})</h2>
        {table("products", [["name", "Name"], ["price_inr", "₹", "number"], ["unit", "Unit"], ["aliases", "Other names"]],
          { name: "", price_inr: 0, unit: "1 pc", aliases: "" })}
      </>)}
      {d.staff.length > 0 && <p className="small"><b>Staff:</b> {d.staff.map((s) => s.name).join(", ")}</p>}
      {d.faqs.length > 0 && <p className="small"><b>Facts:</b> {d.faqs.map((f) => `${f.question}: ${f.answer}`).join(" · ")}</p>}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn" disabled={busy} onClick={() => onApply(d)}>{busy ? "Saving…" : "Looks right: save to shop"}</button>
        <span className="small muted">Replaces the sample prices; items with the same name are updated.</span>
      </div>
    </div>
  );
}
