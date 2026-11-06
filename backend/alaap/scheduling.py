"""Opening hours, free slots and booking checks. Plain code, no LLM:
this decides what is true so the model can't invent a slot."""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, models
from .errors import ToolError
from .timeutil import FMT, WEEKDAYS, now


def parse_dt(value: str) -> datetime:
    try:
        return datetime.strptime(str(value).strip(), FMT)
    except ValueError:
        raise ToolError(f"Time '{value}' must look like YYYY-MM-DD HH:MM (24-hour).")


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise ToolError(f"Date '{value}' must look like YYYY-MM-DD.")


def _hm(day: date, hm: str) -> datetime:
    return datetime.combine(day, datetime.strptime(hm, "%H:%M").time())


def hours_on(s: Session, biz: models.Business, day: date) -> tuple[datetime, datetime] | None:
    """Opening and closing time on a day, or None if closed."""
    if s.scalar(select(models.Closure.id).where(models.Closure.business_id == biz.id, models.Closure.day == day)):
        return None
    h = s.get(models.BusinessHours, (biz.id, day.weekday()))
    if not h:
        return None
    return _hm(day, h.opens), _hm(day, h.closes)


def service(s: Session, biz: models.Business, service_id: int) -> models.Service:
    svc = s.get(models.Service, int(service_id))
    if not svc or svc.business_id != biz.id or not svc.active:
        raise ToolError(f"There is no service with id {service_id}. Use an id from the profile.")
    return svc


def staff_for(s: Session, svc: models.Service) -> list[models.Staff]:
    rows = s.scalars(select(models.Staff).join(models.staff_service)
                     .where(models.staff_service.c.service_id == svc.id, models.Staff.active.is_(True))
                     .order_by(models.Staff.id))
    return list(rows)


def busy(s: Session, staff_id: int, start: datetime, end: datetime, ignore: int | None = None) -> bool:
    q = select(models.Appointment.id).where(
        models.Appointment.staff_id == staff_id, models.Appointment.status == "booked",
        models.Appointment.start_at < end, models.Appointment.end_at > start)
    if ignore:
        q = q.where(models.Appointment.id != ignore)
    return s.scalar(q) is not None


def free_slots(s: Session, biz: models.Business, service_id: int, day: date, staff_id: int | None = None,
               after: str | None = None, before: str | None = None, limit: int = 8,
               ignore: int | None = None) -> dict:
    svc = service(s, biz, service_id)
    hours = hours_on(s, biz, day)
    base = {"date": day.isoformat(), "weekday": WEEKDAYS[day.weekday()]}
    if not hours:
        nxt = next_open_day(s, biz, day)
        return {**base, "closed": True, "next_open_day": nxt.isoformat() if nxt else None, "slots": []}
    staff = staff_for(s, svc)
    if staff_id is not None:
        staff = [p for p in staff if p.id == int(staff_id)]
        if not staff:
            raise ToolError(f"Staff {staff_id} does not do {svc.name}.")
    length = timedelta(minutes=svc.duration_min)
    earliest = now(biz.timezone) + timedelta(minutes=config.MIN_LEAD_MINUTES)
    t, last = hours[0], hours[1] - length
    if after:
        t = max(t, _hm(day, after))
    if before:
        last = min(last, _hm(day, before))
    slots, step = [], timedelta(minutes=config.SLOT_STEP_MINUTES)
    while t <= last and len(slots) < limit:
        if t >= earliest:
            free = [p.name for p in staff if not busy(s, p.id, t, t + length, ignore)]
            if free:
                slots.append({"start": t.strftime(FMT), "staff_free": free})
        t += step
    return {**base, "closed": False, "service": svc.name, "minutes": svc.duration_min, "slots": slots}


def next_open_day(s: Session, biz: models.Business, after: date, horizon: int = 14) -> date | None:
    for i in range(1, horizon + 1):
        d = after + timedelta(days=i)
        if hours_on(s, biz, d):
            return d
    return None


def check_booking(s: Session, biz: models.Business, service_id: int, staff_id: int | None, start: datetime,
                  ignore: int | None = None) -> tuple[models.Service, models.Staff, datetime]:
    """Validate a booking; pick a free staff member if none was asked for.
    Returns (service, staff, end). Raises ToolError with the reason."""
    svc = service(s, biz, service_id)
    if start < now(biz.timezone) + timedelta(minutes=config.MIN_LEAD_MINUTES):
        raise ToolError("That time has passed or is too soon. Offer a later slot.")
    hours = hours_on(s, biz, start.date())
    if not hours:
        raise ToolError(f"The business is closed on {WEEKDAYS[start.weekday()]} {start:%d %b}.")
    end = start + timedelta(minutes=svc.duration_min)
    if start < hours[0] or end > hours[1]:
        raise ToolError(f"{svc.name} at {start:%H:%M} would run outside opening hours "
                        f"({hours[0]:%H:%M}-{hours[1]:%H:%M}).")
    candidates = staff_for(s, svc)
    if staff_id is not None:
        candidates = [p for p in candidates if p.id == int(staff_id)]
        if not candidates:
            raise ToolError(f"Staff {staff_id} does not do {svc.name}.")
    for p in candidates:
        if not busy(s, p.id, start, end, ignore):
            return svc, p, end
    who = candidates[0].name if staff_id is not None else "No one"
    raise ToolError(f"{who} is not free at {start:%Y-%m-%d %H:%M}. Check free slots and offer another time.")
