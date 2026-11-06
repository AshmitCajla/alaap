"""Customer-facing endpoints: web widget chat and voice, payments pages, health."""

import base64
import time

import jwt
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select

from .. import config, db, models, ratelimit, speech
from ..channels.voice import CallSession, business_for_call
from ..engine import assistant_name, get_engine, is_female
from ..spoken import for_speech

router = APIRouter()


def _chat_token(cid: int) -> str:
    return jwt.encode({"cid": cid, "exp": int(time.time()) + 6 * 3600}, config.SECRET_KEY, algorithm="HS256")


def _check(cid: int, token: str) -> None:
    try:
        if jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"]).get("cid") != cid:
            raise HTTPException(403, "Wrong conversation")
    except jwt.PyJWTError:
        raise HTTPException(403, "Conversation expired; start again")


def _business(slug: str) -> models.Business:
    with db.session() as s:
        biz = s.scalar(select(models.Business).where(models.Business.slug == slug, models.Business.active.is_(True)))
        if not biz:
            raise HTTPException(404, "No such business")
        s.expunge(biz)
        return biz


@router.get("/health")
def health():
    """Liveness + readiness: checks the database too (used by Docker and uptime monitors)."""
    from sqlalchemy import text

    try:
        with db.session() as s:
            s.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(503, f"database unavailable: {type(e).__name__}")
    return {"ok": True, "env": config.ENV, "speech": bool(speech.provider()), "llm": config.LLM_PROVIDER}


@router.get("/api/public/{slug}")
def public_info(slug: str):
    biz = _business(slug)
    return {"slug": biz.slug, "name": biz.name, "kind": biz.kind, "city": biz.city,
            "voice": bool(speech.provider()), "assistant": assistant_name(biz), "female": is_female(biz)}


class StartChat(BaseModel):
    phone: str | None = None


class ChatMessage(BaseModel):
    text: str
    token: str


MAX_TEXT = 1000          # characters per customer message
MAX_AUDIO = 3_000_000    # bytes per voice message (~30 s of 16 kHz WAV)


@router.post("/api/chat/{slug}/start")
def chat_start(slug: str, body: StartChat, request: Request):
    ratelimit.limit(request, "chat-start", config.RATE_CHAT_PER_MIN // 3 or 1)
    biz = _business(slug)
    r = get_engine().start(biz.id, "web", body.phone)
    return {"conversation_id": r.conversation_id, "token": _chat_token(r.conversation_id), "text": r.text}


@router.post("/api/chat/{cid}/message")
def chat_message(cid: int, body: ChatMessage, request: Request):
    ratelimit.limit(request, "chat", config.RATE_CHAT_PER_MIN)
    _check(cid, body.token)
    r = get_engine().reply(cid, body.text[:MAX_TEXT])
    return {"text": r.text, "handoff": r.handoff}


@router.post("/api/chat/{cid}/voice")
def chat_voice(cid: int, request: Request, token: str = Form(...), audio: UploadFile = File(...)):
    """A recorded voice message (WAV from the widget): Gnani STT -> engine -> Gnani TTS."""
    ratelimit.limit(request, "chat", config.RATE_CHAT_PER_MIN)
    _check(cid, token)
    gn = speech.provider()
    if not gn:
        raise HTTPException(503, "Voice needs GNANI_API_KEY")
    data = audio.file.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "Voice message too long; keep it under 30 seconds.")
    heard = gn.transcribe(data, audio.filename or "audio.wav", audio.content_type or "audio/wav")
    if not heard.text:
        return {"heard": "", "text": "Maaf kijiye, awaaz saaf nahi aayi. Dobara boliye?", "audio": None}
    r = get_engine().reply(cid, heard.text)
    with db.session() as s:
        conv = s.get(models.Conversation, cid)
        biz = s.get(models.Business, conv.business_id)
        voice, speed = biz.voice, biz.speech_speed
    wav = gn.synthesize(for_speech(r.text), sample_rate=24000, container="wav", voice=voice, speed=speed)
    return {"heard": heard.text, "language": heard.language, "text": r.text,
            "audio": base64.b64encode(wav).decode()}


@router.websocket("/ws/call/{slug}")
async def browser_call(ws: WebSocket, slug: str):
    """Live call from the web widget (same protocol as Exotel, 16 kHz)."""
    await ws.accept()
    if not ratelimit.hit(f"call:{ws.client.host if ws.client else '?'}", config.RATE_CALLS_PER_MIN):
        await ws.close(code=1013, reason="Too many calls; try again in a minute")
        return
    biz_id = business_for_call(slug, None)
    if not biz_id:
        await ws.close(code=1008)
        return
    await CallSession(ws, biz_id).run()


@router.websocket("/ws/exotel")
async def exotel_call(ws: WebSocket, biz: str | None = None):
    """Exotel Voicebot applet URL: wss://<host>/ws/exotel?biz=<slug>"""
    await ws.accept()
    biz_id = business_for_call(biz, ws.query_params.get("to"))
    if not biz_id:
        await ws.close(code=1008)
        return
    await CallSession(ws, biz_id).run()


# ---------- payments ----------

def mark_paid(link_id: str) -> str | None:
    from .. import notify

    with db.session() as s:
        order = s.scalar(select(models.Order).where(models.Order.payment_link_id == link_id))
        if not order:
            return None
        if order.payment_status != "paid":
            order.payment_status = "paid"
            biz = s.get(models.Business, order.business_id)
            notify.queue(s, biz, order.customer.phone, "payment_received",
                         f"Payment of Rs {order.total_inr} received for order {order.ref}. Thank you!", order_id=order.id)
            notify.owner_alert(s, biz, f"Order {order.ref} paid: Rs {order.total_inr} (UPI)")
        return order.ref


PAGE = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{font-family:system-ui;max-width:420px;margin:48px auto;padding:0 16px;color:#1d1d1f}}
button{{background:#0f766e;color:#fff;border:0;border-radius:10px;padding:14px 20px;font-size:16px;width:100%}}
.muted{{color:#666;font-size:14px}}</style></head><body>{body}</body></html>"""


@router.get("/pay/mock/{link_id}", response_class=HTMLResponse)
def mock_pay_page(link_id: str):
    if config.PRODUCTION:
        raise HTTPException(404)
    if link_id.startswith("mockplan_"):
        with db.session() as s:
            pay = s.scalar(select(models.PlanPayment).where(models.PlanPayment.link_id == link_id))
            if not pay:
                raise HTTPException(404)
            body = (f"<h2>Alaap {pay.plan.title()} plan</h2><p>{pay.months} month(s) · <b>Rs {pay.amount_inr}</b></p>"
                    + ("<p>Already paid. Thank you!</p>" if pay.status == "paid" else
                       f"<form method=post><button>Pay Rs {pay.amount_inr} (test)</button></form>")
                    + "<p class=muted>Test payment page. Set Razorpay keys for real UPI payments.</p>")
        return PAGE.format(title="Pay", body=body)
    with db.session() as s:
        order = s.scalar(select(models.Order).where(models.Order.payment_link_id == link_id))
        if not order:
            raise HTTPException(404)
        biz = s.get(models.Business, order.business_id)
        body = (f"<h2>{biz.name}</h2><p>Order {order.ref} &middot; <b>Rs {order.total_inr}</b></p>"
                + ("<p>Already paid. Thank you!</p>" if order.payment_status == "paid" else
                   f"<form method=post><button>Pay Rs {order.total_inr} (test)</button></form>")
                + "<p class=muted>Test payment page. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET for real UPI links.</p>")
    return PAGE.format(title="Pay", body=body)


@router.post("/pay/mock/{link_id}", response_class=HTMLResponse)
def mock_pay(link_id: str):
    if config.RAZORPAY_KEY_ID or config.PRODUCTION:
        raise HTTPException(404)
    if link_id.startswith("mockplan_"):
        from .. import billing

        with db.session() as s:
            pay = billing.mark_paid(s, link_id)
            if not pay:
                raise HTTPException(404)
            return PAGE.format(title="Paid", body=f"<h2>Paid</h2><p>Alaap {pay.plan.title()} plan is active. "
                                                  f"<a href='{config.DASHBOARD_URL}/billing'>Back to dashboard</a></p>")
    ref = mark_paid(link_id)
    if not ref:
        raise HTTPException(404)
    return PAGE.format(title="Paid", body=f"<h2>Paid</h2><p>Order {ref} is paid. Thank you!</p>")


@router.get("/pay/done", response_class=HTMLResponse)
def pay_done():
    return PAGE.format(title="Thank you", body="<h2>Thank you!</h2><p>Your payment is being confirmed.</p>")
