"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const MeContext = createContext(null);
export const useMe = () => useContext(MeContext);

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/setup", label: "Setup" },
  { href: "/share", label: "Share kit" },
  { href: "/appointments", label: "Appointments", skill: "appointments" },
  { href: "/orders", label: "Orders", skill: "orders" },
  { href: "/leads", label: "Leads", skill: "leads" },
  { href: "/inbox", label: "Callbacks & complaints" },
  { href: "/conversations", label: "Conversations" },
  { href: "/outbox", label: "WhatsApp outbox" },
  { href: "/assistant", label: "Ask Alaap" },
  { href: "/billing", label: "Plan & billing" },
  { href: "/settings", label: "Settings" },
];

export default function Shell({ children }) {
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState(null);

  const [plan, setPlan] = useState(null);
  useEffect(() => {
    if (!getToken()) { router.replace("/welcome"); return; }
    api("/api/me").then(setMe).catch(() => {});
    api("/api/billing").then((b) => setPlan(b.status)).catch(() => {});
  }, [router]);

  if (!me) return <div className="main muted">Loading…</div>;
  const skills = new Set(me.business.skills);
  return (
    <MeContext.Provider value={me}>
      <div className="shell">
        <nav className="side">
          <div className="brand">Alaap</div>
          <div className="biz">{me.business.name}</div>
          {NAV.filter((n) => !n.skill || skills.has(n.skill)).map((n) => (
            <Link key={n.href} href={n.href} className={path === n.href ? "on" : ""}>{n.label}</Link>
          ))}
          <div className="spacer" />
          <a href="#" onClick={(e) => { e.preventDefault(); setToken(null); router.replace("/login"); }}>Sign out</a>
        </nav>
        <main className="main">
          {plan && (plan.state === "expired" || (plan.state === "trial" && plan.days_left <= 5)) && (
            <div className="card" style={{ marginBottom: 16, borderColor: plan.state === "expired" ? "var(--bad)" : "var(--warn)",
                                         background: plan.state === "expired" ? "var(--bad-soft)" : "var(--warn-soft)" }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span>{plan.state === "expired" ? "Your Alaap plan has ended." : `Free trial: ${plan.days_left} day${plan.days_left === 1 ? "" : "s"} left.`}</span>
                <Link className="btn small" href="/billing">Choose a plan</Link>
              </div>
            </div>
          )}
          {children}
        </main>
      </div>
    </MeContext.Provider>
  );
}

export function useData(path, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = () => api(path).then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [path, ...deps]); // eslint-disable-line
  return { data, error, reload: load };
}

export function Pill({ value }) {
  const tone = {
    booked: "", done: "good", cancelled: "grey", no_show: "bad", placed: "warn", preparing: "warn",
    out_for_delivery: "", delivered: "good", paid: "good", pending: "warn", cod: "grey", new: "warn",
    contacted: "", visit_booked: "", won: "good", lost: "grey", open: "warn", closed: "grey", urgent: "bad",
    queued: "warn", sent: "good", failed: "bad", logged: "grey", ordered: "good", lead: "", callback: "warn",
    complaint: "bad", rescheduled: "",
  }[value];
  return <span className={"pill " + (tone ?? "grey")}>{String(value ?? "—").replaceAll("_", " ")}</span>;
}
