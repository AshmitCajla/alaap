"""Managed mode: the Alaap team sets a shop up and lends it a phone number; the owner only sends their menu.

- Shops get a short code (GLOW) so customers can reach them on Alaap's shared WhatsApp number.
- Alaap rents numbers (Exotel ExoPhones) into a pool and assigns one per shop; one Exotel flow serves them all,
  because calls are routed by the number dialled.
- Usage and rough cost per shop, so plans can be priced above cost."""

import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auth, config, models, notify, onboarding
from .skills import DEFAULT_SKILLS
from .skills.base import ToolError, normalise_phone
from .timeutil import now

STAGES = ("setup", "review", "live")


def _slug(s: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "shop"
    slug, n = base, 2
    while s.scalar(select(models.Business.id).where(models.Business.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def make_code(s: Session, name: str) -> str:
    """A short, easy-to-type shop code from the name: 'Glow Unisex Salon' -> GLOW, then GLOW2, ..."""
    words = [w for w in re.findall(r"[A-Za-z]+", name.upper()) if w not in ("THE", "SHRI", "SRI", "NEW", "AND")]
    base = (words[0][:6] if words and len(words[0]) >= 3 else "".join(w[0] for w in words)[:6]) or "SHOP"
    code, n = base, 2
    while s.scalar(select(models.Business.id).where(func.upper(models.Business.code) == code)):
        code, n = f"{base}{n}", n + 1
    return code


def create_shop(s: Session, *, name: str, kind: str, city: str, owner_name: str, owner_phone: str,
                email: str | None = None, address: str | None = None) -> tuple[models.Business, str | None]:
    """A managed shop in the 'setup' stage, filled with its kind's starter data. Returns (shop, owner password)."""
    if kind not in DEFAULT_SKILLS:
        raise ToolError(f"kind must be one of {', '.join(DEFAULT_SKILLS)}")
    phone = normalise_phone(owner_phone)
    if not phone:
        raise ToolError("Owner phone must be a 10-digit mobile.")
    if s.scalar(select(models.Business.id).where(models.Business.owner_phone == phone,
                                                 models.Business.managed.is_(True))):
        raise ToolError("A managed shop with this owner mobile already exists.")
    biz = models.Business(slug=_slug(s, name), name=name.strip(), kind=kind, city=(city or "").strip(),
                          address=address, timezone="Asia/Kolkata", owner_name=owner_name.strip(), owner_phone=phone,
                          skills=DEFAULT_SKILLS[kind], managed=True, stage="setup", code=make_code(s, name),
                          plan="starter" if kind in ("salon", "clinic") else
                          ("pro" if kind in ("kirana", "restaurant", "pharmacy") else "business"))
    onboarding.apply_template(biz)
    biz.trial_ends_at = now(biz.timezone) + timedelta(days=config.TRIAL_DAYS)
    s.add(biz)
    s.flush()
    password = None
    if email:
        email = email.lower().strip()
        if s.scalar(select(models.OwnerUser.id).where(models.OwnerUser.email == email)):
            raise ToolError("That email already has a login.")
        password = secrets.token_urlsafe(9)
        s.add(models.OwnerUser(business_id=biz.id, email=email, name=owner_name,
                               password_hash=auth.hash_password(password)))
        s.flush()
    return biz, password


# ---------- numbers ----------

def add_numbers(s: Session, numbers: list[str], monthly_cost_inr: int = 0, notes: str | None = None) -> list[str]:
    added = []
    for raw in numbers:
        digits = re.sub(r"\D", "", raw or "")
        if len(digits) > 10 and digits.startswith(("91", "0")):
            digits = digits[-10:]
        if len(digits) < 10:
            continue
        if s.scalar(select(models.PhoneNumber.id).where(models.PhoneNumber.number == digits)):
            continue
        s.add(models.PhoneNumber(number=digits, monthly_cost_inr=monthly_cost_inr, notes=notes))
        added.append(digits)
    s.flush()
    return added


def assign_number(s: Session, biz: models.Business, number_id: int | None = None) -> models.PhoneNumber:
    """Give the shop a number from the pool (a specific one, or the oldest free one). Calls route by it at once."""
    if biz.exotel_number:
        current = s.scalar(select(models.PhoneNumber).where(models.PhoneNumber.number == biz.exotel_number))
        if current and (number_id is None or current.id == number_id):
            return current
        release_number(s, biz)
    q = select(models.PhoneNumber).where(models.PhoneNumber.business_id.is_(None))
    q = q.where(models.PhoneNumber.id == number_id) if number_id else q.order_by(models.PhoneNumber.id)
    num = s.scalar(q.limit(1).with_for_update())
    if not num:
        raise ToolError("No free number in the pool. Rent one from Exotel and add it under Numbers.")
    num.business_id, num.assigned_at = biz.id, now()
    biz.exotel_number = num.number
    s.flush()
    return num


def release_number(s: Session, biz: models.Business) -> None:
    for num in s.scalars(select(models.PhoneNumber).where(models.PhoneNumber.business_id == biz.id)):
        num.business_id, num.assigned_at = None, None
    biz.exotel_number = None
    s.flush()


# ---------- links and messages ----------

def whatsapp_link(biz: models.Business) -> str | None:
    """wa.me link customers use to reach this shop on Alaap's shared number (opens with the shop code typed)."""
    if biz.whatsapp_phone_number_id or not (config.WHATSAPP_SHARED_NUMBER and biz.code):
        return None
    return f"https://wa.me/{re.sub(r'[^0-9]', '', config.WHATSAPP_SHARED_NUMBER)}?text={quote(biz.code + ' Namaste')}"


def forwarding_codes(number: str | None) -> list[tuple[str, str]]:
    n = re.sub(r"\D", "", number or "")[-10:]
    if not n:
        return []
    return [("When you don't answer", f"**61*{n}#"), ("When you're busy", f"**67*{n}#"),
            ("When phone is off", f"**62*{n}#"), ("Turn forwarding off", "##002#")]


def welcome_text(biz: models.Business) -> str:
    name = biz.assistant_name or "Riya"
    lines = [f"Namaste {biz.owner_name or ''}! {biz.name} ka AI receptionist {name} ab live hai.".replace("  ", " ")]
    if biz.exotel_number:
        lines.append(f"Aapka Alaap number: {biz.exotel_number}. Customers is par call kar sakte hain.")
        lines.append("Jo calls aap utha nahi paate, unhe Alaap par bhejne ke liye apne phone se ek baar dial karein: "
                     + ", ".join(f"{code}" for _, code in forwarding_codes(biz.exotel_number)[:2]))
    link = whatsapp_link(biz)
    if link:
        lines.append(f"WhatsApp par customers yahan se baat karein: {link}")
    lines.append(f"Customer page: {config.PUBLIC_URL}/c/{biz.slug}")
    lines.append("Booking, order ya complaint aate hi aapko yahin WhatsApp aayega. Rate ya timing badalni ho to bas "
                 "yahan likh dijiye, jaise 'facial 900 kar do' ya 'kal shop band hai'.")
    return "\n".join(lines)


def go_live(s: Session, biz: models.Business) -> None:
    biz.stage, biz.active = "live", True
    notify.queue(s, biz, biz.owner_phone, "welcome", welcome_text(biz))


# ---------- usage ----------

def month_start(t: datetime | None = None) -> datetime:
    t = t or now()
    return t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage(s: Session, biz_ids: list[int] | None = None, since: datetime | None = None,
          until: datetime | None = None) -> dict[int, dict]:
    """Per shop in [since, until) (default: this month): call minutes, chats, messages sent, rough cost in rupees."""
    since = since or month_start()
    until = until or datetime(9999, 1, 1)
    C, O, M = models.Conversation, models.Outbox, models.Message
    out: dict[int, dict] = {}

    def row(bid):
        return out.setdefault(bid, {"calls": 0, "call_minutes": 0.0, "chats": 0, "customer_messages": 0,
                                    "messages_sent": 0, "cost_inr": 0.0})

    q = select(C.business_id, C.channel, func.count(C.id), func.coalesce(func.sum(C.call_seconds), 0)).where(
        C.started_at >= since, C.started_at < until, C.is_owner.is_(False))
    if biz_ids is not None:
        q = q.where(C.business_id.in_(biz_ids))
    for bid, channel, n, secs in s.execute(q.group_by(C.business_id, C.channel)):
        r = row(bid)
        if channel == "phone" or (channel == "web" and secs):
            r["calls"] += n
            r["call_minutes"] += round(secs / 60, 1)
        else:
            r["chats"] += n
    q = select(C.business_id, func.count(M.id)).join(M, M.conversation_id == C.id).where(
        C.started_at >= since, C.started_at < until, C.is_owner.is_(False), C.channel.in_(("whatsapp", "web")), M.role == "customer")
    if biz_ids is not None:
        q = q.where(C.business_id.in_(biz_ids))
    for bid, n in s.execute(q.group_by(C.business_id)):
        row(bid)["customer_messages"] = n
    q = select(O.business_id, func.count(O.id)).where(O.created_at >= since, O.created_at < until, O.status == "sent")
    if biz_ids is not None:
        q = q.where(O.business_id.in_(biz_ids))
    for bid, n in s.execute(q.group_by(O.business_id)):
        row(bid)["messages_sent"] = n
    rent = {}
    for bid, cost in s.execute(select(models.PhoneNumber.business_id, models.PhoneNumber.monthly_cost_inr).where(
            models.PhoneNumber.business_id.is_not(None))):
        rent[bid] = rent.get(bid, 0) + (cost or 0)
    for bid in set(out) | set(rent):
        r = row(bid)
        r["number_rent_inr"] = rent.get(bid, 0)
        r["cost_inr"] = round(r["call_minutes"] * config.COST_CALL_MIN_INR
                              + r["messages_sent"] * config.COST_WA_MSG_INR
                              + r["customer_messages"] * config.COST_CHAT_TURN_INR + rent.get(bid, 0), 2)
    return out
