"use client";

import { useState } from "react";
import { api } from "./api";

export const VOICES = [["Shivani", "f"], ["Lakshmi", "f"], ["Kalpana", "f"], ["Chetana", "f"], ["Vasudha", "f"],
  ["Riyaa", "f"], ["Tarika", "f"], ["Avinash", "m"], ["Shubham", "m"], ["Prakash", "m"], ["Devansh", "m"],
  ["Yashraj", "m"], ["Harshad", "m"]];

/* value: {assistant_name, voice, speech_speed}; onChange(newValue) */
export default function VoicePicker({ value, onChange }) {
  const [playing, setPlaying] = useState(null);
  const [err, setErr] = useState(null);
  const set = (k, v) => onChange({ ...value, [k]: v });
  const chosen = value.voice || "Shivani";
  const female = VOICES.find(([v]) => v === chosen)?.[1] !== "m";

  const preview = async (voice) => {
    setPlaying(voice); setErr(null);
    try {
      const r = await api("/api/voice/preview", { method: "POST", body: { voice, speed: value.speech_speed || 1 } });
      const a = new Audio("data:audio/wav;base64," + r.audio);
      a.onended = () => setPlaying(null);
      await a.play();
    } catch (e) { setErr(e.message); setPlaying(null); }
  };

  return (
    <>
      <label>Assistant's name — callers hear "… se <b>{value.assistant_name || (female ? "Riya" : "Arjun")}</b> bol {female ? "rahi" : "raha"} hoon"
        <input value={value.assistant_name || ""} placeholder={female ? "Riya" : "Arjun"} onChange={(e) => set("assistant_name", e.target.value)} /></label>
      <label>Speaking speed: {(value.speech_speed || 1).toFixed(2)}×
        <input type="range" min="0.85" max="1.15" step="0.05" value={value.speech_speed || 1}
          onChange={(e) => set("speech_speed", Number(e.target.value))} /></label>
      <p className="small muted" style={{ margin: "4px 0 10px" }}>Pick the voice that suits your shop. Tap ▶ to hear it.</p>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
        {VOICES.map(([v, g]) => (
          <div key={v} className="card" onClick={() => set("voice", v)}
            style={{ padding: 10, cursor: "pointer", borderColor: chosen === v ? "var(--brand)" : undefined,
                     background: chosen === v ? "var(--brand-soft)" : undefined }}>
            <div className="row" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
              <div><b>{v}</b><div className="small muted">{g === "f" ? "Female" : "Male"}</div></div>
              <button className="btn ghost small" onClick={(e) => { e.stopPropagation(); preview(v); }}>
                {playing === v ? "…" : "▶"}</button>
            </div>
          </div>
        ))}
      </div>
      {err && <div className="err">{err}</div>}
      <p className="small muted">The assistant talks about itself as {female ? "a woman (karti hoon)" : "a man (karta hoon)"} to
        match the voice, and always says it's an AI assistant if asked.</p>
    </>
  );
}
