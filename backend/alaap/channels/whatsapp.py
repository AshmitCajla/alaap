"""WhatsApp Cloud API: receive text and voice notes, reply with text (and voice).

Setup: in Meta's developer console, point the webhook to {PUBLIC_URL}/webhooks/whatsapp with
WHATSAPP_VERIFY_TOKEN, subscribe to `messages`, and set each business's
whatsapp_phone_number_id (Settings page)."""

import hashlib
import hmac
import logging

import httpx
from sqlalchemy import select

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


def _handle_message(phone_number_id: str, msg: dict) -> None:
    with db.session() as s:
        biz = s.scalar(select(models.Business).where(models.Business.whatsapp_phone_number_id == phone_number_id))
        if not biz:
            log.warning("No business for WhatsApp number %s", phone_number_id)
            return
        s.expunge(biz)
    sender = normalise_phone(msg.get("from"))
    owner = sender is not None and sender == normalise_phone(biz.owner_phone)
    voice_in = msg.get("type") in ("audio", "voice")
    if msg.get("type") == "text":
        text = msg["text"]["body"]
    elif voice_in:
        stt = speech.provider()
        if not stt:
            send_text(phone_number_id, sender, "Sorry, voice notes aren't set up yet. Please type your message.")
            return
        audio, mime = download_media(msg["audio"]["id"])
        text = stt.transcribe(audio, "voice.ogg", mime.split(";")[0]).text
        if not text:
            send_text(phone_number_id, sender, "Maaf kijiye, awaaz saaf nahi aayi. Kripya dobara bhejiye.")
            return
    else:
        send_text(phone_number_id, sender, "Please send a text or voice message.")
        return
    cid = _conversation_for(biz, sender, owner)
    reply = get_engine().reply(cid, text)
    send_text(phone_number_id, sender, reply.text)
    tts = speech.provider()
    if voice_in and tts:  # answer a voice note with a voice note too
        try:
            ogg = tts.synthesize(for_speech(reply.text), sample_rate=24000, container="ogg", encoding="oggopus",
                                 voice=biz.voice, speed=biz.speech_speed)
            send_audio(phone_number_id, sender, ogg)
        except Exception:
            log.exception("voice reply failed")
