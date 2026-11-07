# Deploying Alaap to production

One server runs everything with Docker Compose: Caddy (automatic HTTPS), the API, a jobs worker,
the dashboard, Postgres, Redis and daily database backups.

## 1. Server and domains (15 minutes)

- A Linux VPS with **2 vCPU / 4 GB RAM** (DigitalOcean/Hetzner/AWS Lightsail Mumbai, about ₹1,500–2,500/month)
  is enough for the first few hundred businesses. Install Docker: `curl -fsSL https://get.docker.com | sh`.
- Point two DNS **A records** at the server's IP:
  - `app.yourdomain.in` → the owner dashboard and landing page
  - `api.yourdomain.in` → API, customer pages (`/c/<shop>`), the widget, webhooks and live calls
- Open ports 80 and 443 only.

## 2. Configure and start (5 minutes)

```bash
git clone <your repo> alaap && cd alaap
cp .env.production.example .env
nano .env        # domains, SECRET_KEY, POSTGRES_PASSWORD, GEMINI_API_KEY, GNANI_API_KEY
docker compose up -d --build
docker compose exec api python -m alaap.admin check     # must print no FATAL lines
```

Open `https://app.yourdomain.in` — the landing page. HTTPS certificates are issued automatically on first visit.

Optional: show the live demos on the landing page
(`docker compose exec api python -m alaap.admin seed-demo`; demo owner logins get random passwords in production).

The API refuses to start in production if the secret is weak, the database isn't Postgres, `PUBLIC_URL` isn't
https, or webhooks can't be verified — `docker compose logs api` shows why.

## 3. Connect the channels

| Channel | Where | What to enter |
|---|---|---|
| **Razorpay** (customer UPI links + your plan payments) | Razorpay Dashboard → Settings → API keys, and Webhooks | Keys in `.env`; webhook URL `https://api.yourdomain.in/webhooks/razorpay`, event `payment_link.paid`, secret = `RAZORPAY_WEBHOOK_SECRET` |
| **WhatsApp** | Meta for Developers → your app → WhatsApp | `WHATSAPP_TOKEN` (permanent system-user token), `WHATSAPP_APP_SECRET`; webhook `https://api.yourdomain.in/webhooks/whatsapp`, verify token = `WHATSAPP_VERIFY_TOKEN`, subscribe to `messages`. Create a **Utility** template with body `Update from {{1}}: {{2}}` and set `WHATSAPP_TEMPLATE_NAME`. Each business enters its phone-number ID in Settings → Channels. |
| **Phone (Exotel)** | Exotel App Bazaar | Set `EXOTEL_WS_TOKEN` in `.env` (a long random string). Flow: **Voicebot** applet with URL `wss://api.yourdomain.in/ws/exotel?biz=<shop-slug>&token=<EXOTEL_WS_TOKEN>`, then a **Connect** applet to the owner's mobile (for handoffs). The business enters the Exotel number in Settings → Channels; the Share kit then shows its call-forwarding codes. |

After editing `.env`: `docker compose up -d` (only the changed services restart).

## 4. Going from free to paid

Nothing in the code changes. Edit `.env`, then `docker compose up -d`:

| From | To | Change |
|---|---|---|
| Gemini free tier | Gemini paid (higher limits, faster) | Same `GEMINI_API_KEY` after enabling billing in Google AI Studio; optionally pin `LLM_MODEL=gemini-3-flash-preview` and `LLM_REASONING=low` |
| Gnani hackathon credits | Gnani paid | New `GNANI_API_KEY` |
| Razorpay test mode | Live | Live `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / webhook secret |
| Groq or another OpenAI-compatible LLM | — | `LLM_PROVIDER`, its key (`GROQ_API_KEY` or `LLM_API_KEY` + `LLM_BASE_URL`), `LLM_MODEL` |

To charge businesses strictly, set `ENFORCE_BILLING=1` (lapsed businesses stop answering customers with a polite
notice and see a renew banner). Trial length is `TRIAL_DAYS`.

## 5. Operating it

```bash
docker compose ps                                    # everything healthy?
docker compose logs -f api worker                    # live logs
docker compose exec api python -m alaap.admin businesses
docker compose exec api python -m alaap.admin reset-password owner@shop.in
docker compose exec api python -m alaap.admin set-plan shop-slug pro 365   # e.g. founding-customer offer
git pull && docker compose up -d --build             # deploy an update (database columns are added automatically)
```

- **Backups:** `./backups/alaap-YYYYMMDD-HHMM.sql.gz`, daily, kept 14 days. Copy them off the server
  (e.g. `rclone` to Google Drive/S3). Restore: `gunzip -c FILE | docker compose exec -T postgres psql -U alaap alaap`.
- **Monitoring:** point an uptime checker (UptimeRobot, free) at `https://api.yourdomain.in/health`; it checks the database too.
- **Privacy:** callers hear that calls are recorded; transcripts older than `RETENTION_DAYS` are deleted daily;
  owners can delete all transcripts from Settings → Account & privacy. Get a legal review of your privacy policy
  (DPDP Act) before scaling.
- **Abuse limits:** per-IP limits on chat, calls and logins (`RATE_*` in `.env`), calls capped at `MAX_CALL_MINUTES`.

## Scaling later

- More traffic: raise `--workers` in `backend/Dockerfile`, or run more `api` containers behind Caddy (state is in
  Redis and Postgres; background jobs take a Postgres lock, so only one worker runs them).
- Managed Postgres/Redis: point `DATABASE_URL` / `REDIS_URL` at them and remove those services from the compose file.
