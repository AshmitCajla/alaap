"""Appointments: find slots, book, reschedule, cancel."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, notify
from ..scheduling import check_booking, free_slots, parse_date, parse_dt
from ..timeutil import FMT, speakable
from .base import (READBACK_NEXT, Context, Skill, Tool, ToolError, business, phone_or_caller, stash,
                   upsert_customer, new_ref)


def _owned(s: Session, ctx: Context, ref: str, phone: str | None) -> models.Appointment:
    p = phone_or_caller(ctx, phone)
    appt = s.scalar(select(models.Appointment).where(models.Appointment.ref == str(ref).strip(),
                                                     models.Appointment.business_id == ctx.business_id))
    if not appt or (appt.customer.phone != p and not ctx.is_owner):
        raise ToolError(f"No booking {ref} found for that phone number. Use find_my_appointments.")
    if appt.status != "booked":
        raise ToolError(f"Booking {ref} is already {appt.status}.")
    return appt


def find_free_slots(ctx, s, service_id, date, staff_id=None, after=None, before=None):
    return free_slots(s, business(s, ctx), service_id, parse_date(date), staff_id, after, before)


def find_my_appointments(ctx, s, phone=None):
    p = phone_or_caller(ctx, phone)
    rows = s.scalars(select(models.Appointment).join(models.Customer)
                     .where(models.Appointment.business_id == ctx.business_id, models.Customer.phone == p,
                            models.Appointment.status == "booked", models.Appointment.start_at >= ctx.now())
                     .order_by(models.Appointment.start_at))
    return {"phone": p, "upcoming": [{"ref": a.ref, "start": a.start_at.strftime(FMT), "service": a.service.name,
                                      "staff": a.staff.name} for a in rows]}


def prepare_booking(ctx, s, customer_name, service_id, start, customer_phone=None, staff_id=None):
    phone = phone_or_caller(ctx, customer_phone)
    if not str(customer_name or "").strip():
        raise ToolError("Need the customer's name.")
    biz = business(s, ctx)
    at = parse_dt(start)
    try:
        svc, person, _ = check_booking(s, biz, service_id, staff_id, at)
    except ToolError as e:
        # Offer the nearest free times in the same breath, like a receptionist would.
        if "not free" in str(e) or "too soon" in str(e) or "outside opening" in str(e):
            near = free_slots(s, biz, service_id, at.date(), staff_id, limit=40)["slots"]
            near.sort(key=lambda x: abs((parse_dt(x["start"]) - at).total_seconds()))
            if near:
                raise ToolError(f"{e} Nearest free times that day: "
                                + ", ".join(x["start"][11:] for x in sorted(near[:3], key=lambda x: x["start"])))
        raise
    action_id = stash(ctx, "book", {"name": customer_name.strip(), "phone": phone, "service_id": svc.id,
                                     "staff_id": person.id, "start": at.strftime(FMT)})
    return {"action_id": action_id,
            "read_back": f"{svc.name} with {person.name}, {speakable(at)}, Rs {svc.price_inr}, "
                         f"for {customer_name.strip()}, mobile ending {phone[-4:]}",
            "next": READBACK_NEXT}


def prepare_reschedule(ctx, s, appointment_ref, new_start, phone=None, staff_id=None):
    appt = _owned(s, ctx, appointment_ref, phone)
    at = parse_dt(new_start)
    _, person, _ = check_booking(s, business(s, ctx), appt.service_id, staff_id, at, ignore=appt.id)
    action_id = stash(ctx, "reschedule", {"appointment_id": appt.id, "staff_id": person.id, "start": at.strftime(FMT)})
    return {"action_id": action_id,
            "read_back": f"Move {appt.service.name} (ref {appt.ref}) from {speakable(appt.start_at)} "
                         f"to {speakable(at)} with {person.name}",
            "next": READBACK_NEXT}


def prepare_cancellation(ctx, s, appointment_ref, phone=None):
    appt = _owned(s, ctx, appointment_ref, phone)
    action_id = stash(ctx, "cancel_appointment", {"appointment_id": appt.id})
    return {"action_id": action_id,
            "read_back": f"Cancel {appt.service.name} with {appt.staff.name} on {speakable(appt.start_at)} "
                         f"(ref {appt.ref})",
            "next": READBACK_NEXT}


# ---------- executors (run by confirm_action) ----------

def do_book(ctx: Context, s: Session, a: dict) -> dict:
    biz = business(s, ctx)
    at = parse_dt(a["start"])
    # Check again: the slot may have gone while the customer was deciding.
    svc, person, end = check_booking(s, biz, a["service_id"], a["staff_id"], at)
    cust = upsert_customer(s, ctx, a["name"], a["phone"])
    stamp = ctx.now()
    appt = models.Appointment(ref=new_ref(s, models.Appointment), business_id=biz.id, customer_id=cust.id,
                              service_id=svc.id, staff_id=person.id, start_at=at, end_at=end, channel=ctx.channel,
                              conversation_id=ctx.conversation_id, created_at=stamp, updated_at=stamp)
    s.add(appt)
    s.flush()
    notify.appointment_messages(s, biz, appt, "confirmation")
    ctx.outcome = "booked"
    return {"done": "booked", "ref": appt.ref,
            "say": f"Booked. Reference number {appt.ref}. A WhatsApp confirmation is on its way."}


def do_reschedule(ctx: Context, s: Session, a: dict) -> dict:
    biz = business(s, ctx)
    appt = s.get(models.Appointment, a["appointment_id"])
    at = parse_dt(a["start"])
    _, person, end = check_booking(s, biz, appt.service_id, a["staff_id"], at, ignore=appt.id)
    appt.start_at, appt.end_at, appt.staff_id, appt.updated_at = at, end, person.id, ctx.now()
    s.flush()
    s.refresh(appt)
    notify.cancel_reminders(s, appt.id)
    notify.appointment_messages(s, biz, appt, "change")
    ctx.outcome = "rescheduled"
    return {"done": "rescheduled", "ref": appt.ref, "say": "Moved. A WhatsApp with the new time is on its way."}


def do_cancel(ctx: Context, s: Session, a: dict) -> dict:
    biz = business(s, ctx)
    appt = s.get(models.Appointment, a["appointment_id"])
    appt.status, appt.updated_at = "cancelled", ctx.now()
    notify.cancel_reminders(s, appt.id)
    notify.queue(s, biz, appt.customer.phone, "cancellation",
                 f"Your booking {appt.ref} at {biz.name} is cancelled.", appointment_id=appt.id)
    ctx.outcome = "cancelled"
    return {"done": "cancelled", "ref": appt.ref, "say": "Cancelled."}


def profile(biz: models.Business) -> str:
    lines = ["Services (id | name | minutes | price):"]
    for sv in biz.services:
        if sv.active:
            note = f" | note: {sv.notes}" if sv.notes else ""
            lines.append(f"  {sv.id} | {sv.name} | {sv.duration_min} min | Rs {sv.price_inr}{note}")
    lines.append("Staff (id | name | services):")
    for p in biz.staff:
        if p.active:
            lines.append(f"  {p.id} | {p.name} | {', '.join(x.name for x in p.services)}")
    return "\n".join(lines)


_phone = {"type": "string", "description": "10-digit mobile. Leave out to use the caller's number."}
_ref = {"type": "string", "description": "The 4-digit booking reference"}

SKILL = Skill(
    key="appointments",
    name="Appointments",
    goal="Book, reschedule and cancel appointments.",
    fields=["customer name", "mobile (caller ID if known)", "service", "staff (optional)", "date and time"],
    rules=[
        "Turn relative dates like 'kal', 'parson', 'agle Saturday' into YYYY-MM-DD using today's date.",
        "Use the Free time section to suggest times without a tool call; use find_free_slots only for days not "
        "listed there. If the caller already named a time, go straight to prepare_booking (it checks the slot "
        "and suggests the nearest free times if it's taken).",
        "If the business is closed that day, say so and offer the next open day.",
        "To change data: call prepare_booking / prepare_reschedule / prepare_cancellation, read back the "
        "read_back, wait for a clear yes, then call confirm_action.",
        "To reschedule or cancel, find the booking with find_my_appointments first.",
        "Never say a booking exists unless confirm_action returned done.",
    ],
    tools=[
        Tool("find_free_slots", "Free start times for a service on a date, with which staff are free.",
             {"service_id": {"type": "integer"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
              "staff_id": {"type": "integer", "description": "Only this staff member"},
              "after": {"type": "string", "description": "HH:MM earliest start"},
              "before": {"type": "string", "description": "HH:MM latest start"}},
             ["service_id", "date"], find_free_slots),
        Tool("find_my_appointments", "Upcoming bookings for a mobile number.", {"phone": _phone}, [],
             find_my_appointments),
        Tool("prepare_booking", "Check a new booking and get the read-back. Saves nothing.",
             {"customer_name": {"type": "string"}, "customer_phone": _phone, "service_id": {"type": "integer"},
              "staff_id": {"type": "integer", "description": "Leave out for any free staff"},
              "start": {"type": "string", "description": "YYYY-MM-DD HH:MM (24-hour)"}},
             ["customer_name", "service_id", "start"], prepare_booking),
        Tool("prepare_reschedule", "Check moving a booking and get the read-back. Saves nothing.",
             {"appointment_ref": _ref, "new_start": {"type": "string", "description": "YYYY-MM-DD HH:MM"},
              "phone": _phone, "staff_id": {"type": "integer"}},
             ["appointment_ref", "new_start"], prepare_reschedule),
        Tool("prepare_cancellation", "Check cancelling a booking and get the read-back. Saves nothing.",
             {"appointment_ref": _ref, "phone": _phone}, ["appointment_ref"], prepare_cancellation),
    ],
    actions={"book": do_book, "reschedule": do_reschedule, "cancel_appointment": do_cancel},
    profile=profile,
)
