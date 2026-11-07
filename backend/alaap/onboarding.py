"""Plug-and-play setup: starter templates per kind of business, and AI import of a business's
details from pasted text, a website, or a photo of a rate card / menu / price list."""

import base64
import json
import logging
import re
from html.parser import HTMLParser

import httpx
from sqlalchemy import select

from . import config, models
from .llm import LLM

log = logging.getLogger("alaap.onboarding")

# Sensible starting points so a new business can take calls immediately. Owners edit them later.
TEMPLATES: dict[str, dict] = {
    "salon": {
        "hours": [(d, "10:00", "20:00") for d in range(1, 7)],
        "services": [("Haircut (men)", 30, 200), ("Haircut (women)", 45, 400), ("Beard trim", 15, 100),
                     ("Hair colour", 90, 1200), ("Facial", 60, 800), ("Threading", 15, 50), ("Head massage", 30, 250)],
        "staff": [("Stylist 1", None)],
        "faqs": [("Payment", "UPI, cash and cards accepted."), ("Walk-ins", "Walk-ins welcome when a stylist is free.")],
    },
    "clinic": {
        "hours": [(d, "10:00", "14:00") for d in range(0, 6)],
        "services": [("Consultation", 15, 500), ("Follow-up visit", 10, 300)],
        "staff": [("Doctor", None)],
        "faqs": [("What to bring", "Please bring previous prescriptions and reports."),
                 ("Emergencies", "For emergencies please go to the nearest hospital.")],
    },
    "kirana": {
        "hours": [(d, "08:00", "21:00") for d in range(0, 7)],
        "products": [("Atta", "atta, aata, flour", "5 kg", 285), ("Rice", "chawal", "1 kg", 80),
                     ("Sugar", "cheeni, chini", "1 kg", 46), ("Cooking oil", "tel, oil", "1 L", 155),
                     ("Milk", "doodh", "500 ml", 28), ("Salt", "namak", "1 kg", 28)],
        "slots": [("10:00", "12:00"), ("17:00", "19:00")],
        "faqs": [("Payment", "UPI link on WhatsApp or cash on delivery.")],
    },
    "restaurant": {
        "hours": [(d, "12:00", "23:00") for d in range(0, 7)],
        "products": [("Veg thali", "thali", "1 plate", 180), ("Paneer butter masala", "paneer", "1 plate", 240),
                     ("Dal makhani", "dal", "1 plate", 200), ("Butter naan", "naan", "1 pc", 50)],
        "slots": [("12:30", "14:30"), ("19:00", "21:00"), ("21:00", "23:00")],
        "faqs": [("Delivery time", "Usually 30 to 45 minutes after the slot starts.")],
    },
    "pharmacy": {
        "hours": [(d, "09:00", "22:00") for d in range(0, 7)],
        "products": [("Paracetamol 500mg", "crocin, dolo, paracetamol", "strip of 10", 30)],
        "slots": [("10:00", "13:00"), ("17:00", "21:00")],
        "faqs": [("Prescriptions", "Prescription medicines need a photo of the prescription on WhatsApp.")],
    },
    "coaching": {
        "hours": [(d, "09:00", "19:00") for d in range(0, 6)],
        "services": [("Free counselling session", 30, 0), ("Free demo class", 60, 0)],
        "staff": [("Counsellor", None)],
        "faqs": [("Batches", "Morning and evening batches, Monday to Saturday.")],
    },
    "real_estate": {
        "hours": [(d, "10:00", "19:00") for d in range(0, 7)],
        "services": [("Site visit", 60, 0), ("Office meeting", 30, 0)],
        "staff": [("Sales advisor", None)],
        "faqs": [],
    },
    "gym": {
        "hours": [(d, "06:00", "22:00") for d in range(0, 7)],
        "services": [("Free trial session", 60, 0), ("Personal training session", 60, 500)],
        "staff": [("Trainer", None)],
        "faqs": [("Membership", "Monthly, quarterly and yearly memberships available.")],
    },
    "home_services": {
        "hours": [(d, "09:00", "19:00") for d in range(0, 7)],
        "services": [("AC service", 60, 500), ("AC repair visit", 60, 300), ("Plumbing visit", 60, 250)],
        "staff": [("Technician", None)],
        "faqs": [("Visit charge", "The visit charge is adjusted in the final bill if work is done.")],
    },
}


def apply_template(biz: models.Business) -> None:
    """Fill a brand-new business with its kind's starter data (marked as samples to edit)."""
    t = TEMPLATES.get(biz.kind, TEMPLATES["salon"])
    biz.hours = [models.BusinessHours(weekday=d, opens=o, closes=c) for d, o, c in t.get("hours", [])]
    services = [models.Service(name=n, duration_min=m, price_inr=p, notes="Sample - edit me", active=True)
                for n, m, p in t.get("services", [])]
    biz.services = services
    biz.staff = [models.Staff(name=n, services=list(services), active=True) for n, _ in t.get("staff", [])]
    biz.products = [models.Product(name=n, aliases=a, unit=u, price_inr=p, active=True)
                    for n, a, u, p in t.get("products", [])]
    biz.slots = [models.DeliverySlot(start=s, end=e) for s, e in t.get("slots", [])]
    biz.faqs = [models.Faq(question=q, answer=a) for q, a in t.get("faqs", [])]


# ---------- AI import ----------

EXTRACT_PROMPT = """You read a small Indian business's own material (rate card, menu, price list, website text, \
notes) and turn it into data for its AI receptionist. The business is a {kind}.
Return ONLY a JSON object with these keys (use [] or null when the material doesn't say; never invent prices):
{{
  "about": "one or two sentences about the business, or null",
  "address": "street address if given, or null",
  "phone": "public phone if given, or null",
  "hours": [{{"weekday": 0-6 (0=Monday), "opens": "HH:MM", "closes": "HH:MM"}}],
  "services": [{{"name": "...", "price_inr": integer, "duration_min": integer (guess a typical duration if not given)}}],
  "products": [{{"name": "...", "price_inr": integer, "unit": "e.g. 1 kg / 1 plate / 1 pc", "aliases": "other names \
customers say, Hindi/English, comma separated"}}],
  "staff": [{{"name": "...", "services": ["service names they do"]}}],
  "faqs": [{{"question": "short topic", "answer": "the fact"}}]
}}
Rules: services are things customers book time for (haircut, consultation, class); products are things they order \
(groceries, dishes, medicines). Prices in rupees as integers (take the lower one if a range). Keep names short and \
as the business writes them. If a menu has many items, include them all."""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def fetch_website(url: str) -> str:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    r = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "AlaapSetup/1.0"})
    r.raise_for_status()
    p = _Text()
    p.feed(r.text)
    return "\n".join(p.parts)[:20000]


def _parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("The AI did not return data. Try a clearer photo or paste the text.")
    return json.loads(m.group(0))


def extract(kind: str, text: str | None = None, image: bytes | None = None, image_type: str = "image/jpeg",
            llm: LLM | None = None) -> dict:
    """Ask the LLM to turn the material into profile data. Nothing is saved here."""
    llm = llm or LLM()
    content: list[dict] = [{"type": "text", "text": "Material:\n" + (text or "(see the image)")}]
    if image:
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:{image_type};base64,{base64.b64encode(image).decode()}"}})
    msg = llm.chat([{"role": "system", "content": EXTRACT_PROMPT.format(kind=kind.replace("_", " "))},
                    {"role": "user", "content": content}])
    data = _parse_json(msg.get("content") or "")
    return clean(data)


def _int(v, default=0):
    try:
        return int(round(float(re.sub(r"[^\d.]", "", str(v)) or default)))
    except ValueError:
        return default


def clean(data: dict) -> dict:
    """Normalise what the model returned so the review screen and apply() can trust it."""
    hhmm = re.compile(r"^\d{1,2}:\d{2}$")
    out = {"about": data.get("about") or None, "address": data.get("address") or None,
           "phone": data.get("phone") or None, "hours": [], "services": [], "products": [], "staff": [], "faqs": []}
    for h in data.get("hours") or []:
        try:
            d = int(h.get("weekday"))
            o, c = str(h.get("opens", "")), str(h.get("closes", ""))
            if 0 <= d <= 6 and hhmm.match(o) and hhmm.match(c):
                out["hours"].append({"weekday": d, "opens": o.zfill(5), "closes": c.zfill(5)})
        except (TypeError, ValueError):
            continue
    on_request = []  # no price given ("bridal makeup on call"): never let the assistant quote Rs 0
    for s in data.get("services") or []:
        if s.get("name"):
            row = {"name": str(s["name"])[:200], "price_inr": _int(s.get("price_inr")),
                   "duration_min": max(5, min(480, _int(s.get("duration_min"), 30)))}
            (out["services"] if row["price_inr"] > 0 else on_request).append(row)
    for p in data.get("products") or []:
        if p.get("name"):
            row = {"name": str(p["name"])[:200], "price_inr": _int(p.get("price_inr")),
                   "unit": str(p.get("unit") or "1 pc")[:50], "aliases": p.get("aliases") or None}
            (out["products"] if row["price_inr"] > 0 else on_request).append(row)
    for st in data.get("staff") or []:
        if st.get("name"):
            out["staff"].append({"name": str(st["name"])[:100], "services": [str(x) for x in st.get("services") or []]})
    for f in data.get("faqs") or []:
        if f.get("question") and f.get("answer"):
            out["faqs"].append({"question": str(f["question"])[:200], "answer": str(f["answer"])[:1000]})
    for row in on_request:
        out["faqs"].append({"question": f"{row['name']} price",
                            "answer": f"{row['name']}: price on request. Don't quote a price; offer a callback "
                                      "from the owner (take the customer's name and number)."})
    return out


def apply(s, biz: models.Business, data: dict, replace_samples: bool = True) -> dict:
    """Merge reviewed import data into the business. Items with the same name are updated."""
    data = clean(data)
    counts = {"services": 0, "products": 0, "staff": 0, "faqs": 0, "hours": 0}
    for k in ("about", "address", "phone"):
        if data.get(k):
            setattr(biz, k, data[k])
    if data["hours"]:
        biz.hours = [models.BusinessHours(weekday=h["weekday"], opens=h["opens"], closes=h["closes"])
                     for h in {h["weekday"]: h for h in data["hours"]}.values()]
        counts["hours"] = len(biz.hours)
    if replace_samples and (data["services"] or data["products"]):
        for sv in biz.services:
            if sv.notes == "Sample - edit me":
                sv.active = False
        for st in biz.staff:
            if st.name in ("Stylist 1", "Doctor", "Counsellor", "Sales advisor", "Trainer", "Technician"):
                st.active = False
    by_name = {sv.name.lower(): sv for sv in biz.services}
    for item in data["services"]:
        sv = by_name.get(item["name"].lower())
        if sv:
            sv.price_inr, sv.duration_min, sv.active, sv.notes = item["price_inr"], item["duration_min"], True, None
        else:
            sv = models.Service(name=item["name"], price_inr=item["price_inr"], duration_min=item["duration_min"],
                                active=True)
            biz.services.append(sv)
            by_name[sv.name.lower()] = sv
        counts["services"] += 1
    if replace_samples and data["products"]:
        sample_names = {n.lower() for n, *_ in TEMPLATES.get(biz.kind, {}).get("products", [])}
        for p in biz.products:
            if p.name.lower() in sample_names:
                p.active = False
    prods = {p.name.lower(): p for p in biz.products}
    for item in data["products"]:
        p = prods.get(item["name"].lower())
        if p:
            p.price_inr, p.unit, p.active = item["price_inr"], item["unit"], True
            p.aliases = item["aliases"] or p.aliases
        else:
            biz.products.append(models.Product(name=item["name"], price_inr=item["price_inr"], unit=item["unit"],
                                               aliases=item["aliases"], active=True))
        counts["products"] += 1
    active_services = [sv for sv in biz.services if sv.active]
    staff_by_name = {st.name.lower(): st for st in biz.staff}
    for item in data["staff"]:
        does = [by_name[n.lower()] for n in item["services"] if n.lower() in by_name] or active_services
        st = staff_by_name.get(item["name"].lower())
        if st:
            st.services, st.active = does, True
        else:
            biz.staff.append(models.Staff(name=item["name"], services=does, active=True))
        counts["staff"] += 1
    if not any(st.active for st in biz.staff) and active_services:
        biz.staff.append(models.Staff(name=biz.owner_name or "Owner", services=active_services, active=True))
    if replace_samples and data["faqs"]:
        samples = {(q, a) for q, a in TEMPLATES.get(biz.kind, {}).get("faqs", [])}
        biz.faqs = [f for f in biz.faqs if (f.question, f.answer) not in samples]  # don't contradict the import
    faq_by_q = {f.question.lower(): f for f in biz.faqs}
    for item in data["faqs"]:
        f = faq_by_q.get(item["question"].lower())
        if f:
            f.answer = item["answer"]
        else:
            biz.faqs.append(models.Faq(question=item["question"], answer=item["answer"]))
        counts["faqs"] += 1
    s.flush()
    return counts


def checklist(s, biz: models.Business) -> list[dict]:
    """What's left before this business is fully plug-and-play."""
    has_samples = any(sv.notes == "Sample - edit me" and sv.active for sv in biz.services)
    sold = [sv for sv in biz.services if sv.active] or [p for p in biz.products if p.active]
    test_calls = s.scalar(select(models.Conversation.id).where(
        models.Conversation.business_id == biz.id, models.Conversation.is_owner.is_(False)).limit(1))
    return [
        {"key": "profile", "label": "Add your prices and hours", "done": bool(sold) and not has_samples,
         "hint": "Upload a photo of your rate card, paste your price list, or edit in Settings."},
        {"key": "voice", "label": "Choose your assistant's name and voice", "done": bool(biz.voice),
         "hint": "Settings → Voice & assistant."},
        {"key": "test", "label": "Talk to your assistant once", "done": bool(test_calls),
         "hint": "Open your customer page and press Call."},
        {"key": "share", "label": "Put your QR poster on the counter", "done": bool(biz.shared_at),
         "hint": "Share kit → print the poster."},
        {"key": "whatsapp", "label": "Connect WhatsApp (optional)", "done": bool(biz.whatsapp_phone_number_id or (
            biz.managed and biz.code and config.WHATSAPP_SHARED_NUMBER_ID)),
         "hint": "Settings → Channels."},
        {"key": "phone", "label": "Forward missed calls to Alaap (optional)", "done": bool(biz.exotel_number),
         "hint": "Share kit → call forwarding."},
    ]
