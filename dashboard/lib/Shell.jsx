"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import {
  BadgeIndianRupee, Bot, CalendarDays, Home, Inbox, LogOut, Menu, MessagesSquare, QrCode, Rocket, Send,
  Settings, ShoppingBag, Sparkles, Target, X,
} from "lucide-react";
import { api, getToken, setToken } from "./api";
import { ToastProvider } from "./ui";

const MeContext = createContext(null);
export const useMe = () => useContext(MeContext);

const GROUPS = [
  { items: [
    { href: "/", label: "Home", icon: Home },
    { href: "/assistant", label: "Ask Alaap", icon: Sparkles },
  ] },
  { label: "Customers", items: [
    { href: "/appointments", label: "Appointments", icon: CalendarDays, skill: "appointments" },
    { href: "/orders", label: "Orders", icon: ShoppingBag, skill: "orders" },
    { href: "/leads", label: "Leads", icon: Target, skill: "leads" },
    { href: "/inbox", label: "Callbacks", icon: Inbox, count: "open_tickets" },
    { href: "/conversations", label: "Conversations", icon: MessagesSquare },
  ] },
  { label: "Your assistant", items: [
    { href: "/setup", label: "Setup", icon: Rocket, count: "setup_left" },
    { href: "/share", label: "Share kit", icon: QrCode },
    { href: "/settings", label: "Settings", icon: Settings },
    { href: "/outbox", label: "Messages sent", icon: Send },
    { href: "/billing", label: "Plan & billing", icon: BadgeIndianRupee },
  ] },
];

const SHORT = { "Ask Alaap": "Ask", Appointments: "Bookings", Conversations: "Chats" };
const active = (path, href) => (href === "/" ? path === "/" : path.startsWith(href));

export default function Shell({ children }) {
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [plan, setPlan] = useState(null);
  const [counts, setCounts] = useState({});
  const [more, setMore] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.replace("/welcome"); return; }
    api("/api/me").then(setMe).catch(() => {});
    api("/api/billing").then((b) => setPlan(b.status)).catch(() => {});
  }, [router]);
  useEffect(() => {
    if (!me) return;
    const load = () => api("/api/counts").then(setCounts).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [me, path]);
  useEffect(() => setMore(false), [path]);

  if (!me) return <div className="main"><div className="skel" style={{ height: 32, width: 220, marginBottom: 20 }} /><div className="skel" style={{ height: 120 }} /></div>;
  const skills = new Set(me.business.skills);
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((n) => !n.skill || skills.has(n.skill)) }));
  const signOut = (e) => { e.preventDefault(); setToken(null); router.replace("/login"); };
  const primary = skills.has("appointments") ? "/appointments" : skills.has("orders") ? "/orders" : "/leads";
  const all = groups.flatMap((g) => g.items);
  const tabs = [all.find((n) => n.href === "/"), all.find((n) => n.href === primary), all.find((n) => n.href === "/conversations"),
    all.find((n) => n.href === "/assistant")].filter(Boolean);

  return (
    <MeContext.Provider value={me}>
      <ToastProvider>
        <div className="shell">
          <nav className="side" aria-label="Main">
            <div className="brand"><span className="logo"><Bot size={18} /></span>Alaap</div>
            <div className="biz">
              <b>{me.business.name}</b>
              <span>{me.user.support ? "Alaap team (support login)" : `${me.business.plan} plan`}</span>
            </div>
            {groups.map((g, i) => (
              <div key={i}>
                {g.label && <div className="nav-label">{g.label}</div>}
                {g.items.map((n) => (
                  <Link key={n.href} href={n.href} className={"nav" + (active(path, n.href) ? " on" : "")}>
                    <n.icon size={18} />{n.label}
                    {n.count && counts[n.count] > 0 && <span className="count">{counts[n.count]}</span>}
                  </Link>
                ))}
              </div>
            ))}
            <div className="spacer" />
            <a href="#" className="nav" onClick={signOut}><LogOut size={18} />Sign out</a>
          </nav>

          <header className="topbar">
            <div className="brand"><span className="logo" style={{ width: 26, height: 26 }}><Bot size={15} /></span>Alaap
              <span>· {me.business.name}</span></div>
            {counts.open_tickets > 0 && <Link href="/inbox" className="badge warn"><Inbox size={13} />{counts.open_tickets}</Link>}
          </header>

          <main className="main">
            {me.user.support && (
              <div className="callout info" style={{ marginBottom: 16 }}>
                <Bot size={18} /><div>You're inside <b>{me.business.name}</b>'s dashboard as the Alaap team. Changes apply to this shop.</div>
              </div>
            )}
            {plan && (plan.state === "expired" || (plan.state === "trial" && plan.days_left <= 5)) && (
              <div className={"callout " + (plan.state === "expired" ? "bad" : "warn")} style={{ marginBottom: 18, alignItems: "center" }}>
                <BadgeIndianRupee size={18} />
                <div style={{ flex: 1 }}>{plan.state === "expired" ? "Your Alaap plan has ended. Customers hear a short notice instead of your assistant."
                  : `Free trial: ${plan.days_left} day${plan.days_left === 1 ? "" : "s"} left.`}</div>
                <Link className="btn small" href="/billing">Choose a plan</Link>
              </div>
            )}
            {children}
          </main>

          <nav className="bottom-nav" aria-label="Quick">
            {tabs.map((n) => (
              <Link key={n.href} href={n.href} className={active(path, n.href) ? "on" : ""}><n.icon size={21} />{SHORT[n.label] || n.label}</Link>
            ))}
            <button onClick={() => setMore(true)} className={more ? "on" : ""}><Menu size={21} />More</button>
          </nav>
          {more && (<>
            <div className="sheet-bg" onClick={() => setMore(false)} />
            <div className="sheet" role="dialog" aria-label="All pages">
              <div className="row between" style={{ padding: "4px 6px 8px" }}><b>{me.business.name}</b>
                <button className="icon-btn" onClick={() => setMore(false)} aria-label="Close"><X size={16} /></button></div>
              {all.map((n) => <Link key={n.href} href={n.href} className={active(path, n.href) ? "on" : ""}><n.icon size={19} />{n.label}
                {n.count && counts[n.count] > 0 && <span className="badge warn" style={{ marginLeft: "auto" }}>{counts[n.count]}</span>}</Link>)}
              <a href="#" onClick={signOut}><LogOut size={19} />Sign out</a>
            </div>
          </>)}
        </div>
      </ToastProvider>
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

const TONE = {
  booked: "info", done: "good", cancelled: "grey", no_show: "bad", placed: "warn", preparing: "warn",
  out_for_delivery: "info", delivered: "good", paid: "good", pending: "warn", cod: "grey", new: "warn",
  contacted: "info", visit_booked: "info", won: "good", lost: "grey", open: "warn", closed: "grey", urgent: "bad",
  queued: "warn", sent: "good", failed: "bad", logged: "grey", ordered: "good", lead: "info", callback: "warn",
  complaint: "bad", rescheduled: "info", answered: "grey", handoff: "bad",
};
const LABEL = { no_show: "No-show", out_for_delivery: "On the way", visit_booked: "Visit booked", cod: "Cash on delivery",
  logged: "Not sent", queued: "Waiting", answered: "Answered", handoff: "Needs you" };

export function Pill({ value }) {
  const label = LABEL[value] ?? String(value ?? "—").replaceAll("_", " ");
  return <span className={"pill " + (TONE[value] ?? "grey")}>{label}</span>;
}
