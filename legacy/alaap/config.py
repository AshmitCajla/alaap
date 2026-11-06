"""Settings read from the environment (or a local .env file)."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.getenv("ALAAP_DB", ROOT / "data" / "alaap.db"))
MODEL = os.getenv("ALAAP_MODEL", "claude-opus-5-5")
# Phone calls need short, fast turns, so default to low effort.
EFFORT = os.getenv("ALAAP_EFFORT", "low")
# Server-side refusal fallback (beta). Set ALAAP_FALLBACKS=0 to turn it off.
USE_FALLBACKS = os.getenv("ALAAP_FALLBACKS", "1") != "0"
TZ = ZoneInfo(os.getenv("ALAAP_TZ", "Asia/Kolkata"))

# Reminder goes out this many hours before an appointment.
REMINDER_HOURS = 2
# Earliest bookable slot is this many minutes from now.
MIN_LEAD_MINUTES = 15
SLOT_STEP_MINUTES = 15
