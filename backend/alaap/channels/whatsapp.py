"""WhatsApp Cloud API: receive text and voice notes, reply with text (and voice).

Setup: in Meta's developer console, point the webhook to {PUBLIC_URL}/webhooks/whatsapp with
WHATSAPP_VERIFY_TOKEN, subscribe to `messages`, and set each business's
whatsapp_phone_number_id (Settings page)."""

import hashlib
import hmac
import json
import logging
import re
import time

import httpx
from sqlalchemy import func, select

from .. import config, db, models, speech
from ..engine import get_engine
from ..skills.base import normalise_phone
from ..spoken import for_speech
from ..state import store

log = logging.getLogger("alaap.whatsapp")
GRAPH = "https://graph.facebook.com"
IDLE_MINUTES = 30  # a new message after this long starts a new conversation


def enabled() -> bool:
    return bool(config.WHATSAPP_TOKEN)


def _headers():
    return {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}


def verify_signature(body: bytes, signature: str | None) -> bool:
    if not config.WHATSAPP_APP_SECRET:
        return True  # not configured (local dev)
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(config.WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature[7:])


def send_text(phone_number_id: str, to: str, text: str) -> str:
    r = httpx.post(f"{GRAPH}/{config.WHATSAPP_API_VERSION}/{phone_number_id}/messages", headers=_headers(), timeout=20,
                   json={"messaging_product": "whatsapp", "to": _intl(to), "type": "text",
                         "text": {"body": text[:4096], "preview_url": True}})
    r.raise_for_status()
    return r.json()["messages"][0]["id"]


OUTSIDE_WINDOW = {131047, 131026, 470}  # "re-engagement message" / outside the 24-hour customer window


def needs_template(err: Exception) -> bool:
    resp = getattr(err, "response", None)
    try:
        return int(resp.json()["error"]["code"]) in OUTSIDE_WINDOW
    except Exception:
        return False


def send_template(phone_number_id: str, to: str, business_name: str, text: str) -> str:
    """Business-initiated message via the approved utility template ("Update from {{1}}: {{2}}")."""
    body = {"messaging_product": "whatsapp", "to": _intl(to), "type": "template", "template": {
        "name": config.WHATSAPP_TEMPLATE_NAME, "language": {"code": config.WHATSAPP_TEMPLATE_LANG},
        "components": [{"type": "body", "parameters": [
            {"type": "text", "text": business_name[:60]},
            {"type": "text", "text": " ".join(text.split())[:1000]}]}]}}  # template params can't contain newlines
    r = httpx.post(f"{GRAPH}/{config.WHATSAPP_API_VERSION}/{phone_number_id}/messages", headers=_headers(),
                   timeout=20, json=body)
    r.raise_for_status()
    return r.json()["messages"][0]["id"]


def send_audio(phone_number_id: str, to: str, ogg_bytes: bytes) -> str:
    """Upload an OGG/Opus voice note and send it."""
    up = httpx.post(f"{GRAPH}/{config.WHATSAPP_API_VERSION}/{phone_number_id}/media", headers=_headers(), timeout=30,
                    data={"messaging_product": "whatsapp", "type": "audio/ogg"},
                    files={"file": ("voice.ogg", ogg_bytes, "audio/ogg")})
    up.raise_for_status()
    r = httpx.post(f"{GRAPH}/{config.WHATSAPP_API_VERSION}/{phone_number_id}/messages", headers=_headers(), timeout=20,
                   json={"messaging_product": "whatsapp", "to": _intl(to), "type": "audio",
                         "audio": {"id": up.json()["id"]}})
    r.raise_for_status()
    return r.json()["messages"][0]["id"]


def download_media(media_id: str) -> tuple[bytes, str]:
    meta = httpx.get(f"{GRAPH}/{config.WHATSAPP_API_VERSION}/{media_id}", headers=_headers(), timeout=20)
    meta.raise_for_status()
    info = meta.json()
    data = httpx.get(info["url"], headers=_headers(), timeout=30)
    data.raise_for_status()
    return data.content, info.get("mime_type", "audio/ogg")


def _intl(phone: str) -> str:
    p = normalise_phone(phone) or phone
    return f"91{p}" if len(p) == 10 else p


def _conversation_for(biz: models.Business, phone: str, owner: bool) -> int:
    """Reuse the open WhatsApp conversation with this number, or start one."""
    key = f"wa:{biz.id}:{phone}"
    st = store()
    cid = (st.get(key) or {}).get("conversation_id")
    if cid:
        with db.session() as s:
            conv = s.get(models.Conversation, cid)
            from ..timeutil import now
            if conv and not conv.ended_at and (now(biz.timezone) - conv.last_at).total_seconds() < IDLE_MINUTES * 60:
                return cid
    cid = get_engine().start(biz.id, "whatsapp", phone, owner=owner, verified=True).conversation_id
    st.set(key, {"conversation_id": cid})
    return cid


def handle_webhook(payload: dict) -> int:
    """Process a webhook delivery. Returns the number of messages handled."""
    handled = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            pnid = value.get("metadata", {}).get("phone_number_id")
            for msg in value.get("messages", []):
                try:
                    _handle_message(pnid, msg)
                    handled += 1
                except Exception:
                    log.exception("whatsapp message failed")
    return handled


def sender_id(biz: models.Business) -> str | None:
    """The WhatsApp number this shop's messages go out from: its own, or Alaap's shared number."""
    return biz.whatsapp_phone_number_id or (config.WHATSAPP_SHARED_NUMBER_ID if biz.code else None)


def on_shared(biz: models.Business) -> bool:
    return not biz.whatsapp_phone_number_id and bool(config.WHATSAPP_SHARED_NUMBER_ID and biz.code)


def labelled(biz: models.Business, text: str) -> str:
    """On the shared number one chat may hear from several shops, so say which shop is talking."""
    return f"*{biz.name}*\n{text}" if on_shared(biz) else text


def _read(phone_number_id: str, sender: str, msg: dict) -> tuple[str | None, bool]:
    """Text of a text or voice message (None if it couldn't be read; the sender has been told)."""
    if msg.get("type") == "text":
        return msg["text"]["body"], False
    if msg.get("type") in ("audio", "voice"):
        stt = speech.provider()
        if not stt:
            send_text(phone_number_id, sender, "Sorry, voice notes aren't set up yet. Please type your message.")
            return None, True
        audio, mime = download_media(msg["audio"]["id"])
        text = stt.transcribe(audio, "voice.ogg", mime.split(";")[0]).text
        if not text:
            send_text(phone_number_id, sender, "Maaf kijiye, awaaz saaf nahi aayi. Kripya dobara bhejiye.")
            return None, True
        return text, True
    return None, False


def _converse(phone_number_id: str, biz: models.Business, sender: str, text: str, owner: bool, voice_in: bool,
              label: bool = False) -> None:
    cid = _conversation_for(biz, sender, owner)
    reply = get_engine().reply(cid, text)
    send_text(phone_number_id, sender, labelled(biz, reply.text) if label else reply.text)
    tts = speech.provider()
    if voice_in and tts:  # answer a voice note with a voice note too
        try:
            ogg = tts.synthesize(for_speech(reply.text), sample_rate=24000, container="ogg", encoding="oggopus",
                                 voice=biz.voice, speed=biz.speech_speed)
            send_audio(phone_number_id, sender, ogg)
        except Exception:
            log.exception("voice reply failed")


def _save_photo(msg: dict, biz: models.Business | None, sender: str) -> models.Intake:
    """A menu / rate-card photo from an owner: keep it, read it with the LLM, queue it for the team to review."""
    from .. import onboarding

    media = msg.get("image") or msg.get("document") or {}
    data, mime = download_media(media["id"])
    folder = config.MEDIA_DIR / "intake"
    folder.mkdir(parents=True, exist_ok=True)
    ext = {"image/png": "png", "application/pdf": "pdf"}.get(mime.split(";")[0], "jpg")
    path = folder / f"{sender}-{int(time.time())}.{ext}"
    path.write_bytes(data)
    extracted = None
    if biz and mime.startswith("image/"):
        try:
            extracted = json.dumps(onboarding.extract(biz.kind, media.get("caption"), data, mime.split(";")[0]))
        except Exception:
            log.exception("reading menu photo failed")
    with db.session() as s:
        item = models.Intake(business_id=biz.id if biz else None, from_phone=sender, kind="photo",
                             text=media.get("caption"), media_path=str(path), extracted=extracted)
        s.add(item)
        s.flush()
        s.expunge(item)
    return item


def _intake_reply(item: models.Intake) -> str:
    if not item.extracted:
        return "Photo mil gayi, dhanyavaad! Alaap team ise dekh kar aapki details update kar degi."
    d = json.loads(item.extracted)
    parts = [f"{len(d.get(k) or [])} {label}" for k, label in (("services", "services"), ("products", "items"))
             if d.get(k)]
    got = " aur ".join(parts) or "kuch details"
    return (f"Photo mil gayi! Isme {got} padhe. Alaap team check karke aaj hi update kar degi; "
            "update hote hi aapko yahin message aayega.")


def _handle_message(phone_number_id: str, msg: dict) -> None:
    sender = normalise_phone(msg.get("from"))
    if not sender:
        return
    if config.WHATSAPP_SHARED_NUMBER_ID and phone_number_id == config.WHATSAPP_SHARED_NUMBER_ID:
        return _handle_shared(phone_number_id, sender, msg)
    with db.session() as s:
        biz = s.scalar(select(models.Business).where(models.Business.whatsapp_phone_number_id == phone_number_id))
        if not biz:
            log.warning("No business for WhatsApp number %s", phone_number_id)
            return
        s.expunge(biz)
    owner = sender == normalise_phone(biz.owner_phone)
    if owner and msg.get("type") in ("image", "document"):
        send_text(phone_number_id, sender, _intake_reply(_save_photo(msg, biz, sender)))
        return
    text, voice_in = _read(phone_number_id, sender, msg)
    if text is None:
        if not voice_in:
            send_text(phone_number_id, sender, "Please send a text or voice message.")
        return
    _converse(phone_number_id, biz, sender, text, owner, voice_in)


JOIN = re.compile(r"^\s*(join|alaap|demo|register|signup|sign up)\b", re.I)
WELCOME_SHARED = ("Namaste! Yeh Alaap hai, dukaanon ka AI receptionist.\n"
                  "Kisi dukaan se baat karni hai? Unke poster par diya code bhejiye (jaise GLOW).\n"
                  "Apni dukaan ke liye Alaap chahiye? JOIN likh kar bhejiye.")


def _shop_by_code(word: str) -> models.Business | None:
    code = re.sub(r"[^A-Za-z0-9]", "", word or "").upper()
    if not code or len(code) > 12:
        return None
    with db.session() as s:
        biz = s.scalar(select(models.Business).where(func.upper(models.Business.code) == code,
                                                     models.Business.active.is_(True)))
        if biz:
            s.expunge(biz)
        return biz


def _shop(biz_id: int) -> models.Business | None:
    with db.session() as s:
        biz = s.get(models.Business, biz_id)
        if biz:
            s.expunge(biz)
        return biz


def _handle_shared(pnid: str, sender: str, msg: dict) -> None:
    """Alaap's shared number: route each sender to a shop by its code, its owner, or the join flow.

    Order: a shop code in the message > the sender owns a managed shop > the shop they last messaged > help."""
    st = store()
    route_key = f"wa:route:{sender}"
    if msg.get("type") in ("image", "document"):
        owned = _owned_shop(sender)
        item = _save_photo(msg, owned, sender)
        send_text(pnid, sender, _intake_reply(item) if owned else
                  "Photo mil gayi, dhanyavaad! Alaap team aapko jaldi call karegi aur aapki dukaan set kar degi.")
        return
    text, voice_in = _read(pnid, sender, msg)
    if text is None:
        if not voice_in:
            send_text(pnid, sender, WELCOME_SHARED)
        return
    first, _, rest = text.strip().partition(" ")
    biz = _shop_by_code(first)
    if biz:
        st.set(route_key, {"business_id": biz.id})
        _converse(pnid, biz, sender, rest.strip() or "Namaste", sender == normalise_phone(biz.owner_phone),
                  voice_in, label=True)
        return
    if JOIN.match(text):
        with db.session() as s:
            s.add(models.Intake(from_phone=sender, kind="join", text=text))
        send_text(pnid, sender, "Dhanyavaad! Alaap team aapko jaldi call karegi. Tab tak apna rate card ya menu "
                                "ki photo yahin bhej dijiye, hum sab set kar denge. Aapko kuch install nahi karna.")
        return
    owned = _owned_shop(sender)
    if owned:
        _converse(pnid, owned, sender, text, True, voice_in)
        return
    routed = (st.get(route_key) or {}).get("business_id")
    biz = _shop(routed) if routed else None
    if biz and biz.active:
        _converse(pnid, biz, sender, text, False, voice_in)
        return
    send_text(pnid, sender, WELCOME_SHARED)


def _owned_shop(sender: str) -> models.Business | None:
    """The managed shop this number owns (owners use the shared number for alerts, updates and menus)."""
    with db.session() as s:
        biz = s.scalar(select(models.Business).where(models.Business.owner_phone == sender,
                                                     models.Business.managed.is_(True)).order_by(models.Business.id))
        if biz:
            s.expunge(biz)
        return biz
