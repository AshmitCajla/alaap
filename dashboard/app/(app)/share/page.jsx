"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { API, api } from "../../../lib/api";
import { useMe } from "../../../lib/Shell";

function Copy({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  return <button className="btn ghost small" onClick={() => navigator.clipboard.writeText(text).then(() => {
    setDone(true); setTimeout(() => setDone(false), 1500); })}>{done ? "Copied ✓" : label}</button>;
}

export default function Share() {
  const me = useMe();
  const [s, setS] = useState(null);
  const [qr, setQr] = useState(null);
  const link = `${API}/c/${me.business.slug}`;

  useEffect(() => {
    api("/api/settings").then(setS);
    QRCode.toDataURL(link, { margin: 1, width: 520, color: { dark: "#0b3b37" } }).then(setQr);
  }, [link]);
  if (!s) return <div className="muted">Loading…</div>;
  const b = s.business;
  const name = b.assistant_name || "Riya";
  const exo = (b.exotel_number || "").replace(/\D/g, "").slice(-10);
  const shareText = `Ab ${b.name} se 24x7 baat kijiye — booking, rate, timing sab: ${link}`;

  const printPoster = () => { api("/api/setup/shared", { method: "POST" }).catch(() => {}); window.print(); };

  return (
    <>
      <style>{`
        @media print {
          body * { visibility: hidden !important; }
          .poster, .poster * { visibility: visible !important; }
          .poster { position: fixed; inset: 0; margin: 0 !important; border: 0 !important; box-shadow: none !important;
                    width: 100% !important; max-width: none !important; }
        }
        .poster { background: #fff; color: #0b3b37; border-radius: 18px; padding: 34px 28px; text-align: center;
                  max-width: 420px; border: 1px solid var(--line); }
        .poster h2 { font-size: 30px; margin: 4px 0 6px; color: #0b3b37; }
        .poster .big { font-size: 20px; font-weight: 700; margin: 6px 0 14px; }
        .poster img { width: 260px; height: 260px; }
        .poster .small { color: #35524f; }
      `}</style>
      <h1>Share kit</h1>
      <p className="sub">Put {name} wherever your customers already are. Each of these takes under a minute.</p>

      <div className="split" style={{ gridTemplateColumns: "1fr 440px", alignItems: "start" }}>
        <div>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>1. Your customer link</h2>
            <p className="small">Customers can call or chat with {name} here, from any phone, no app needed.</p>
            <div className="row" style={{ flexWrap: "nowrap" }}><input readOnly value={link} /><Copy text={link} />
              <a className="btn ghost small" href={link} target="_blank">Open</a></div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>2. Counter poster</h2>
            <p className="small">Print it and stick it at the counter or door. Customers scan it to book even when you're busy or closed.</p>
            <button className="btn" onClick={printPoster}>🖨️ Print poster</button>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>3. WhatsApp, Instagram, Google</h2>
            <div className="row">
              <a className="btn ghost small" target="_blank" href={`https://wa.me/?text=${encodeURIComponent(shareText)}`}>Share on WhatsApp</a>
              <Copy text={shareText} label="Copy message" />
            </div>
            <ul className="small">
              <li><b>WhatsApp status / groups:</b> send the message above to your regular customers.</li>
              <li><b>Instagram:</b> put the link in your bio.</li>
              <li><b>Google Business Profile:</b> add the link as your "Appointment" or "Order" link.</li>
            </ul>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>4. Your website</h2>
            <p className="small">Paste before <code>&lt;/body&gt;</code>. A chat bubble with voice appears on every page.</p>
            <pre>{`<script src="${API}/widget.js" data-business="${b.slug}" defer></script>`}</pre>
            <Copy text={`<script src="${API}/widget.js" data-business="${b.slug}" defer></script>`} label="Copy code" />
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 style={{ marginTop: 0 }}>5. Missed calls on your shop phone</h2>
            {exo ? (<>
              <p className="small">Dial these once from your shop phone. Calls you can't pick up go to {name} instead of ringing out.</p>
              <table><tbody>
                <tr><td>When you don't answer</td><td><code>**61*{exo}#</code></td><td><Copy text={`**61*${exo}#`} /></td></tr>
                <tr><td>When you're busy on another call</td><td><code>**67*{exo}#</code></td><td><Copy text={`**67*${exo}#`} /></td></tr>
                <tr><td>When phone is off / no network</td><td><code>**62*{exo}#</code></td><td><Copy text={`**62*${exo}#`} /></td></tr>
                <tr><td>Turn all forwarding off</td><td><code>##002#</code></td><td><Copy text="##002#" /></td></tr>
              </tbody></table>
              <p className="small muted">These are standard GSM codes; most Indian operators support them. Some charge forwarded calls at normal rates.</p>
            </>) : (
              <p className="small">Needs an Alaap phone number (via Exotel). Add it in <a href="/settings">Settings → Channels</a> and the forwarding
                codes appear here. Until then, the customer link and poster already work.</p>
            )}
          </div>
        </div>

        <div className="poster">
          <div className="small">{b.name}</div>
          <h2>Busy? Closed? Still talk to us!</h2>
          <div className="big">Scan → call or chat with {name}</div>
          {qr && <img src={qr} alt="QR code" />}
          <p style={{ fontSize: 17, margin: "12px 0 4px" }}>Booking · Rates · Timings · Orders</p>
          <p className="small">Hindi · Punjabi · English · 24×7<br />{link.replace(/^https?:\/\//, "")}</p>
        </div>
      </div>
    </>
  );
}
