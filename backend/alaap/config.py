"""All settings come from the environment (or backend/.env)."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


ROOT = Path(__file__).resolve().parent.parent

# "production" turns on strict checks (real secret, Postgres, signed webhooks, no mock payments).
ENV = env("ALAAP_ENV", "development")
PRODUCTION = ENV == "production"

# Storage. SQLite for local dev; set DATABASE_URL=postgresql+psycopg://... in production.
DATABASE_URL = env("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'alaap.db'}")
REDIS_URL = env("REDIS_URL")  # optional; conversation state falls back to memory
MEDIA_DIR = Path(env("ALAAP_MEDIA_DIR", str(ROOT / "data" / "media")))

# Public URL of this backend (for payment callbacks, widget, media links).
PUBLIC_URL = env("PUBLIC_URL", "http://localhost:8000").rstrip("/")
DASHBOARD_URL = env("DASHBOARD_URL", "http://localhost:3000").rstrip("/")
SECRET_KEY = env("SECRET_KEY", "dev-only-secret-change-me-before-going-live")

# LLM: any OpenAI-compatible API. gemini (default, free tier), groq (free tier) or ollama (local).
LLM_PROVIDER = env("LLM_PROVIDER", "gemini")
LLM_MODEL = env("LLM_MODEL")  # default depends on provider
LLM_BASE_URL = env("LLM_BASE_URL")
LLM_API_KEY = env("LLM_API_KEY")
LLM_REASONING = env("LLM_REASONING", "low")  # Gemini thinking: none | low | medium | high

# Gnani (speech). https://docs.gnani.ai
GNANI_API_KEY = env("GNANI_API_KEY")
GNANI_BASE_URL = env("GNANI_BASE_URL", "https://api.vachana.ai")
GNANI_STT_MODEL = env("GNANI_STT_MODEL", "prisma-v3.0")
GNANI_STT_LANGUAGE = env("GNANI_STT_LANGUAGE", "indic-auto")
GNANI_STT_FORMAT = env("GNANI_STT_FORMAT", "codemix")
GNANI_TTS_MODEL = env("GNANI_TTS_MODEL", "timbre-v3.0")
GNANI_TTS_VOICE = env("GNANI_TTS_VOICE", "Shivani")

# WhatsApp Cloud API. Without a token, messages stay in the outbox (shown on the dashboard).
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN")
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", "alaap-verify")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", "v21.0")
# Business-initiated messages (reminders, follow-ups) outside the 24-hour window must use an approved template.
# Create a "Utility" template with two body variables, e.g. "Update from {{1}}: {{2}}", and name it here.
WHATSAPP_TEMPLATE_NAME = env("WHATSAPP_TEMPLATE_NAME")
WHATSAPP_TEMPLATE_LANG = env("WHATSAPP_TEMPLATE_LANG", "en")
# Alaap's own WhatsApp number, shared by every managed shop that has no number of its own. Customers reach a
# shop through its code (the QR poster opens wa.me/<number>?text=<CODE>); owners send menus here to get set up.
WHATSAPP_SHARED_NUMBER_ID = env("WHATSAPP_SHARED_NUMBER_ID")  # Meta phone-number ID
WHATSAPP_SHARED_NUMBER = env("WHATSAPP_SHARED_NUMBER")        # the number itself, e.g. 919800000000

# Rough running costs per shop, for the operator console's usage page (edit to your real rates).
COST_CALL_MIN_INR = float(env("COST_CALL_MIN_INR", "1.5"))     # telephony + speech + LLM per call minute
COST_WA_MSG_INR = float(env("COST_WA_MSG_INR", "0.15"))        # per WhatsApp message sent (avg incl. templates)
COST_CHAT_TURN_INR = float(env("COST_CHAT_TURN_INR", "0.05"))  # LLM per customer message on web/WhatsApp

# Razorpay. Without keys, payment links point to a local mock page.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET")

# Exotel (phone). Inbound calls use the Voicebot applet pointed at /ws/exotel.
EXOTEL_SID = env("EXOTEL_SID")
EXOTEL_API_KEY = env("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = env("EXOTEL_API_TOKEN")
EXOTEL_SUBDOMAIN = env("EXOTEL_SUBDOMAIN", "api.exotel.com")
# Secret in the Voicebot URL (…/ws/exotel?biz=SLUG&token=THIS). Phone calls are refused without it.
EXOTEL_WS_TOKEN = env("EXOTEL_WS_TOKEN")

# Who may call the API from a browser. The widget/customer endpoints are public by design.
CORS_ORIGINS = [o.strip() for o in env("CORS_ORIGINS", "*").split(",") if o.strip()]

# Abuse limits (per IP, per minute). Each customer message costs LLM and speech credits.
RATE_CHAT_PER_MIN = int(env("RATE_CHAT_PER_MIN", "30"))
RATE_LOGIN_PER_MIN = int(env("RATE_LOGIN_PER_MIN", "10"))
RATE_CALLS_PER_MIN = int(env("RATE_CALLS_PER_MIN", "6"))
MAX_CALL_MINUTES = int(env("MAX_CALL_MINUTES", "15"))

# Billing: new businesses get a free trial; plans are paid through Razorpay payment links.
TRIAL_DAYS = int(env("TRIAL_DAYS", "14"))
# When true, a business whose trial/plan has lapsed stops answering customers (they get a polite notice).
ENFORCE_BILLING = env("ENFORCE_BILLING", "0") == "1"

# Privacy: conversations and transcripts older than this are deleted automatically (0 = keep forever).
RETENTION_DAYS = int(env("RETENTION_DAYS", "180"))

# Behaviour
REMINDER_HOURS = 2
MIN_LEAD_MINUTES = 15
SLOT_STEP_MINUTES = 15
DAILY_SUMMARY_HOUR = int(env("DAILY_SUMMARY_HOUR", "21"))
RUN_JOBS = env("ALAAP_RUN_JOBS", "1") == "1"  # background scheduler inside the API process


DEFAULT_SECRET = "dev-only-secret-change-me-before-going-live"


def check() -> list[str]:
    """Problems with this configuration. In production, the fatal ones stop the server from starting."""
    fatal, warn = [], []
    if PRODUCTION:
        if SECRET_KEY == DEFAULT_SECRET or len(SECRET_KEY) < 32:
            fatal.append("SECRET_KEY must be a random string of 32+ characters (python -c 'import secrets; "
                         "print(secrets.token_urlsafe(48))').")
        if DATABASE_URL.startswith("sqlite"):
            fatal.append("Use Postgres in production: set DATABASE_URL=postgresql+psycopg://user:pass@host/db.")
        if not PUBLIC_URL.startswith("https://"):
            fatal.append("PUBLIC_URL must be the public https:// address of the API (payments, WhatsApp, Exotel).")
        if WHATSAPP_TOKEN and not WHATSAPP_APP_SECRET:
            fatal.append("WHATSAPP_APP_SECRET is required with WHATSAPP_TOKEN so webhooks can be verified.")
        if RAZORPAY_KEY_ID and not RAZORPAY_WEBHOOK_SECRET:
            fatal.append("RAZORPAY_WEBHOOK_SECRET is required with Razorpay keys so payments can be verified.")
        if not REDIS_URL:
            warn.append("REDIS_URL not set: live conversations are kept in memory (fine for one server only).")
    from . import llm  # noqa: PLC0415

    if not llm.LLM().ready:
        warn.append(f"No LLM key for provider '{LLM_PROVIDER}': customers get a 'not connected' reply.")
    if not GNANI_API_KEY:
        warn.append("GNANI_API_KEY not set: voice (calls, voice notes) is off.")
    if not WHATSAPP_TOKEN:
        warn.append("WHATSAPP_TOKEN not set: WhatsApp messages stay in the dashboard outbox.")
    elif not WHATSAPP_TEMPLATE_NAME:
        warn.append("WHATSAPP_TEMPLATE_NAME not set: reminders outside the 24-hour window will fail.")
    if WHATSAPP_SHARED_NUMBER_ID and not WHATSAPP_SHARED_NUMBER:
        warn.append("WHATSAPP_SHARED_NUMBER not set: share kits can't show the shared WhatsApp link.")
    if not EXOTEL_WS_TOKEN:
        warn.append("EXOTEL_WS_TOKEN not set: phone calls via Exotel are refused until you set it.")
    if not RAZORPAY_KEY_ID:
        warn.append("Razorpay keys not set: UPI links use a test page" + (" (disabled in production)." if PRODUCTION else "."))
    return [f"FATAL: {m}" for m in fatal] + [f"warning: {m}" for m in warn]
