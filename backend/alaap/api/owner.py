"""Owner dashboard API (Bearer token from /api/auth/login)."""

import re
from datetime import datetime, timedelta

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from .. import auth, billing, config, db, jobs, managed, metrics, models, onboarding, ratelimit
from ..engine import get_engine
from ..scheduling import parse_date
from ..skills import DEFAULT_SKILLS, PLANS, REGISTRY
from ..skills import owner as owner_skill
from ..skills.base import Context, ToolError, normalise_phone
from ..timeutil import FMT, now
from .deps import Owner, current_owner

router = APIRouter(prefix="/api")


# ---------- auth / onboarding ----------

class Login(BaseModel):
    email: str
    password: str


class Signup(BaseModel):
    business_name: str
    kind: str
    city: str
    owner_name: str
    owner_phone: str
    email: str
    password: str


@router.post("/auth/login")
def login(body: Login, request: Request):
    ratelimit.limit(request, "login", config.RATE_LOGIN_PER_MIN)
    with db.session() as s:
        user = s.scalar(select(models.OwnerUser).where(models.OwnerUser.email == body.email.lower().strip()))
        if not user or not auth.verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Wrong email or password")
        return {"token": auth.make_token(user.id, user.business_id)}


@router.post("/auth/signup")
def signup(body: Signup, request: Request):
    ratelimit.limit(request, "signup", 5)
    if body.kind not in DEFAULT_SKILLS:
        raise HTTPException(400, f"kind must be one of {', '.join(DEFAULT_SKILLS)}")
    if len(body.password) < 8:
        raise HTTPException(400, "Password needs at least 8 characters")
    phone = normalise_phone(body.owner_phone)
    if not phone:
        raise HTTPException(400, "Owner phone must be a 10-digit mobile")
    slug = re.sub(r"[^a-z0-9]+", "-", body.business_name.lower()).strip("-")[:40] or "business"
    with db.session() as s:
        if s.scalar(select(models.OwnerUser.id).where(models.OwnerUser.email == body.email.lower().strip())):
            raise HTTPException(400, "That email already has an account")
        base, n = slug, 2
        while s.scalar(select(models.Business.id).where(models.Business.slug == slug)):
            slug, n = f"{base}-{n}", n + 1
        biz = models.Business(slug=slug, name=body.business_name.strip(), kind=body.kind, city=body.city.strip(),
                              timezone="Asia/Kolkata",
                              owner_name=body.owner_name.strip(), owner_phone=phone, skills=DEFAULT_SKILLS[body.kind],
                              plan="starter" if body.kind in ("salon", "clinic") else
                              ("pro" if body.kind in ("kirana", "restaurant", "pharmacy") else "business"))
        biz.code = managed.make_code(s, biz.name)  # reachable on Alaap's shared WhatsApp too
        onboarding.apply_template(biz)  # works from minute one; the owner replaces samples in the setup wizard
        biz.trial_ends_at = now(biz.timezone) + timedelta(days=config.TRIAL_DAYS)
        s.add(biz)
        s.flush()
        user = models.OwnerUser(business_id=biz.id, email=body.email.lower().strip(), name=body.owner_name,
                                password_hash=auth.hash_password(body.password))
        s.add(user)
        s.flush()
        return {"token": auth.make_token(user.id, biz.id), "slug": slug}


# ---------- reading ----------

def _biz(s, owner: Owner) -> models.Business:
    biz = s.get(models.Business, owner.business_id)
    if not biz:
        raise HTTPException(404)
    return biz


@router.get("/me")
def me(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        user = s.get(models.OwnerUser, owner.user_id) if owner.user_id else None
        return {"user": {"name": user.name, "email": user.email} if user else
                        {"name": "Alaap team", "email": None, "support": True},
                "business": {"id": biz.id, "slug": biz.slug, "name": biz.name, "kind": biz.kind, "plan": biz.plan,
                             "skills": biz.skill_list(), "managed": bool(biz.managed), "code": biz.code,
                             "stage": biz.stage or "live", "exotel_number": biz.exotel_number,
                             "whatsapp_link": managed.whatsapp_link(biz)},
                "plans": {k: {**v, "skills": sorted(v["skills"])} for k, v in PLANS.items()},
                "all_skills": {k: sk.name for k, sk in REGISTRY.items() if k != "owner"}}


@router.get("/overview")
def overview(days: int = 7, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        return metrics.overview(s, _biz(s, owner), max(1, min(days, 90)))


@router.get("/counts")
def counts(owner: Owner = Depends(current_owner)):
    """Small numbers for the menu badges (polled; kept cheap)."""
    with db.session() as s:
        biz = _biz(s, owner)
        items = onboarding.checklist(s, biz)
        return {"open_tickets": s.scalar(select(func.count(models.Ticket.id)).where(
                    models.Ticket.business_id == biz.id, models.Ticket.status == "open")) or 0,
                "setup_left": sum(1 for i in items if not i["done"])}


def _dt(d):
    return d.strftime(FMT) if d else None


@router.get("/appointments")
def appointments(days_back: int = 1, days_ahead: int = 30, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        t = now(biz.timezone)
        rows = s.scalars(select(models.Appointment).where(
            models.Appointment.business_id == biz.id,
            models.Appointment.start_at >= t - timedelta(days=days_back),
            models.Appointment.start_at <= t + timedelta(days=days_ahead)).order_by(models.Appointment.start_at))
        return [{"id": a.id, "ref": a.ref, "start": _dt(a.start_at), "end": _dt(a.end_at), "service": a.service.name,
                 "staff": a.staff.name, "customer": a.customer.name, "phone": a.customer.phone, "status": a.status,
                 "channel": a.channel, "conversation_id": a.conversation_id} for a in rows]


class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


@router.patch("/appointments/{appt_id}")
def update_appointment(appt_id: int, body: StatusUpdate, owner: Owner = Depends(current_owner)):
    if body.status not in ("booked", "cancelled", "done", "no_show"):
        raise HTTPException(400, "Bad status")
    with db.session() as s:
        a = s.get(models.Appointment, appt_id)
        if not a or a.business_id != owner.business_id:
            raise HTTPException(404)
        a.status = body.status
        return {"ok": True}


@router.get("/orders")
def orders(limit: int = 100, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        rows = s.scalars(select(models.Order).where(models.Order.business_id == owner.business_id)
                         .order_by(models.Order.id.desc()).limit(limit))
        return [{"id": o.id, "ref": o.ref, "created": _dt(o.created_at), "customer": o.customer.name,
                 "phone": o.customer.phone, "address": o.address, "landmark": o.landmark, "pincode": o.pincode,
                 "slot": f"{o.slot_date.isoformat()} {o.slot_label}", "total_inr": o.total_inr,
                 "payment_method": o.payment_method, "payment_status": o.payment_status, "status": o.status,
                 "payment_link": o.payment_link_url, "conversation_id": o.conversation_id,
                 "items": [{"name": i.name, "qty": i.qty, "line_total_inr": i.line_total_inr} for i in o.items]}
                for o in rows]


@router.patch("/orders/{order_id}")
def update_order(order_id: int, body: StatusUpdate, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        o = s.get(models.Order, order_id)
        if not o or o.business_id != owner.business_id:
            raise HTTPException(404)
        ctx = Context(business_id=owner.business_id, conversation_id=0, is_owner=True,
                      tz=s.get(models.Business, owner.business_id).timezone)
        try:
            return owner_skill.update_order_status(ctx, s, o.ref, body.status, body.note)
        except ToolError as e:
            raise HTTPException(400, str(e))


@router.get("/leads")
def leads(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        rows = s.scalars(select(models.Lead).where(models.Lead.business_id == owner.business_id)
                         .order_by(models.Lead.id.desc()).limit(200))
        return [{"id": l.id, "created": _dt(l.created_at), "name": l.name, "phone": l.phone, "need": l.need,
                 "budget": l.budget, "location": l.location, "preferred_time": l.preferred_time, "score": l.score,
                 "status": l.status, "notes": l.notes, "conversation_id": l.conversation_id} for l in rows]


@router.patch("/leads/{lead_id}")
def update_lead(lead_id: int, body: StatusUpdate, owner: Owner = Depends(current_owner)):
    if body.status not in ("new", "contacted", "visit_booked", "won", "lost"):
        raise HTTPException(400, "Bad status")
    with db.session() as s:
        l = s.get(models.Lead, lead_id)
        if not l or l.business_id != owner.business_id:
            raise HTTPException(404)
        l.status = body.status
        if body.note is not None:
            l.notes = body.note
        return {"ok": True}


@router.get("/tickets")
def tickets(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        rows = s.scalars(select(models.Ticket).where(models.Ticket.business_id == owner.business_id)
                         .order_by(models.Ticket.status.desc(), models.Ticket.id.desc()).limit(200))
        return [{"id": t.id, "created": _dt(t.created_at), "kind": t.kind, "name": t.name, "phone": t.phone,
                 "issue": t.issue, "urgency": t.urgency, "status": t.status, "conversation_id": t.conversation_id}
                for t in rows]


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: StatusUpdate, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        t = s.get(models.Ticket, ticket_id)
        if not t or t.business_id != owner.business_id:
            raise HTTPException(404)
        t.status = "closed" if body.status == "closed" else "open"
        return {"ok": True}


@router.get("/conversations")
def conversations(limit: int = 50, owner: Owner = Depends(current_owner)):
    C, M = models.Conversation, models.Message
    with db.session() as s:
        said = (select(M.conversation_id, func.count(M.id).label("turns"), func.min(M.id).label("first_id"))
                .where(M.role == "customer", M.conversation_id.in_(
                    select(C.id).where(C.business_id == owner.business_id)))
                .group_by(M.conversation_id).subquery())
        rows = s.execute(select(C, said.c.turns, M.text).join(said, said.c.conversation_id == C.id)
                         .join(M, M.id == said.c.first_id).where(C.business_id == owner.business_id)
                         .order_by(C.id.desc()).limit(max(1, min(limit, 200)))).all()
        return [{"id": c.id, "started": _dt(c.started_at), "channel": c.channel, "caller": c.caller_phone,
                 "outcome": c.outcome, "handoff": c.handoff, "turns": turns, "first": first[:120]}
                for c, turns, first in rows]


@router.get("/conversations/{cid}")
def conversation(cid: int, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        c = s.get(models.Conversation, cid)
        if not c or c.business_id != owner.business_id:
            raise HTTPException(404)
        return {"id": c.id, "channel": c.channel, "caller": c.caller_phone, "outcome": c.outcome,
                "handoff": c.handoff, "started": _dt(c.started_at), "call_seconds": c.call_seconds,
                "messages": [{"role": m.role, "text": m.text, "at": _dt(m.created_at), "latency_ms": m.latency_ms}
                             for m in c.messages]}


@router.get("/outbox")
def outbox(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        rows = s.scalars(select(models.Outbox).where(models.Outbox.business_id == owner.business_id)
                         .order_by(models.Outbox.id.desc()).limit(100))
        return [{"id": o.id, "send_after": _dt(o.send_after), "to": o.to_phone, "kind": o.kind, "channel": o.channel,
                 "body": o.body, "status": o.status, "error": o.error, "has_audio": bool(o.media_path)} for o in rows]


@router.post("/jobs/daily-summary")
def send_summary_now(owner: Owner = Depends(current_owner)):
    jobs.daily_summaries(force=True)
    return {"ok": True}


# ---------- owner chat ("aaj kitne orders aaye?") ----------

class OwnerChat(BaseModel):
    text: str


@router.post("/owner-chat/start")
def owner_chat_start(owner: Owner = Depends(current_owner)):
    r = get_engine().start(owner.business_id, "web", None, owner=True)
    return {"conversation_id": r.conversation_id, "text": r.text}


@router.post("/owner-chat/{cid}")
def owner_chat(cid: int, body: OwnerChat, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        c = s.get(models.Conversation, cid)
        if not c or c.business_id != owner.business_id or not c.is_owner:
            raise HTTPException(404)
    return {"text": get_engine().reply(cid, body.text).text}


# ---------- settings ----------

def _settings(biz: models.Business) -> dict:
    return {
        "business": {k: getattr(biz, k) for k in (
            "name", "kind", "phone", "owner_name", "owner_phone", "owner_language", "address", "city", "languages",
            "about", "skills", "plan", "voice", "whatsapp_phone_number_id", "exotel_number", "slug",
            "assistant_name", "speech_speed")},
        "hours": [{"weekday": h.weekday, "opens": h.opens, "closes": h.closes} for h in biz.hours],
        "closures": [{"id": c.id, "day": c.day.isoformat(), "note": c.note} for c in biz.closures],
        "services": [{"id": x.id, "name": x.name, "duration_min": x.duration_min, "price_inr": x.price_inr,
                      "notes": x.notes, "active": x.active} for x in biz.services],
        "staff": [{"id": p.id, "name": p.name, "active": p.active, "service_ids": [x.id for x in p.services]}
                  for p in biz.staff],
        "products": [{"id": p.id, "name": p.name, "aliases": p.aliases, "unit": p.unit, "price_inr": p.price_inr,
                      "stock": p.stock, "reorder_days": p.reorder_days, "active": p.active} for p in biz.products],
        "areas": [{"id": a.id, "pincode": a.pincode, "delivery_fee_inr": a.delivery_fee_inr,
                   "min_order_inr": a.min_order_inr} for a in biz.areas],
        "slots": [{"id": x.id, "start": x.start, "end": x.end} for x in biz.slots],
        "faqs": [{"id": f.id, "question": f.question, "answer": f.answer} for f in biz.faqs],
    }


@router.get("/settings")
def get_settings(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        return _settings(_biz(s, owner))


EDITABLE = {"name", "phone", "owner_name", "owner_phone", "owner_language", "address", "city", "languages", "about",
            "skills", "voice", "whatsapp_phone_number_id", "exotel_number", "assistant_name", "speech_speed"}
SECTIONS = {
    "services": (models.Service, ["name", "duration_min", "price_inr", "notes", "active"], "soft"),
    "products": (models.Product, ["name", "aliases", "unit", "price_inr", "stock", "reorder_days", "active"], "soft"),
    "areas": (models.ServiceArea, ["pincode", "delivery_fee_inr", "min_order_inr"], "hard"),
    "slots": (models.DeliverySlot, ["start", "end"], "hard"),
    "faqs": (models.Faq, ["question", "answer"], "hard"),
    "staff": (models.Staff, ["name", "active"], "soft"),
}


@router.put("/settings/business")
def put_business(body: dict, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        for k, v in body.items():
            if k not in EDITABLE:
                continue
            if k == "owner_phone":
                v = normalise_phone(v)
            if k == "speech_speed":
                v = min(1.15, max(0.85, float(v or 1.0)))
            if k == "assistant_name" and v:
                v = str(v).strip()[:40]
                v = v[:1].upper() + v[1:]  # "riya" -> "Riya": it's spoken and shown to customers
            if k == "skills":
                v = ",".join(x for x in (v if isinstance(v, list) else str(v).split(",")) if x in REGISTRY)
            setattr(biz, k, v or None if k not in ("name", "skills", "languages") else v)
        s.flush()
        return _settings(biz)


@router.put("/settings/hours")
def put_hours(body: list[dict], owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        for h in body:
            if not (re.fullmatch(r"\d\d:\d\d", h.get("opens", "")) and re.fullmatch(r"\d\d:\d\d", h.get("closes", ""))):
                raise HTTPException(400, "Times must be HH:MM")
        biz.hours = [models.BusinessHours(weekday=int(h["weekday"]), opens=h["opens"], closes=h["closes"])
                     for h in body if h.get("open", True)]
        s.flush()
        return _settings(biz)


@router.put("/settings/closures")
def put_closures(body: list[dict], owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        biz.closures = [models.Closure(day=parse_date(c["day"]), note=c.get("note")) for c in body]
        s.flush()
        return _settings(biz)


@router.put("/settings/{section}")
def put_section(section: str, body: list[dict], owner: Owner = Depends(current_owner)):
    """Upsert a list. Rows with an id are updated; new rows created; missing rows deactivated (or deleted)."""
    if section not in SECTIONS:
        raise HTTPException(404)
    model, fields, mode = SECTIONS[section]
    with db.session() as s:
        biz = _biz(s, owner)
        existing = {r.id: r for r in s.scalars(select(model).where(model.business_id == biz.id))}
        seen = set()
        for row in body:
            obj = existing.get(row.get("id")) if row.get("id") else None
            if obj is None:
                obj = model(business_id=biz.id)
                s.add(obj)
            for f in fields:
                if f in row:
                    setattr(obj, f, row[f] if row[f] != "" else None)
            if section == "staff" and "service_ids" in row:
                obj.services = [x for x in biz.services if x.id in set(row["service_ids"])]
            s.flush()
            seen.add(obj.id)
        for rid, obj in existing.items():
            if rid not in seen:
                if mode == "soft":
                    obj.active = False
                else:
                    s.delete(obj)
        s.flush()
        s.refresh(biz)
        return _settings(biz)


class VoicePreview(BaseModel):
    voice: str | None = None
    speed: float | None = None
    text: str | None = None


@router.post("/voice/preview")
def voice_preview(body: VoicePreview, owner: Owner = Depends(current_owner)):
    if not ratelimit.hit(f"preview:{owner.business_id}", 30):
        raise HTTPException(429, "Too many previews; wait a minute.")
    """Hear a voice before choosing it."""
    import base64

    from .. import speech
    from ..engine import FEMALE_VOICES
    from ..spoken import for_speech

    gn = speech.provider()
    if not gn:
        raise HTTPException(503, "Voice needs GNANI_API_KEY")
    with db.session() as s:
        biz = _biz(s, owner)
        name = biz.assistant_name or "Riya"
        bname = biz.name
    female = (body.voice or "Shivani") in FEMALE_VOICES
    text = body.text or (f"Namaste ji! {bname} se {name} {'bol rahi' if female else 'bol raha'} hoon. "
                         f"Kal shaam saade chhe baje ka slot khali hai, book kar doon?")
    wav = gn.synthesize(for_speech(text)[:300], sample_rate=24000, container="wav", voice=body.voice,
                        speed=min(1.15, max(0.85, body.speed or 1.0)))
    return {"audio": base64.b64encode(wav).decode()}


# ---------- plug-and-play setup ----------

class ImportText(BaseModel):
    text: str | None = None
    url: str | None = None


@router.post("/setup/import")
def setup_import(body: ImportText, owner: Owner = Depends(current_owner)):
    if not ratelimit.hit(f"import:{owner.business_id}", 20):
        raise HTTPException(429, "Too many imports; wait a minute.")
    """Read a price list / menu / website and return what Alaap understood (not saved yet)."""
    with db.session() as s:
        kind = _biz(s, owner).kind
    text = body.text or ""
    if body.url:
        try:
            text = onboarding.fetch_website(body.url) + "\n" + text
        except Exception as e:
            raise HTTPException(400, f"Couldn't open that website ({type(e).__name__}). Paste the text instead.")
    if not text.strip():
        raise HTTPException(400, "Paste some text, give a website, or upload a photo.")
    try:
        return onboarding.extract(kind, text=text)
    except Exception as e:
        raise HTTPException(502, f"Couldn't read it: {e}")


@router.post("/setup/import-photo")
async def setup_import_photo(photo: UploadFile = File(...), owner: Owner = Depends(current_owner)):
    if not ratelimit.hit(f"import:{owner.business_id}", 20):
        raise HTTPException(429, "Too many imports; wait a minute.")
    """Photo of a rate card, menu or price list -> services/products/hours (not saved yet)."""
    data = await photo.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Photo is too large (max 8 MB).")
    with db.session() as s:
        kind = _biz(s, owner).kind
    try:
        return await asyncio.to_thread(onboarding.extract, kind, None, data, photo.content_type or "image/jpeg")
    except Exception as e:
        raise HTTPException(502, f"Couldn't read the photo: {e}")


@router.post("/setup/apply")
def setup_apply(body: dict, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        counts = onboarding.apply(s, biz, body)
        s.refresh(biz)
        return {"saved": counts, "settings": _settings(biz)}


@router.get("/setup/status")
def setup_status(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        items = onboarding.checklist(s, biz)
        return {"items": items, "done": sum(i["done"] for i in items), "total": len(items),
                "slug": biz.slug, "kind": biz.kind}


@router.post("/setup/shared")
def setup_shared(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        biz.shared_at = biz.shared_at or now(biz.timezone)
    return {"ok": True}


# ---------- billing ----------

@router.get("/billing")
def get_billing(owner: Owner = Depends(current_owner)):
    with db.session() as s:
        biz = _biz(s, owner)
        payments = s.scalars(select(models.PlanPayment).where(models.PlanPayment.business_id == biz.id)
                             .order_by(models.PlanPayment.id.desc()).limit(12))
        return {"status": billing.status(biz), "enforced": config.ENFORCE_BILLING,
                "plans": {k: {"price_inr": v["price_inr"], "minutes": v["minutes"],
                              "skills": [REGISTRY[x].name for x in sorted(v["skills"]) if x in REGISTRY]}
                          for k, v in PLANS.items()},
                "payments": [{"plan": p.plan, "months": p.months, "amount_inr": p.amount_inr, "status": p.status,
                              "created": _dt(p.created_at), "url": p.link_url if p.status != "paid" else None}
                             for p in payments]}


class Checkout(BaseModel):
    plan: str
    months: int = 1


@router.post("/billing/checkout")
def billing_checkout(body: Checkout, owner: Owner = Depends(current_owner)):
    with db.session() as s:
        try:
            pay = billing.checkout(s, _biz(s, owner), body.plan, body.months)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"Payment provider error: {type(e).__name__}")
        return {"url": pay.link_url, "amount_inr": pay.amount_inr}


# ---------- privacy ----------

@router.delete("/data/conversations")
def delete_conversations(owner: Owner = Depends(current_owner)):
    """Delete every transcript for this business (bookings and orders stay)."""
    with db.session() as s:
        ids = list(s.scalars(select(models.Conversation.id).where(models.Conversation.business_id == owner.business_id)))
        if ids:
            s.execute(models.Message.__table__.delete().where(models.Message.conversation_id.in_(ids)))
            s.execute(models.Conversation.__table__.delete().where(models.Conversation.id.in_(ids)))
        return {"deleted": len(ids)}


class PasswordChange(BaseModel):
    current: str
    new: str


@router.put("/me/password")
def change_password(body: PasswordChange, request: Request, owner: Owner = Depends(current_owner)):
    ratelimit.limit(request, "password", config.RATE_LOGIN_PER_MIN)
    if len(body.new) < 8:
        raise HTTPException(400, "New password needs at least 8 characters")
    with db.session() as s:
        user = s.get(models.OwnerUser, owner.user_id) if owner.user_id else None
        if not user:
            raise HTTPException(400, "Only the shop owner can change their password.")
        if not auth.verify_password(body.current, user.password_hash):
            raise HTTPException(400, "Current password is wrong")
        user.password_hash = auth.hash_password(body.new)
    return {"ok": True}
