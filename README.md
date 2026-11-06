# Alaap — AI front desk for Indian businesses

Answers calls, WhatsApp (text and voice notes) and web chats in Hindi, Punjabi, English or a mix.
It takes bookings and orders, sends UPI links, qualifies leads, handles complaints, follows up,
and tells the owner what happened, including a daily voice note in their language.

**One conversation engine plus a library of skills.** Each skill is the fields it collects, its rules and
the tools it may call. Supporting a new kind of business means adding skills, not building a new product.

| Skill | Tools | For |
|---|---|---|
| Appointments | find slots, prepare booking / reschedule / cancel | salons, clinics, coaching visits |
| Enquiries | answers from the profile only, else callback | everyone |
| Complaints and handoff | log complaint; urgent phone calls transfer to the owner | everyone |
| Orders and delivery | catalog search (Hinglish names), pincode and slots, prepare order | kirana, restaurants, pharmacies |
| Payments | Razorpay UPI payment links, paid webhook | Pro plan |
| Order status | status, cancel before dispatch | Pro plan |
| Leads | qualify, score 0–100, hot-lead alert | coaching, real estate, gyms |
| Follow-ups | feedback after visits, reorder reminders, win-back, lead follow-up | scheduler |
| Owner assistant | "aaj kitne orders aaye?", "kal shop band hai, sab shift karo" | owners |

**Trust first:** the model never writes data directly. `prepare_*` tools check everything in plain code
(hours, closures, staff, stock, pincodes, totals) and return a read-back; `confirm_action` saves it only
after the customer replies, and checks again. The model answers only from the business profile.

## Plug and play for a business

1. **Sign up** (dashboard → New business): pick the kind of business. Alaap starts with sensible sample services,
   timings and FAQs for that kind, so it can take calls from the first minute.
2. **Teach it in one minute** (Setup → Teach): upload a **photo of the rate card or menu**, paste a price list, or give
   a website. Gemini reads services, prices, durations, items, staff, timings and facts; the owner checks and saves.
3. **Pick a voice** with previews, and a name for the assistant.
4. **Try it**: call your own assistant right inside the setup page.
5. **Go live** (Share kit): customer page `/c/<slug>` with a Call button, a printable **QR counter poster**,
   WhatsApp/Instagram/Google sharing, a one-line website snippet, and the call-forwarding codes for missed calls.
6. **Run it by talking** (Ask Alaap, or WhatsApp from the owner's number): "Facial ka rate 900 kar do",
   "yaad rakhna, parking peeche hai", "Sunday ko 11 se 5 khulenge", "kal shop band hai, sab shift karo".

The overview shows a setup checklist until everything is done.

## How calls sound human

- **Listens like a person:** Gnani's streaming speech-to-text ends each utterance as the caller stops; short
  openers ("haan ji, …") wait for the rest of the sentence instead of getting their own answer.
- **Starts talking early:** the reply streams from the LLM sentence by sentence, and each sentence streams from
  Gnani's WebSocket TTS (about 0.2 s to first audio). Typical gap after the caller stops: about 2 seconds.
- **Fills pauses:** a quick "achha" / "ek second ji, dekh leti hoon" if an answer takes a moment.
- **Can be interrupted:** talk over Alaap and it stops and listens (noise-aware, so background sound doesn't).
- **Speaks numbers like people do:** "saade chhe baje", "do sau rupaye", order numbers digit by digit.
- **Has a name and remembers you:** "Sat Sri Akal Aman ji! Glow Salon se Riya bol rahi hoon…"; it knows past visits,
  upcoming bookings and the last order. It always says it's an AI assistant if asked.
- **Natural endings:** checks in if the line goes quiet, says goodbye and hangs up.
- Owners pick the assistant's name, voice (with previews) and speaking speed in Settings → Voice & assistant.

## Layout

```
backend/    FastAPI, SQLAlchemy (SQLite or Postgres), Redis (optional)
  alaap/engine.py       conversation engine (LLM tool loop)
  alaap/skills/         the skills above
  alaap/llm.py          any OpenAI-compatible LLM: Gemini (default, free), Groq, Ollama
  alaap/speech.py       Gnani Prisma STT + Timbre TTS
  alaap/channels/       WhatsApp Cloud API, live voice (Exotel Voicebot + browser calls)
  alaap/jobs.py         outbox sender, reminders, follow-ups, daily voice summary
  alaap/static/         embeddable web widget (chat, voice messages, live call)
dashboard/  Next.js owner dashboard
```

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env      # add GEMINI_API_KEY and GNANI_API_KEY
cd backend && ../.venv/bin/python -m alaap.seed --demo-data && ../.venv/bin/uvicorn alaap.api.main:app --port 8000
```

In a second terminal:

```bash
cd dashboard && npm install && npm run dev
```

- Landing page and sign-up: http://localhost:3000/welcome
- Owner dashboard: http://localhost:3000 — demo logins `owner@glow.demo`, `owner@kirana.demo`,
  `owner@coaching.demo`, password `demo1234` (development only)
- A shop's customer page: http://localhost:8000/c/glow-salon
- Tests: `cd backend && ../.venv/bin/python -m pytest`

## Production

**[DEPLOY.md](DEPLOY.md)** takes you from an empty server to live in about 20 minutes. It's one
`docker compose up -d --build`, with automatic HTTPS, Postgres, Redis, a jobs worker and daily backups.
Moving from free to paid AI is only a change of keys in `.env`.

Built for production:
- **Startup checks:** in production mode the server won't start with a weak secret, SQLite, a non-HTTPS URL,
  or unverifiable webhooks. It also lists which integrations are off.
- **Abuse limits:** per-IP limits on chat, calls and logins; message and audio size limits; calls are capped in length.
- **Billing:** a free trial, plan payments by Razorpay UPI link, renewal reminders on WhatsApp, and optional
  enforcement when a plan lapses.
- **WhatsApp:** messages sent outside the 24-hour window go through an approved template automatically.
- **Privacy:** callers hear a recording notice, old transcripts are deleted automatically, and owners can
  delete all their transcripts.
- **Operations:** an admin CLI (`python -m alaap.admin`), a database-checking `/health` endpoint, jobs locked
  to one worker, and CI on GitHub Actions.

## Keys and accounts

| What | Needed for | Without it |
|---|---|---|
| `GEMINI_API_KEY` (free, aistudio.google.com) | conversations | chat replies with a "not connected" notice |
| `GNANI_API_KEY` | voice messages, live calls, voice notes, daily voice summary | text only; widget falls back to the browser's speech |
| WhatsApp Cloud API token + phone number ID | WhatsApp channel and sending messages | messages stay in the dashboard outbox as "logged" |
| Exotel account (Voicebot applet → `wss://HOST/ws/exotel?biz=SLUG`) | phone calls | use the widget's Call button |
| Razorpay keys | real UPI links | links open a test payment page |

WhatsApp messages sent more than 24 hours after the customer's last message (reminders, follow-ups)
need approved templates in Meta's console. Webhooks and Exotel need a public HTTPS URL (e.g. a tunnel)
set as `PUBLIC_URL`.

All prices, plan limits and demo businesses are placeholders to test with pilots.
`legacy/` holds the first Gradio prototype.
