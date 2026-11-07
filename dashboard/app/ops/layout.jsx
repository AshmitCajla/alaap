"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BarChart3, Bot, Inbox, LogOut, Phone, Store } from "lucide-react";
import { getOpsToken, opsApi, setOpsToken } from "../../lib/ops";
import { ToastProvider } from "../../lib/ui";

const NAV = [
  { href: "/ops", label: "Shops", icon: Store },
  { href: "/ops/intakes", label: "Inbox", badge: "new_intakes", icon: Inbox },
  { href: "/ops/numbers", label: "Numbers", icon: Phone },
  { href: "/ops/usage", label: "Usage & cost", icon: BarChart3 },
];

export default function OpsLayout({ children }) {
  const path = usePathname();
  const router = useRouter();
  const [ov, setOv] = useState(null);
  const isLogin = path === "/ops/login";

  useEffect(() => {
    if (isLogin) return;
    if (!getOpsToken()) { router.replace("/ops/login"); return; }
    const load = () => opsApi("/overview").then(setOv).catch(() => {});
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [isLogin, router, path]);

  if (isLogin) return children;
  if (!ov) return <div className="main"><div className="skel" style={{ height: 32, width: 220, marginBottom: 20 }} /><div className="skel" style={{ height: 120 }} /></div>;
  const on = (n) => (n.href === "/ops" ? path === "/ops" || path.startsWith("/ops/shops") : path.startsWith(n.href));
  return (
    <ToastProvider>
      <div className="shell">
        <nav className="side">
          <div className="brand"><span className="logo"><Bot size={18} /></span>Alaap</div>
          <div className="biz"><b>Team console</b><span>{ov.shops} shops · {ov.stages.live || 0} live</span></div>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={"nav" + (on(n) ? " on" : "")}>
              <n.icon size={18} />{n.label}{n.badge && ov[n.badge] ? <span className="count">{ov[n.badge]}</span> : null}
            </Link>
          ))}
          <div className="spacer" />
          <a href="#" className="nav" onClick={(e) => { e.preventDefault(); setOpsToken(null); router.replace("/ops/login"); }}><LogOut size={18} />Sign out</a>
        </nav>
        <header className="topbar"><div className="brand"><span className="logo" style={{ width: 26, height: 26 }}><Bot size={15} /></span>Alaap <span>· team</span></div></header>
        <main className="main">{children}</main>
        <nav className="bottom-nav" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          {NAV.map((n) => <Link key={n.href} href={n.href} className={on(n) ? "on" : ""}><n.icon size={21} />{n.label.split(" ")[0]}</Link>)}
        </nav>
      </div>
    </ToastProvider>
  );
}
