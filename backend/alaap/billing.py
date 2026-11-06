"""Plans, free trial and plan payments (Razorpay payment links; a test page in development)."""

import logging
import time
from datetime import timedelta

import httpx
from sqlalchemy import select

from . import config, models, notify
from .skills import PLANS
from .timeutil import now

log = logging.getLogger("alaap.billing")


def status(biz: models.Business) -> dict:
    t = now(biz.timezone)
    if biz.paid_until and biz.paid_until > t:
        state, until = "active", biz.paid_until
    elif biz.trial_ends_at and biz.trial_ends_at > t:
        state, until = "trial", biz.trial_ends_at
    elif biz.trial_ends_at is None and biz.paid_until is None:
        state, until = "active", None  # created before billing existed (e.g. demo businesses)
    else:
        state, until = "expired", biz.paid_until or biz.trial_ends_at
    days_left = max(0, (until - t).days) if until else None
    return {"plan": biz.plan, "state": state, "until": until.strftime("%Y-%m-%d") if until else None,
            "days_left": days_left, "price_inr": PLANS.get(biz.plan, PLANS["starter"])["price_inr"]}


def can_serve(biz: models.Business) -> bool:
    return not config.ENFORCE_BILLING or status(biz)["state"] != "expired"


def suspended_message(biz: models.Business) -> str:
    phone = f" {biz.phone} par" if biz.phone else ""
    return (f"Namaste! Abhi {biz.name} ki online booking band hai. Kripya dukaan par seedha{phone} call kijiye. "
            f"Dhanyavaad!")


def checkout(s, biz: models.Business, plan: str, months: int = 1) -> models.PlanPayment:
    if plan not in PLANS:
        raise ValueError("Unknown plan")
    months = max(1, min(12, int(months)))
    amount = PLANS[plan]["price_inr"] * months
    pay = models.PlanPayment(business_id=biz.id, plan=plan, months=months, amount_inr=amount)
    s.add(pay)
    s.flush()
    if config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET:
        r = httpx.post("https://api.razorpay.com/v1/payment_links", timeout=15,
                       auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET), json={
                           "amount": amount * 100, "currency": "INR",
                           "reference_id": f"plan-{biz.id}-{pay.id}-{int(time.time())}",
                           "description": f"Alaap {plan.title()} plan for {biz.name}, {months} month(s)",
                           "customer": {"name": biz.owner_name or biz.name,
                                        "contact": f"+91{biz.owner_phone}" if biz.owner_phone else None},
                           "notify": {"sms": True, "email": False}, "reminder_enable": True,
                           "notes": {"kind": "plan", "business_id": str(biz.id), "plan_payment_id": str(pay.id)},
                           "callback_url": f"{config.DASHBOARD_URL}/billing?paid=1", "callback_method": "get"})
        r.raise_for_status()
        data = r.json()
        pay.link_id, pay.link_url = data["id"], data["short_url"]
    elif config.PRODUCTION:
        raise RuntimeError("Razorpay keys are not configured.")
    else:
        pay.link_id = f"mockplan_{pay.id}"
        pay.link_url = f"{config.PUBLIC_URL}/pay/mock/{pay.link_id}"
    return pay


def mark_paid(s, link_id: str) -> models.PlanPayment | None:
    pay = s.scalar(select(models.PlanPayment).where(models.PlanPayment.link_id == link_id))
    if not pay or pay.status == "paid":
        return pay
    biz = s.get(models.Business, pay.business_id)
    t = now(biz.timezone)
    start = max(t, biz.paid_until or t, biz.trial_ends_at or t)  # paying during the trial keeps the trial days
    biz.paid_until = start + timedelta(days=30 * pay.months)
    biz.plan = pay.plan
    pay.status, pay.paid_at = "paid", t
    notify.owner_alert(s, biz, f"Payment received: Alaap {pay.plan.title()} plan till {biz.paid_until:%d %b %Y}. "
                               f"Thank you!")
    return pay
