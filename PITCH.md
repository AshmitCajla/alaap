# Alaap — solution pitch

**An AI front desk for India's small shops · "Har call ka jawab"**
The Great Indian AI Internship Challenge by Gnani AI · Ashmit Cajla ·
[One-page PDF](docs/Alaap-Solution-Pitch.pdf) · [Demo video (2:56)](demo/alaap-demo.mp4)

## The problem
India's salons, clinics, kiranas and coaching centres run on phone calls, and most have one person to answer them.
Calls go unanswered while the owner serves someone at the counter, after closing time, or when two phones ring at once,
and a missed call is often a booking that goes to the shop next door. Menu-based IVRs and English chatbots don't fit
customers who speak Hindi, Punjabi and the mix in between.

## The solution
**Alaap answers every call, WhatsApp message and web chat like a trained receptionist**, in the customer's own language.
It checks real free slots and stock, books appointments, takes orders with UPI payment links, logs complaints, qualifies
leads, and passes anything it can't solve to the owner on WhatsApp. Owners see everything in a dashboard and change
prices or timings by simply telling it ("Facial ka rate 900 kar do"). Shops set it up in minutes from a photo of their
rate card, or the Alaap team sets it up for them and lends them a phone number.

## How Gnani AI powers the voice
| Gnani Prisma (speech-to-text) | Gemini (reasoning) | Gnani Timbre (text-to-speech) |
|---|---|---|
| Streaming recognition over WebSocket on every call; Hindi, Punjabi, English and code-mixed speech; its voice-activity detection ends each turn; the shop's service names are sent as keyterms | Tool calls for free slots, bookings, orders, complaints and leads; reads back and saves only after a clear "yes"; answers only from the shop's own data | Streamed sentence by sentence, so it starts talking early; 13 voices; numbers spoken naturally ("saade chhe baje"); also answers WhatsApp voice notes |

## Built to be trusted
- **Safe actions:** every booking or order is checked in code, read back, and confirmed only after the customer replies.
- **Correct under load:** database row locks prevent double bookings and overselling (tested with 20 simultaneous confirmations).
- **Security:** per-shop data isolation; only real caller ID unlocks a customer's bookings; signed webhooks.
- **Tested:** 44 automated tests, live conversation checks against the real models, and an end-to-end voice-call test.
- **Stack:** FastAPI · Next.js · Postgres · Redis · Docker + Caddy (HTTPS) · Exotel, WhatsApp Cloud API, Razorpay.

## Status and next steps
- **Working MVP:** live voice calls in the browser, web chat, owner dashboard, Ask Alaap, team console and billing. In the
  [demo video](demo/alaap-demo.mp4) a real call books a slot end to end.
- **Honest numbers:** on free-tier Gemini the caller hears Riya 2.3–3.0 s after speaking and gets her answer in 2.6–4.9 s;
  a paid tier should bring this down.
- **Next:** connect the Exotel phone line and the WhatsApp Business API, then pilot with 10 shops in Patiala.
- **Business model:** monthly plans ₹999 / ₹2,499 / ₹5,999 with a 14-day trial, plus done-for-you setup.

**Impact:** a small shop gets a front desk that never misses a call, speaks its customers' language and never invents a
price, and the owner gets every booking, order and complaint on WhatsApp.
