"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { AlertCircle, CheckCircle2, Globe, MessageCircle, Phone, UserRound } from "lucide-react";

// ---------- formatting ----------
const pad = (n) => String(n).padStart(2, "0");
export function parseAt(s) {
  if (!s) return null;
  if (s instanceof Date) return s;
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})[ T]?(\d{2})?:?(\d{2})?/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)) : new Date(s);
}
export function time12(s) {
  const d = parseAt(s); if (!d) return "—";
  const h = d.getHours(), mm = pad(d.getMinutes());
  return `${((h + 11) % 12) + 1}:${mm} ${h < 12 ? "am" : "pm"}`;
}
export function dayLabel(s) {
  const d = parseAt(s); if (!d) return "—";
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(d); day.setHours(0, 0, 0, 0);
  const diff = Math.round((day - today) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
}
export function when(s) {
  const d = parseAt(s); if (!d) return "—";
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins >= 0 && mins < 1) return "just now";
  if (mins >= 0 && mins < 60) return `${mins} min ago`;
  if (mins >= 0 && mins < 12 * 60 && dayLabel(d) === "Today") return `${Math.round(mins / 60)} h ago`;
  return `${dayLabel(d)}, ${time12(d)}`;
}
export const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
export const phoneFmt = (p) => (p && /^\d{10}$/.test(p) ? `${p.slice(0, 5)} ${p.slice(5)}` : p || "");

export const CHANNEL = {
  phone: { label: "Phone call", Icon: Phone }, whatsapp: { label: "WhatsApp", Icon: MessageCircle },
  web: { label: "Web chat", Icon: Globe }, owner: { label: "You", Icon: UserRound },
};
export function ChannelIcon({ channel, size = 16 }) {
  const C = (CHANNEL[channel] || CHANNEL.web).Icon;
  return <C size={size} />;
}

// ---------- building blocks ----------
export function PageHead({ title, sub, children }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{sub && <p className="sub">{sub}</p>}</div>
      {children && <div className="row">{children}</div>}
    </div>
  );
}

export function Stat({ icon: Icon, label, value, hint, star, children }) {
  return (
    <div className={"card stat" + (star ? " star" : "")}>
      <div className="label">{Icon && <span className="ico"><Icon size={16} /></span>}{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
      {children}
    </div>
  );
}

export function Empty({ icon: Icon = CheckCircle2, title, children, action }) {
  return (
    <div className="empty">
      <div className="ico"><Icon size={24} /></div>
      <b>{title}</b>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ rows = 3, height = 54 }) {
  return <div className="stack">{Array.from({ length: rows }, (_, i) => <div key={i} className="skel" style={{ height }} />)}</div>;
}

export function ErrorBox({ error }) {
  return <div className="callout bad"><AlertCircle size={18} /><div>{error}</div></div>;
}

export function Seg({ value, options, onChange }) {
  return (
    <div className="seg">
      {options.map(([v, l]) => <button key={v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}

// ---------- toasts ----------
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const show = useCallback((text, tone = "") => {
    const id = Math.random();
    setItems((x) => [...x, { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div className="toast-wrap" aria-live="polite">
        {items.map((t) => <div key={t.id} className={"toast " + t.tone}>
          {t.tone === "bad" ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}
