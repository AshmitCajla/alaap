import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .. import config, payments
from ..channels import whatsapp
from .public import mark_paid

router = APIRouter(prefix="/webhooks")


@router.get("/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == config.WHATSAPP_VERIFY_TOKEN:
        return q.get("hub.challenge", "")
    raise HTTPException(403)


@router.post("/whatsapp")
async def whatsapp_receive(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not whatsapp.verify_signature(body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403, "Bad signature")
    background.add_task(whatsapp.handle_webhook, json.loads(body or b"{}"))
    return {"ok": True}  # answer fast; Meta retries slow webhooks


@router.post("/razorpay")
async def razorpay(request: Request):
    body = await request.body()
    if not payments.verify_webhook(body, request.headers.get("x-razorpay-signature")):
        raise HTTPException(403, "Bad signature")
    event = json.loads(body)
    if event.get("event") == "payment_link.paid":
        link_id = event["payload"]["payment_link"]["entity"]["id"]
        from .. import billing, db

        with db.session() as s:
            plan = billing.mark_paid(s, link_id)
            if plan:
                return {"ok": True, "plan": plan.plan}
        return {"ok": True, "order": mark_paid(link_id)}
    return {"ok": True}
