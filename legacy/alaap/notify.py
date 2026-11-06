"""WhatsApp messages. The MVP queues them in the outbox table and the owner
dashboard shows them; sending through the WhatsApp Cloud API is Phase 1."""

from datetime import datetime, timedelta

from . import config
from .scheduling import FMT, now


def queue(conn, business_id: int, to_phone: str, kind: str, body: str,
          send_after: datetime | None = None, appointment_id: int | None = None) -> None:
    conn.execute(
        "INSERT INTO outbox (business_id, to_phone, kind, body, send_after, appointment_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (business_id, to_phone, kind, body, (send_after or now()).strftime(FMT),
         appointment_id, now().strftime(FMT)),
    )


def cancel_reminders(conn, appointment_id: int) -> None:
    conn.execute(
        "UPDATE outbox SET status = 'cancelled' WHERE appointment_id = ? AND kind = 'reminder' AND status = 'queued'",
        (appointment_id,),
    )


def booking_messages(conn, biz: dict, appt: dict, service: str, staff: str, kind: str = "confirmation") -> None:
    """Confirmation now, reminder REMINDER_HOURS before the start (if that is still ahead)."""
    start = datetime.strptime(appt["start_at"], FMT)
    when = start.strftime("%a %d %b, %I:%M %p")
    head = "Booking confirmed" if kind == "confirmation" else "Booking changed"
    queue(conn, biz["id"], appt["phone"], kind,
          f"{head} at {biz['name']}: {service} with {staff}, {when}. Ref {appt['ref']}. "
          f"To change it, call or message us.", appointment_id=appt["id"])
    remind_at = start - timedelta(hours=config.REMINDER_HOURS)
    if remind_at > now():
        queue(conn, biz["id"], appt["phone"], "reminder",
              f"Reminder: {service} at {biz['name']} today at {start:%I:%M %p}. Ref {appt['ref']}.",
              send_after=remind_at, appointment_id=appt["id"])
