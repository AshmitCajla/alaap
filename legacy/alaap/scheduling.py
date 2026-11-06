"""Business profile, free slots and booking validation. No LLM in here:
this is the code that decides what is true, so the engine can't invent it."""

import sqlite3
from datetime import date, datetime, timedelta

from . import config, db

FMT = "%Y-%m-%d %H:%M"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class BookingError(ValueError):
    """A booking request that breaks a rule. The message is shown to the model."""


def now() -> datetime:
    return datetime.now(config.TZ).replace(tzinfo=None, second=0, microsecond=0)


def parse_dt(value: str) -> datetime:
    try:
        return datetime.strptime(value.strip(), FMT)
    except ValueError:
        raise BookingError(f"Time '{value}' must look like YYYY-MM-DD HH:MM (24-hour).")


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise BookingError(f"Date '{value}' must look like YYYY-MM-DD.")


# ---------- profile ----------

def profile(conn: sqlite3.Connection, business_id: int) -> dict:
    biz = db.row(conn, "SELECT * FROM business WHERE id = ?", business_id)
    if not biz:
        raise KeyError(f"No business {business_id}")
    hours = {r["weekday"]: (r["opens"], r["closes"]) for r in db.rows(
        conn, "SELECT * FROM business_hours WHERE business_id = ?", business_id)}
    services = db.rows(conn, "SELECT * FROM service WHERE business_id = ? ORDER BY id", business_id)
    staff = db.rows(conn, "SELECT * FROM staff WHERE business_id = ? ORDER BY id", business_id)
    for s in staff:
        s["service_ids"] = [r["service_id"] for r in db.rows(
            conn, "SELECT service_id FROM staff_service WHERE staff_id = ?", s["id"])]
    faqs = db.rows(conn, "SELECT question, answer FROM faq WHERE business_id = ?", business_id)
    return {**biz, "hours": hours, "services": services, "staff": staff, "faqs": faqs}


def profile_text(p: dict) -> str:
    """The profile as plain text for the system prompt. Alaap answers only from this."""
    lines = [
        f"Name: {p['name']} ({p['kind']})",
        f"Address: {p['address']}, {p['city']}",
        f"Phone: {p['phone']}",
        f"About: {p['about']}",
        "Opening hours:",
    ]
    for d, day in enumerate(WEEKDAYS):
        if d in p["hours"]:
            o, c = p["hours"][d]
            lines.append(f"  {day}: {o}-{c}")
        else:
            lines.append(f"  {day}: closed")
    names = {s["id"]: s["name"] for s in p["services"]}
    lines.append("Services (id | name | minutes | price):")
    for s in p["services"]:
        note = f" | note: {s['notes']}" if s["notes"] else ""
        lines.append(f"  {s['id']} | {s['name']} | {s['duration_min']} min | Rs {s['price_inr']}{note}")
    lines.append("Staff (id | name | services):")
    for s in p["staff"]:
        lines.append(f"  {s['id']} | {s['name']} | {', '.join(names[i] for i in s['service_ids'])}")
    if p["faqs"]:
        lines.append("Other facts:")
        lines.extend(f"  {f['question']}: {f['answer']}" for f in p["faqs"])
    return "\n".join(lines)


def _service(conn, business_id: int, service_id: int) -> dict:
    s = db.row(conn, "SELECT * FROM service WHERE id = ? AND business_id = ?", service_id, business_id)
    if not s:
        raise BookingError(f"There is no service with id {service_id}. Use an id from the profile.")
    return s


def _staff_for(conn, business_id: int, service_id: int) -> list[dict]:
    return db.rows(
        conn,
        "SELECT st.* FROM staff st JOIN staff_service ss ON ss.staff_id = st.id"
        " WHERE st.business_id = ? AND ss.service_id = ? ORDER BY st.id",
        business_id, service_id,
    )


def _hours(conn, business_id: int, day: date) -> tuple[datetime, datetime] | None:
    r = db.row(conn, "SELECT opens, closes FROM business_hours WHERE business_id = ? AND weekday = ?",
               business_id, day.weekday())
    if not r:
        return None
    return (datetime.combine(day, datetime.strptime(r["opens"], "%H:%M").time()),
            datetime.combine(day, datetime.strptime(r["closes"], "%H:%M").time()))


def _busy(conn, staff_id: int, start: datetime, end: datetime, ignore_appt: int | None = None) -> bool:
    clash = db.row(
        conn,
        "SELECT id FROM appointment WHERE staff_id = ? AND status = 'booked'"
        " AND start_at < ? AND end_at > ? AND id IS NOT ?",
        staff_id, end.strftime(FMT), start.strftime(FMT), ignore_appt,
    )
    return clash is not None


# ---------- slots ----------

def free_slots(conn, business_id: int, service_id: int, day: date, staff_id: int | None = None,
               after: str | None = None, before: str | None = None, limit: int = 8,
               ignore_appt: int | None = None, current: datetime | None = None) -> dict:
    """Free start times for a service on a day, each with the staff who are free."""
    service = _service(conn, business_id, service_id)
    hours = _hours(conn, business_id, day)
    if not hours:
        return {"date": day.isoformat(), "weekday": WEEKDAYS[day.weekday()], "closed": True, "slots": []}
    staff = _staff_for(conn, business_id, service_id)
    if staff_id is not None:
        staff = [s for s in staff if s["id"] == staff_id]
        if not staff:
            raise BookingError(f"Staff {staff_id} does not do {service['name']}.")
    opens, closes = hours
    length = timedelta(minutes=service["duration_min"])
    earliest = (current or now()) + timedelta(minutes=config.MIN_LEAD_MINUTES)
    t = opens
    if after:
        t = max(t, datetime.combine(day, datetime.strptime(after, "%H:%M").time()))
    last_start = closes - length
    if before:
        last_start = min(last_start, datetime.combine(day, datetime.strptime(before, "%H:%M").time()))
    slots = []
    step = timedelta(minutes=config.SLOT_STEP_MINUTES)
    while t <= last_start and len(slots) < limit:
        if t >= earliest:
            free = [s["name"] for s in staff if not _busy(conn, s["id"], t, t + length, ignore_appt)]
            if free:
                slots.append({"start": t.strftime(FMT), "staff_free": free})
        t += step
    return {"date": day.isoformat(), "weekday": WEEKDAYS[day.weekday()], "closed": False,
            "service": service["name"], "minutes": service["duration_min"], "slots": slots}


def check_booking(conn, business_id: int, service_id: int, staff_id: int | None, start: datetime,
                  ignore_appt: int | None = None, current: datetime | None = None) -> dict:
    """Validate a booking and pick a free staff member if none was asked for.
    Returns {service, staff, start, end}. Raises BookingError with a reason."""
    service = _service(conn, business_id, service_id)
    if start < (current or now()) + timedelta(minutes=config.MIN_LEAD_MINUTES):
        raise BookingError("That time has passed or is too soon. Offer a later slot.")
    hours = _hours(conn, business_id, start.date())
    if not hours:
        raise BookingError(f"The business is closed on {WEEKDAYS[start.weekday()]}.")
    end = start + timedelta(minutes=service["duration_min"])
    if start < hours[0] or end > hours[1]:
        raise BookingError(
            f"{service['name']} at {start:%H:%M} would run outside opening hours "
            f"({hours[0]:%H:%M}-{hours[1]:%H:%M}).")
    candidates = _staff_for(conn, business_id, service_id)
    if staff_id is not None:
        candidates = [s for s in candidates if s["id"] == staff_id]
        if not candidates:
            raise BookingError(f"Staff {staff_id} does not do {service['name']}.")
    for s in candidates:
        if not _busy(conn, s["id"], start, end, ignore_appt):
            return {"service": service, "staff": s, "start": start, "end": end}
    who = candidates[0]["name"] if staff_id is not None else "No one"
    raise BookingError(f"{who} is not free at {start:%Y-%m-%d %H:%M}. Check free slots and offer another time.")
