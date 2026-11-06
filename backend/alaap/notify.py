"""Queue outgoing messages. jobs.py sends them (WhatsApp Cloud API / Exotel)."""

from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from . import config, models
from .timeutil import now


def queue(s: Session, biz: models.Business, to_phone: str | None, kind: str, body: str, *,
          channel: str = "whatsapp", send_after: datetime | None = None, appointment_id: int | None = None,
          order_id: int | None = None, media_path: str | None = None) -> models.Outbox | None:
    if not to_phone:
        return None
    item = models.Outbox(business_id=biz.id, to_phone=to_phone, kind=kind, body=body, channel=channel,
                         send_after=send_after or now(biz.timezone), appointment_id=appointment_id,
                         order_id=order_id, media_path=media_path)
    s.add(item)
    s.flush()
    return item


def owner_alert(s: Session, biz: models.Business, body: str) -> None:
    queue(s, biz, biz.owner_phone, "owner_alert", body)


def cancel_reminders(s: Session, appointment_id: int) -> None:
    s.execute(update(models.Outbox)
              .where(models.Outbox.appointment_id == appointment_id, models.Outbox.kind == "reminder",
                     models.Outbox.status == "queued")
              .values(status="cancelled"))


def appointment_messages(s: Session, biz: models.Business, appt: models.Appointment, kind: str) -> None:
    """Confirmation (or change notice) now, and a reminder before the appointment."""
    when = appt.start_at.strftime("%a %d %b, %I:%M %p")
    head = {"confirmation": "Booking confirmed", "change": "Booking changed"}[kind]
    queue(s, biz, appt.customer.phone, kind,
          f"{head} at {biz.name}: {appt.service.name} with {appt.staff.name}, {when}. Ref {appt.ref}. "
          f"Reply here to change or cancel.", appointment_id=appt.id)
    remind_at = appt.start_at - timedelta(hours=config.REMINDER_HOURS)
    if remind_at > now(biz.timezone):
        queue(s, biz, appt.customer.phone, "reminder",
              f"Reminder: {appt.service.name} at {biz.name} today at {appt.start_at:%I:%M %p}. Ref {appt.ref}.",
              send_after=remind_at, appointment_id=appt.id)
