"""Enquiries: answer from the business profile only; offer a callback when unsure."""

from .. import db, notify
from ..scheduling import FMT, BookingError, now
from .base import Context, Skill, Tool, normalise_phone


def request_callback(ctx: Context, reason: str, name: str | None = None, phone: str | None = None) -> dict:
    p = normalise_phone(phone) or normalise_phone(ctx.caller_phone)
    if not p:
        raise BookingError("Need a 10-digit mobile number for the callback. Ask for it.")
    with db.connect(ctx.db_path) as conn:
        conn.execute(
            "INSERT INTO callback (business_id, name, phone, reason, conversation_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (ctx.business_id, name, p, reason, ctx.conversation_id, now().strftime(FMT)),
        )
        biz = db.row(conn, "SELECT owner_phone FROM business WHERE id = ?", ctx.business_id)
        notify.queue(conn, ctx.business_id, biz["owner_phone"], "owner_alert",
                     f"Callback wanted: {name or 'customer'} ({p}) asked: {reason}")
    return {"done": "callback_logged", "say": "The owner will call back."}


SKILL = Skill(
    name="Enquiries",
    goal="Answer questions about prices, hours, location, services and staff.",
    fields=["the question"],
    rules=[
        "Answer only from the business profile. If the answer is not there, say you are not sure and "
        "offer a callback from the owner (request_callback). Never guess prices, offers or availability.",
    ],
    tools=[
        Tool("request_callback", "Ask the owner to call the customer back about something Alaap can't answer.",
             {"reason": {"type": "string", "description": "What the customer wants, in English"},
              "name": {"type": "string"},
              "phone": {"type": "string", "description": "10-digit mobile. Leave out to use the caller's number."}},
             ["reason"], request_callback),
    ],
)
