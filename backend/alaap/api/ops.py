"""Operator console API for the Alaap team (managed mode). Bearer token from /api/ops/auth/login."""

import asyncio
import base64
import json
import mimetypes
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from .. import auth, billing, config, db, managed, models, onboarding, ratelimit
from ..channels import whatsapp
from ..skills import DEFAULT_SKILLS
from ..skills.base import ToolError
from ..timeutil import now
from .deps import OperatorUser, current_operator

router = APIRouter(prefix="/api/ops")


class Login(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: Login, request: Request):
    ratelimit.limit(request, "ops-login", config.RATE_LOGIN_PER_MIN)
    with db.session() as s:
        op = s.scalar(select(models.Operator).where(models.Operator.email == body.email.lower().strip()))
        if not op or not auth.verify_password(body.password, op.password_hash):
            raise HTTPException(401, "Wrong email or password")
        return {"token": auth.make_operator_token(op.id), "name": op.name or op.email}


def _shop(s, shop_id: int) -> models.Business:
    biz = s.get(models.Business, shop_id)
    if not biz:
        raise HTTPException(404, "No such shop")
    return biz


def _row(biz: models.Business, use: dict | None, last_at=None) -> dict:
    st = billing.status(biz)
    return {"id": biz.id, "name": biz.name, "slug": biz.slug, "kind": biz.kind, "city": biz.city,
            "code": biz.code, "managed": bool(biz.managed), "stage": biz.stage or "live", "active": biz.active,
            "owner_name": biz.owner_name, "owner_phone": biz.owner_phone, "number": biz.exotel_number,
            "whatsapp": "own" if biz.whatsapp_phone_number_id else ("shared" if whatsapp.on_shared(biz) else None),
            "plan": biz.plan, "billing": st["state"], "billing_until": st["until"],
            "last_activity": last_at.isoformat(timespec="minutes") if last_at else None,
            "usage": use or {"calls": 0, "call_minutes": 0, "chats": 0, "customer_messages": 0,
                             "messages_sent": 0, "cost_inr": 0, "number_rent_inr": 0}}


# ---------- overview / shops ----------

@router.get("/overview")
def overview(op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        stages = dict(s.execute(select(func.coalesce(models.Business.stage, "live"), func.count(models.Business.id))
                                .group_by(func.coalesce(models.Business.stage, "live"))).all())
        use = managed.usage(s)
        total = {k: round(sum(u[k] for u in use.values()), 1) for k in ("calls", "call_minutes", "chats",
                                                                        "messages_sent", "cost_inr")}
        return {
            "shops": sum(stages.values()), "stages": stages,
            "new_intakes": s.scalar(select(func.count(models.Intake.id)).where(models.Intake.status == "new")),
            "numbers_free": s.scalar(select(func.count(models.PhoneNumber.id))
                                     .where(models.PhoneNumber.business_id.is_(None))),
            "numbers_total": s.scalar(select(func.count(models.PhoneNumber.id))),
            "month": total,
            "channels": {"exotel_socket": bool(config.EXOTEL_WS_TOKEN),
                         "exotel_api": bool(config.EXOTEL_SID and config.EXOTEL_API_KEY and config.EXOTEL_API_TOKEN),
                         "whatsapp": whatsapp.enabled(), "shared_whatsapp": bool(config.WHATSAPP_SHARED_NUMBER_ID),
                         "voicebot_url": f"{config.PUBLIC_URL.replace('http', 'ws', 1)}/ws/exotel?token=…"},
        }


@router.get("/shops")
def shops(op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        use = managed.usage(s)
        last = dict(s.execute(select(models.Conversation.business_id, func.max(models.Conversation.last_at))
                              .where(models.Conversation.is_owner.is_(False))
                              .group_by(models.Conversation.business_id)).all())
        rows = s.scalars(select(models.Business).order_by(models.Business.id.desc())).all()
        return {"shops": [_row(b, use.get(b.id), last.get(b.id)) for b in rows], "kinds": list(DEFAULT_SKILLS)}


class NewShop(BaseModel):
    name: str
    kind: str
    city: str = ""
    owner_name: str
    owner_phone: str
    email: str | None = None
    address: str | None = None
    intake_id: int | None = None  # created from a "JOIN" message
    assign_number: bool = True


@router.post("/shops")
def create_shop(body: NewShop, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        try:
            biz, password = managed.create_shop(s, name=body.name, kind=body.kind, city=body.city,
                                                owner_name=body.owner_name, owner_phone=body.owner_phone,
                                                email=body.email or None, address=body.address)
        except ToolError as e:
            raise HTTPException(400, str(e))
        note = None
        if body.assign_number:
            try:
                managed.assign_number(s, biz)
            except ToolError as e:
                note = str(e)
        # Photos this owner already sent (before the shop existed) now belong to it.
        for item in s.scalars(select(models.Intake).where(models.Intake.business_id.is_(None),
                                                          models.Intake.from_phone == biz.owner_phone)):
            item.business_id = biz.id
            if item.kind == "join":
                item.status = "done"
        if body.intake_id:
            item = s.get(models.Intake, body.intake_id)
            if item:
                item.business_id, item.status = biz.id, "done" if item.kind == "join" else item.status
        return {"id": biz.id, "code": biz.code, "number": biz.exotel_number, "password": password, "note": note}


@router.get("/shops/{shop_id}")
def shop(shop_id: int, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        biz = _shop(s, shop_id)
        use = managed.usage(s, [biz.id]).get(biz.id)
        intakes = s.scalars(select(models.Intake).where(models.Intake.business_id == biz.id)
                            .order_by(models.Intake.id.desc()).limit(20)).all()
        login = s.scalar(select(models.OwnerUser.email).where(models.OwnerUser.business_id == biz.id))
        return {**_row(biz, use), "address": biz.address, "ops_notes": biz.ops_notes, "owner_login": login,
                "assistant_name": biz.assistant_name, "voice": biz.voice,
                "checklist": onboarding.checklist(s, biz),
                "counts": {"services": sum(x.active for x in biz.services), "products": sum(x.active for x in biz.products),
                           "staff": sum(x.active for x in biz.staff), "faqs": len(biz.faqs), "hours": len(biz.hours),
                           "samples": sum(1 for x in biz.services if x.active and x.notes == "Sample - edit me")},
                "links": {"customer_page": f"{config.PUBLIC_URL}/c/{biz.slug}", "whatsapp": managed.whatsapp_link(biz),
                          "forwarding": managed.forwarding_codes(biz.exotel_number)},
                "welcome_text": managed.welcome_text(biz),
                "intakes": [_intake(i) for i in intakes]}


class ShopPatch(BaseModel):
    stage: str | None = None
    active: bool | None = None
    ops_notes: str | None = None
    code: str | None = None
    plan: str | None = None


@router.patch("/shops/{shop_id}")
def patch_shop(shop_id: int, body: ShopPatch, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        biz = _shop(s, shop_id)
        if body.stage is not None:
            if body.stage not in managed.STAGES:
                raise HTTPException(400, f"stage must be one of {managed.STAGES}")
            biz.stage = body.stage
        if body.code is not None:
            code = re.sub(r"[^A-Za-z0-9]", "", body.code).upper()[:12]
            if not code:
                raise HTTPException(400, "Code needs letters or digits")
            clash = s.scalar(select(models.Business.id).where(func.upper(models.Business.code) == code,
                                                              models.Business.id != biz.id))
            if clash:
                raise HTTPException(400, "Another shop has that code")
            biz.code = code
        if body.plan is not None:
            if body.plan not in ("starter", "pro", "business"):
                raise HTTPException(400, "plan must be starter, pro or business")
            biz.plan = body.plan
        for k in ("active", "ops_notes"):
            if getattr(body, k) is not None:
                setattr(biz, k, getattr(body, k))
        return {"ok": True}


class AssignBody(BaseModel):
    number_id: int | None = None


@router.post("/shops/{shop_id}/number")
def assign(shop_id: int, body: AssignBody, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        biz = _shop(s, shop_id)
        try:
            num = managed.assign_number(s, biz, body.number_id)
        except ToolError as e:
            raise HTTPException(400, str(e))
        return {"number": num.number}


@router.delete("/shops/{shop_id}/number")
def release(shop_id: int, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        managed.release_number(s, _shop(s, shop_id))
    return {"ok": True}


@router.post("/shops/{shop_id}/go-live")
def go_live(shop_id: int, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        biz = _shop(s, shop_id)
        managed.go_live(s, biz)
        return {"ok": True, "welcome_text": managed.welcome_text(biz)}


@router.post("/shops/{shop_id}/open")
def open_dashboard(shop_id: int, op: OperatorUser = Depends(current_operator)):
    """A short-lived login into this shop's own dashboard, to set it up exactly as the owner would."""
    with db.session() as s:
        _shop(s, shop_id)
    return {"token": auth.make_support_token(op.operator_id, shop_id)}


# ---------- importing a shop's material ----------

class ImportText(BaseModel):
    text: str | None = None
    url: str | None = None


def _new_intake(s, biz, kind, text=None, media_path=None, extracted=None) -> models.Intake:
    item = models.Intake(business_id=biz.id, from_phone=None, source="console", kind=kind, text=text,
                         media_path=media_path, extracted=json.dumps(extracted) if extracted else None)
    s.add(item)
    s.flush()
    return item


@router.post("/shops/{shop_id}/import")
def import_text(shop_id: int, body: ImportText, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        kind = _shop(s, shop_id).kind
    text = body.text or ""
    if body.url:
        try:
            text = onboarding.fetch_website(body.url) + "\n" + text
        except Exception as e:
            raise HTTPException(400, f"Couldn't open that website ({type(e).__name__}). Paste the text instead.")
    if not text.strip():
        raise HTTPException(400, "Paste some text or give a website.")
    try:
        data = onboarding.extract(kind, text=text)
    except Exception as e:
        raise HTTPException(502, f"Couldn't read it: {e}")
    with db.session() as s:
        item = _new_intake(s, _shop(s, shop_id), "text", text=text[:20000], extracted=data)
        return _intake(item)


@router.post("/shops/{shop_id}/import-photo")
async def import_photo(shop_id: int, photo: UploadFile = File(...), op: OperatorUser = Depends(current_operator)):
    data = await photo.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Photo is too large (max 8 MB).")
    with db.session() as s:
        kind = _shop(s, shop_id).kind
    mime = photo.content_type or "image/jpeg"
    try:
        extracted = await asyncio.to_thread(onboarding.extract, kind, None, data, mime)
    except Exception as e:
        raise HTTPException(502, f"Couldn't read the photo: {e}")
    folder = config.MEDIA_DIR / "intake"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"console-{shop_id}-{int(now().timestamp())}{mimetypes.guess_extension(mime) or '.jpg'}"
    path.write_bytes(data)
    with db.session() as s:
        item = _new_intake(s, _shop(s, shop_id), "photo", media_path=str(path), extracted=extracted)
        return _intake(item)


# ---------- intake inbox ----------

def _intake(i: models.Intake, with_media: bool = False) -> dict:
    out = {"id": i.id, "business_id": i.business_id, "from_phone": i.from_phone, "source": i.source, "kind": i.kind,
           "text": i.text, "status": i.status, "created_at": i.created_at.isoformat(timespec="minutes"),
           "extracted": json.loads(i.extracted) if i.extracted else None, "has_media": bool(i.media_path)}
    if with_media and i.media_path and Path(i.media_path).exists():
        mime = mimetypes.guess_type(i.media_path)[0] or "image/jpeg"
        out["media"] = f"data:{mime};base64,{base64.b64encode(Path(i.media_path).read_bytes()).decode()}"
    return out


@router.get("/intakes")
def intakes(status: str = "new", op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        q = select(models.Intake).order_by(models.Intake.id.desc()).limit(200)
        if status != "all":
            q = q.where(models.Intake.status == status)
        rows = s.scalars(q).all()
        names = dict(s.execute(select(models.Business.id, models.Business.name)).all())
        return {"intakes": [{**_intake(i), "shop": names.get(i.business_id)} for i in rows]}


@router.get("/intakes/{intake_id}")
def intake(intake_id: int, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        i = s.get(models.Intake, intake_id)
        if not i:
            raise HTTPException(404)
        return _intake(i, with_media=True)


@router.post("/intakes/{intake_id}/read")
def reread(intake_id: int, op: OperatorUser = Depends(current_operator)):
    """(Re)read a stored photo or text with the LLM, e.g. one that arrived before its shop existed."""
    with db.session() as s:
        i = s.get(models.Intake, intake_id)
        if not i or not i.business_id:
            raise HTTPException(400, "Attach it to a shop first (create the shop from this owner's number).")
        kind, path, text = _shop(s, i.business_id).kind, i.media_path, i.text
    try:
        if path:
            data = Path(path).read_bytes()
            data_out = onboarding.extract(kind, text, data, mimetypes.guess_type(path)[0] or "image/jpeg")
        else:
            data_out = onboarding.extract(kind, text=text or "")
    except Exception as e:
        raise HTTPException(502, f"Couldn't read it: {e}")
    with db.session() as s:
        i = s.get(models.Intake, intake_id)
        i.extracted = json.dumps(data_out)
        return _intake(i)


@router.post("/intakes/{intake_id}/apply")
def apply_intake(intake_id: int, body: dict, op: OperatorUser = Depends(current_operator)):
    """Save reviewed data (the operator may have edited `extracted`) into the shop."""
    with db.session() as s:
        i = s.get(models.Intake, intake_id)
        if not i or not i.business_id:
            raise HTTPException(400, "This intake isn't attached to a shop.")
        biz = _shop(s, i.business_id)
        data = body.get("data") or (json.loads(i.extracted) if i.extracted else None)
        if not data:
            raise HTTPException(400, "Nothing to apply; read it first.")
        counts = onboarding.apply(s, biz, data)
        i.status = "applied"
        if biz.stage == "setup":
            biz.stage = "review"
        return {"saved": counts}


class IntakePatch(BaseModel):
    status: str


@router.patch("/intakes/{intake_id}")
def patch_intake(intake_id: int, body: IntakePatch, op: OperatorUser = Depends(current_operator)):
    if body.status not in ("new", "done", "discarded"):
        raise HTTPException(400, "status must be new, done or discarded")
    with db.session() as s:
        i = s.get(models.Intake, intake_id)
        if not i:
            raise HTTPException(404)
        i.status = body.status
    return {"ok": True}


# ---------- numbers ----------

@router.get("/numbers")
def numbers(op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        names = dict(s.execute(select(models.Business.id, models.Business.name)).all())
        rows = s.scalars(select(models.PhoneNumber).order_by(models.PhoneNumber.id)).all()
        return {"numbers": [{"id": n.id, "number": n.number, "provider": n.provider, "notes": n.notes,
                             "monthly_cost_inr": n.monthly_cost_inr, "business_id": n.business_id,
                             "shop": names.get(n.business_id),
                             "assigned_at": n.assigned_at.isoformat(timespec="minutes") if n.assigned_at else None}
                            for n in rows],
                "exotel_api": bool(config.EXOTEL_SID and config.EXOTEL_API_KEY and config.EXOTEL_API_TOKEN)}


class AddNumbers(BaseModel):
    numbers: list[str]
    monthly_cost_inr: int = 0
    notes: str | None = None


@router.post("/numbers")
def add_numbers(body: AddNumbers, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        added = managed.add_numbers(s, body.numbers, body.monthly_cost_inr, body.notes)
    if not added:
        raise HTTPException(400, "No new numbers (need 10+ digits; duplicates are skipped).")
    return {"added": added}


@router.delete("/numbers/{number_id}")
def delete_number(number_id: int, op: OperatorUser = Depends(current_operator)):
    with db.session() as s:
        n = s.get(models.PhoneNumber, number_id)
        if not n:
            raise HTTPException(404)
        if n.business_id:
            raise HTTPException(400, "Release it from its shop first.")
        s.delete(n)
    return {"ok": True}


def _phone_numbers(obj) -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("phone_number", "PhoneNumber") and isinstance(v, str):
                found.append(v)
            else:
                found += _phone_numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _phone_numbers(v)
    return found


@router.post("/numbers/sync-exotel")
def sync_exotel(op: OperatorUser = Depends(current_operator)):
    """Pull the ExoPhones on Alaap's Exotel account into the pool (needs EXOTEL_SID, _API_KEY, _API_TOKEN)."""
    if not (config.EXOTEL_SID and config.EXOTEL_API_KEY and config.EXOTEL_API_TOKEN):
        raise HTTPException(400, "Set EXOTEL_SID, EXOTEL_API_KEY and EXOTEL_API_TOKEN in .env first.")
    url = f"https://{config.EXOTEL_SUBDOMAIN}/v2_beta/Accounts/{config.EXOTEL_SID}/IncomingPhoneNumbers"
    try:
        r = httpx.get(url, auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN), timeout=20,
                      headers={"Accept": "application/json"})
        r.raise_for_status()
        found = _phone_numbers(r.json())
    except Exception as e:
        raise HTTPException(502, f"Exotel didn't answer ({e}). Add the numbers by hand instead.")
    with db.session() as s:
        added = managed.add_numbers(s, found, notes="from Exotel")
    return {"found": len(found), "added": added}


# ---------- usage ----------

@router.get("/usage")
def usage(month: str | None = None, op: OperatorUser = Depends(current_operator)):
    """Per shop for one month: activity, rough cost, plan price and margin."""
    from datetime import datetime, timedelta

    from ..skills import PLANS

    start = managed.month_start()
    if month:
        try:
            start = datetime.strptime(month, "%Y-%m")
        except ValueError:
            raise HTTPException(400, "month is YYYY-MM")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    with db.session() as s:
        use = managed.usage(s, since=start, until=end)
        rows = []
        for b in s.scalars(select(models.Business).order_by(models.Business.name)):
            u = use.get(b.id) or {"calls": 0, "call_minutes": 0, "chats": 0, "customer_messages": 0,
                                  "messages_sent": 0, "cost_inr": 0, "number_rent_inr": 0}
            plan = PLANS.get(b.plan, PLANS["starter"])
            rows.append({"id": b.id, "name": b.name, "plan": b.plan, "price_inr": plan["price_inr"],
                         "included_minutes": plan["minutes"], "margin_inr": round(plan["price_inr"] - u["cost_inr"]),
                         **u})
        return {"month": start.strftime("%Y-%m"), "shops": rows,
                "rates": {"call_min": config.COST_CALL_MIN_INR, "wa_msg": config.COST_WA_MSG_INR,
                          "chat_turn": config.COST_CHAT_TURN_INR}}
