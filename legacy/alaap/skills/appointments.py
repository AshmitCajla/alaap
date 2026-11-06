"""Appointments: find slots, book, reschedule and cancel.

Every change is two steps: prepare_* validates and returns a read-back,
confirm_action writes it, and only after the customer has replied."""

import random
from datetime import datetime

from .. import db, notify
from ..scheduling import FMT, BookingError, check_booking, free_slots, now, parse_date, parse_dt
from .base import Context, Skill, Tool, normalise_phone


def _biz(conn, ctx: Context) -> dict:
    return db.row(conn, "SELECT * FROM business WHERE id = ?", ctx.business_id)


def _new_ref(conn) -> str:
    while True:
        ref = str(random.randint(1000, 9999))
        if not db.row(conn, "SELECT 1 FROM appointment WHERE ref = ?", ref):
            return ref


def _speakable(start: datetime) -> str:
    return start.strftime("%A %d %B at %I:%M %p")


def _phone_or_caller(ctx: Context, phone: str | None) -> str:
    p = normalise_phone(phone) or normalise_phone(ctx.caller_phone)
    if not p:
        raise BookingError("Need the customer's 10-digit mobile number. Ask for it.")
    return p


def _owned_appointment(conn, ctx: Context, ref: str, phone: str | None) -> dict:
    p = _phone_or_caller(ctx, phone)
    appt = db.row(
        conn,
        "SELECT a.*, c.name AS customer, c.phone, s.name AS service, st.name AS staff"
        " FROM appointment a JOIN customer c ON c.id = a.customer_id"
        " JOIN service s ON s.id = a.service_id JOIN staff st ON st.id = a.staff_id"
        " WHERE a.ref = ? AND a.business_id = ?",
        str(ref).strip(), ctx.business_id,
    )
    if not appt or appt["phone"] != p:
        raise BookingError(f"No booking {ref} found for that phone number. Use find_my_appointments.")
    if appt["status"] != "booked":
        raise BookingError(f"Booking {ref} is already {appt['status']}.")
    return appt


def _stash(ctx: Context, action: dict) -> str:
    action_id = f"A{ctx.next_action}"
    ctx.next_action += 1
    action["user_turn"] = ctx.user_turn
    ctx.pending = {action_id: action}  # only the latest proposal can be confirmed
    return action_id


# ---------- tools ----------

def find_free_slots(ctx: Context, service_id: int, date: str, staff_id: int | None = None,
                    after: str | None = None, before: str | None = None) -> dict:
    with db.connect(ctx.db_path) as conn:
        return free_slots(conn, ctx.business_id, service_id, parse_date(date), staff_id, after, before)


def find_my_appointments(ctx: Context, phone: str | None = None) -> dict:
    p = _phone_or_caller(ctx, phone)
    with db.connect(ctx.db_path) as conn:
        found = db.rows(
            conn,
            "SELECT a.ref, a.start_at, s.name AS service, st.name AS staff"
            " FROM appointment a JOIN customer c ON c.id = a.customer_id"
            " JOIN service s ON s.id = a.service_id JOIN staff st ON st.id = a.staff_id"
            " WHERE a.business_id = ? AND c.phone = ? AND a.status = 'booked' AND a.start_at >= ?"
            " ORDER BY a.start_at",
            ctx.business_id, p, now().strftime(FMT),
        )
    return {"phone": p, "upcoming": found}


def prepare_booking(ctx: Context, customer_name: str, service_id: int, start: str,
                    customer_phone: str | None = None, staff_id: int | None = None) -> dict:
    phone = _phone_or_caller(ctx, customer_phone)
    if not customer_name.strip():
        raise BookingError("Need the customer's name.")
    with db.connect(ctx.db_path) as conn:
        ok = check_booking(conn, ctx.business_id, service_id, staff_id, parse_dt(start))
    action_id = _stash(ctx, {
        "kind": "book", "customer_name": customer_name.strip(), "phone": phone,
        "service_id": service_id, "staff_id": ok["staff"]["id"], "start": ok["start"].strftime(FMT),
    })
    return {
        "action_id": action_id,
        "read_back": f"{ok['service']['name']} with {ok['staff']['name']}, {_speakable(ok['start'])}, "
                     f"Rs {ok['service']['price_inr']}, for {customer_name.strip()}, mobile ending {phone[-4:]}",
        "next": "Read this back in the customer's language and ask them to confirm. "
                "Call confirm_action only after they say yes.",
    }


def prepare_reschedule(ctx: Context, appointment_ref: str, new_start: str,
                       phone: str | None = None, staff_id: int | None = None) -> dict:
    with db.connect(ctx.db_path) as conn:
        appt = _owned_appointment(conn, ctx, appointment_ref, phone)
        ok = check_booking(conn, ctx.business_id, appt["service_id"], staff_id,
                           parse_dt(new_start), ignore_appt=appt["id"])
    action_id = _stash(ctx, {
        "kind": "reschedule", "appointment_id": appt["id"], "staff_id": ok["staff"]["id"],
        "start": ok["start"].strftime(FMT),
    })
    old = datetime.strptime(appt["start_at"], FMT)
    return {
        "action_id": action_id,
        "read_back": f"Move {appt['service']} (ref {appt['ref']}) from {_speakable(old)} "
                     f"to {_speakable(ok['start'])} with {ok['staff']['name']}",
        "next": "Read this back and ask the customer to confirm. Call confirm_action only after they say yes.",
    }


def prepare_cancellation(ctx: Context, appointment_ref: str, phone: str | None = None) -> dict:
    with db.connect(ctx.db_path) as conn:
        appt = _owned_appointment(conn, ctx, appointment_ref, phone)
    action_id = _stash(ctx, {"kind": "cancel", "appointment_id": appt["id"]})
    return {
        "action_id": action_id,
        "read_back": f"Cancel {appt['service']} with {appt['staff']} on "
                     f"{_speakable(datetime.strptime(appt['start_at'], FMT))} (ref {appt['ref']})",
        "next": "Read this back and ask the customer to confirm. Call confirm_action only after they say yes.",
    }


def confirm_action(ctx: Context, action_id: str) -> dict:
    action = ctx.pending.get(action_id)
    if not action:
        raise BookingError("Unknown or expired action_id. Prepare the action again.")
    if ctx.user_turn <= action["user_turn"]:
        raise BookingError("The customer has not replied to the read-back yet. "
                           "Read it back and wait for their yes before confirming.")
    with db.connect(ctx.db_path) as conn:
        biz = _biz(conn, ctx)
        stamp = now().strftime(FMT)
        if action["kind"] == "book":
            # Re-check: the slot may have gone while the customer was deciding.
            ok = check_booking(conn, ctx.business_id, action["service_id"], action["staff_id"],
                               parse_dt(action["start"]))
            conn.execute(
                "INSERT INTO customer (business_id, name, phone) VALUES (?, ?, ?)"
                " ON CONFLICT (business_id, phone) DO UPDATE SET name = excluded.name",
                (ctx.business_id, action["customer_name"], action["phone"]),
            )
            cust = db.row(conn, "SELECT id FROM customer WHERE business_id = ? AND phone = ?",
                          ctx.business_id, action["phone"])
            ref = _new_ref(conn)
            cur = conn.execute(
                "INSERT INTO appointment (ref, business_id, customer_id, service_id, staff_id, start_at, end_at,"
                " channel, conversation_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ref, ctx.business_id, cust["id"], action["service_id"], ok["staff"]["id"],
                 ok["start"].strftime(FMT), ok["end"].strftime(FMT), ctx.channel, ctx.conversation_id,
                 stamp, stamp),
            )
            appt = {"id": cur.lastrowid, "ref": ref, "start_at": ok["start"].strftime(FMT), "phone": action["phone"]}
            notify.booking_messages(conn, biz, appt, ok["service"]["name"], ok["staff"]["name"])
            result = {"done": "booked", "ref": ref,
                      "say": f"Booked. Reference number {ref}. A WhatsApp confirmation is on its way."}
        elif action["kind"] == "reschedule":
            appt = db.row(conn, "SELECT a.*, c.phone FROM appointment a JOIN customer c ON c.id = a.customer_id"
                                " WHERE a.id = ?", action["appointment_id"])
            ok = check_booking(conn, ctx.business_id, appt["service_id"], action["staff_id"],
                               parse_dt(action["start"]), ignore_appt=appt["id"])
            conn.execute(
                "UPDATE appointment SET start_at = ?, end_at = ?, staff_id = ?, updated_at = ? WHERE id = ?",
                (ok["start"].strftime(FMT), ok["end"].strftime(FMT), ok["staff"]["id"], stamp, appt["id"]),
            )
            notify.cancel_reminders(conn, appt["id"])
            appt.update(start_at=ok["start"].strftime(FMT))
            notify.booking_messages(conn, biz, appt, ok["service"]["name"], ok["staff"]["name"], kind="change")
            result = {"done": "rescheduled", "ref": appt["ref"],
                      "say": "Moved. A WhatsApp with the new time is on its way."}
        else:
            appt = db.row(conn, "SELECT a.*, c.phone FROM appointment a JOIN customer c ON c.id = a.customer_id"
                                " WHERE a.id = ?", action["appointment_id"])
            conn.execute("UPDATE appointment SET status = 'cancelled', updated_at = ? WHERE id = ?",
                         (stamp, appt["id"]))
            notify.cancel_reminders(conn, appt["id"])
            notify.queue(conn, ctx.business_id, appt["phone"], "cancellation",
                         f"Your booking {appt['ref']} at {biz['name']} is cancelled.", appointment_id=appt["id"])
            result = {"done": "cancelled", "ref": appt["ref"], "say": "Cancelled."}
    ctx.pending.clear()
    return result


# ---------- skill ----------

_phone = {"type": "string", "description": "10-digit mobile. Leave out to use the caller's number."}
_ref = {"type": "string", "description": "The 4-digit booking reference"}

SKILL = Skill(
    name="Appointments",
    goal="Book, reschedule and cancel appointments.",
    fields=["customer name", "mobile number (use caller ID if known)", "service", "staff (optional)",
            "date and time"],
    rules=[
        "Turn relative dates like 'kal', 'parson', 'next Saturday' into YYYY-MM-DD using today's date.",
        "Call find_free_slots before proposing a time. Offer at most two or three options.",
        "If the business is closed that day, say so and offer the next open day.",
        "To change data: call prepare_booking / prepare_reschedule / prepare_cancellation, read the "
        "read_back to the customer, and wait. Call confirm_action only after the customer clearly says yes.",
        "If a tool returns an error, explain it simply and offer an alternative. Never claim a booking "
        "exists unless confirm_action returned done.",
        "To reschedule or cancel, find the booking with find_my_appointments first.",
    ],
    tools=[
        Tool("find_free_slots", "Free start times for a service on a date, with which staff are free.",
             {"service_id": {"type": "integer"},
              "date": {"type": "string", "description": "YYYY-MM-DD"},
              "staff_id": {"type": "integer", "description": "Only this staff member"},
              "after": {"type": "string", "description": "HH:MM, earliest start wanted"},
              "before": {"type": "string", "description": "HH:MM, latest start wanted"}},
             ["service_id", "date"], find_free_slots),
        Tool("find_my_appointments", "Upcoming bookings for a mobile number.",
             {"phone": _phone}, [], find_my_appointments),
        Tool("prepare_booking", "Check a new booking and get the read-back. Does not save anything.",
             {"customer_name": {"type": "string"}, "customer_phone": _phone,
              "service_id": {"type": "integer"},
              "staff_id": {"type": "integer", "description": "Leave out for any free staff"},
              "start": {"type": "string", "description": "YYYY-MM-DD HH:MM, 24-hour"}},
             ["customer_name", "service_id", "start"], prepare_booking),
        Tool("prepare_reschedule", "Check moving a booking to a new time and get the read-back. Does not save.",
             {"appointment_ref": _ref, "new_start": {"type": "string", "description": "YYYY-MM-DD HH:MM"},
              "phone": _phone, "staff_id": {"type": "integer"}},
             ["appointment_ref", "new_start"], prepare_reschedule),
        Tool("prepare_cancellation", "Check cancelling a booking and get the read-back. Does not save.",
             {"appointment_ref": _ref, "phone": _phone},
             ["appointment_ref"], prepare_cancellation),
        Tool("confirm_action", "Save the prepared action. Only after the customer said yes to the read-back.",
             {"action_id": {"type": "string"}}, ["action_id"], confirm_action),
    ],
)
