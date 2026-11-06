"""UPI payment links via Razorpay Payment Links. Without keys (local dev and
demos) links point to a mock page on this server that marks the order paid."""

import hashlib
import hmac
import logging

import httpx

from . import config, models

log = logging.getLogger("alaap.payments")


def live() -> bool:
    return bool(config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET)


def create_link(biz: models.Business, order: models.Order) -> tuple[str, str]:
    """Create a payment link for an order. Returns (link_id, short_url)."""
    if not live():
        link_id = f"mock_{order.ref}"
        return link_id, f"{config.PUBLIC_URL}/pay/mock/{link_id}"
    payload = {
        "amount": order.total_inr * 100,  # paise
        "currency": "INR",
        "accept_partial": False,
        "reference_id": f"{biz.slug}-{order.ref}",
        "description": f"{biz.name} order {order.ref}",
        "customer": {"name": order.customer.name, "contact": f"+91{order.customer.phone}"},
        "notify": {"sms": False, "email": False},  # Alaap sends it on WhatsApp
        "reminder_enable": True,
        "notes": {"business_id": str(biz.id), "order_ref": order.ref},
        "callback_url": f"{config.PUBLIC_URL}/pay/done",
        "callback_method": "get",
    }
    r = httpx.post("https://api.razorpay.com/v1/payment_links", json=payload, timeout=15,
                   auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
    r.raise_for_status()
    data = r.json()
    return data["id"], data["short_url"]


def verify_webhook(body: bytes, signature: str | None) -> bool:
    if not config.RAZORPAY_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(config.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
