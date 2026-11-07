"""The owner talking to Alaap: "aaj kitne orders aaye?", "kal shop band hai, sab appointments shift karo"."""

from datetime import datetime, timedelta

from sqlalchemy import func, select

from .. import models, notify
from ..scheduling import check_booking, next_open_day, parse_date
from ..timeutil import FMT, WEEKDAYS
from .base import READBACK_NEXT, Skill, Tool, ToolError, business, stash


def _day(ctx, date):
    return parse_date(date) if date else ctx.now().date()


def get_stats(ctx, s, date=None):
    d = _day(ctx, date)
    start, end = datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())
    b = ctx.business_id
    M = models

    def count(model, *where):
        return s.scalar(select(func.count(model.id)).where(model.business_id == b, *where)) or 0

    revenue = s.scalar(select(func.coalesce(func.sum(M.Order.total_inr), 0)).where(
        M.Order.business_id == b, M.Order.created_at >= start, M.Order.created_at < end,
        M.Order.status != "cancelled")) or 0
    return {
        "date": d.isoformat(),
        "appointments_booked_by_alaap": count(M.Appointment, M.Appointment.created_at >= start,
                                              M.Appointment.created_at < end, M.Appointment.status != "cancelled"),
        "appointments_on_this_day": count(M.Appointment, M.Appointment.start_at >= start, M.Appointment.start_at < end,
                                          M.Appointment.status == "booked"),
        "orders": count(M.Order, M.Order.created_at >= start, M.Order.created_at < end, M.Order.status != "cancelled"),
        "order_value_inr": int(revenue),
        "unpaid_upi_orders": count(M.Order, M.Order.payment_status == "pending", M.Order.status != "cancelled"),
        "new_leads": count(M.Lead, M.Lead.created_at >= start, M.Lead.created_at < end),
        "open_callbacks_and_complaints": count(M.Ticket, M.Ticket.status == "open"),
        "conversations": count(M.Conversation, M.Conversation.started_at >= start, M.Conversation.started_at < end,
                               M.Conversation.is_owner.is_(False)),
    }


def list_schedule(ctx, s, date=None):
    d = _day(ctx, date)
    start, end = datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())
    appts = s.scalars(select(models.Appointment).where(
        models.Appointment.business_id == ctx.business_id, models.Appointment.status == "booked",
        models.Appointment.start_at >= start, models.Appointment.start_at < end).order_by(models.Appointment.start_at))
    orders = s.scalars(select(models.Order).where(
        models.Order.business_id == ctx.business_id, models.Order.slot_date == d, models.Order.status != "cancelled"))
    return {"date": d.isoformat(),
            "appointments": [f"{a.start_at:%H:%M} {a.service.name} - {a.customer.name} ({a.staff.name}) ref {a.ref}"
                             for a in appts],
            "deliveries": [f"{o.slot_label} order {o.ref} - {o.customer.name}, Rs {o.total_inr}, {o.status}"
                           for o in orders]}


def list_open_orders(ctx, s):
    rows = s.scalars(select(models.Order).where(
        models.Order.business_id == ctx.business_id,
        models.Order.status.in_(("placed", "preparing", "out_for_delivery"))).order_by(models.Order.slot_date, models.Order.id))
    return {"orders": [{"ref": o.ref, "customer": o.customer.name, "total_inr": o.total_inr, "status": o.status,
                        "payment": o.payment_status, "slot": f"{o.slot_date:%a %d %b} {o.slot_label}",
                        "items": [f"{i.qty} x {i.name}" for i in o.items]} for o in rows]}


def _find_item(s, ctx, name):
    """A service or product by (fuzzy) name."""
    import difflib

    q = str(name).lower().strip()
    items = list(s.scalars(select(models.Service).where(models.Service.business_id == ctx.business_id))) + \
        list(s.scalars(select(models.Product).where(models.Product.business_id == ctx.business_id)))
    best = max(items, key=lambda x: (q in x.name.lower()) + difflib.SequenceMatcher(None, q, x.name.lower()).ratio(),
               default=None)
    if not best or (q not in best.name.lower() and difflib.SequenceMatcher(None, q, best.name.lower()).ratio() < 0.5):
        return None
    return best


def update_item(ctx, s, name, price_inr=None, duration_min=None, available=None):
    """Change a price / duration, or switch an item off and on."""
    item = _find_item(s, ctx, name)
    if not item:
        raise ToolError(f"No service or product like '{name}'. Use add_item to add it.")
    before = item.price_inr
    if price_inr is not None:
        item.price_inr = int(price_inr)
    if duration_min is not None and isinstance(item, models.Service):
        item.duration_min = int(duration_min)
    if available is not None:
        item.active = bool(available)
    if isinstance(item, models.Service) and item.notes == "Sample - edit me":
        item.notes = None
    return {"done": "updated", "item": item.name, "old_price": before, "price": item.price_inr, "active": item.active}


def add_item(ctx, s, name, price_inr, kind="auto", duration_min=None, unit=None):
    biz = business(s, ctx)
    is_service = kind == "service" or (kind == "auto" and "appointments" in biz.skills and "orders" not in biz.skills)
    if is_service:
        sv = models.Service(business_id=biz.id, name=name, price_inr=int(price_inr), duration_min=int(duration_min or 30))
        s.add(sv)
        s.flush()
        for st in biz.staff:
            if st.active:
                st.services.append(sv)
        return {"done": "added service", "name": name, "price": int(price_inr), "minutes": sv.duration_min}
    s.add(models.Product(business_id=biz.id, name=name, price_inr=int(price_inr), unit=unit or "1 pc"))
    return {"done": "added product", "name": name, "price": int(price_inr)}


def remember_fact(ctx, s, topic, fact):
    """Teach Alaap something to tell customers ("parking peeche hai")."""
    f = s.scalar(select(models.Faq).where(models.Faq.business_id == ctx.business_id, models.Faq.question == topic))
    if f:
        f.answer = fact
    else:
        s.add(models.Faq(business_id=ctx.business_id, question=topic, answer=fact))
    return {"done": "remembered", "topic": topic}


def set_hours(ctx, s, weekday, opens=None, closes=None, closed=False):
    w = int(weekday)
    if not 0 <= w <= 6:
        raise ToolError("weekday is 0 (Monday) to 6 (Sunday).")
    h = s.get(models.BusinessHours, (ctx.business_id, w))
    if closed:
        if h:
            s.delete(h)
        return {"done": "closed every week", "weekday": WEEKDAYS[w]}
    if not (opens and closes):
        raise ToolError("Give opens and closes as HH:MM, or closed=true.")
    if h:
        h.opens, h.closes = opens, closes
    else:
        s.add(models.BusinessHours(business_id=ctx.business_id, weekday=w, opens=opens, closes=closes))
    return {"done": "hours set", "weekday": WEEKDAYS[w], "opens": opens, "closes": closes}


ORDER_STATUSES = ("preparing", "out_for_delivery", "delivered", "cancelled")


def update_order_status(ctx, s, order_ref, status, note=None):
    if status not in ORDER_STATUSES:
        raise ToolError(f"status must be one of {', '.join(ORDER_STATUSES)}")
    o = s.scalar(select(models.Order).where(models.Order.business_id == ctx.business_id,
                                            models.Order.ref == str(order_ref).strip()))
    if not o:
        raise ToolError(f"No order {order_ref}.")
    o.status, o.status_note, o.updated_at = status, note, ctx.now()
    biz = business(s, ctx)
    text = {"preparing": "is being packed", "out_for_delivery": "is out for delivery",
            "delivered": "has been delivered. Thank you!", "cancelled": "has been cancelled by the shop"}[status]
    notify.queue(s, biz, o.customer.phone, "order_update",
                 f"Your order {o.ref} from {biz.name} {text}.{' ' + note if note else ''}", order_id=o.id)
    return {"done": "updated", "ref": o.ref, "status": status}


def set_stock(ctx, s, product_id, stock):
    p = s.scalar(select(models.Product).where(models.Product.id == int(product_id)).with_for_update())
    if not p or p.business_id != ctx.business_id:
        raise ToolError(f"No product {product_id}.")
    p.stock = None if stock is None or int(stock) < 0 else int(stock)
    return {"done": "updated", "product": p.name, "stock": p.stock}


def prepare_close_day(ctx, s, date, note=None, move_appointments_to=None):
    biz = business(s, ctx)
    d = parse_date(date)
    target = parse_date(move_appointments_to) if move_appointments_to else next_open_day(s, biz, d)
    start, end = datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())
    appts = s.scalars(select(models.Appointment).where(
        models.Appointment.business_id == biz.id, models.Appointment.status == "booked",
        models.Appointment.start_at >= start, models.Appointment.start_at < end)).all()
    action_id = stash(ctx, "close_day", {"date": d.isoformat(), "note": note,
                                          "target": target.isoformat() if target else None})
    return {"action_id": action_id,
            "read_back": f"Close on {WEEKDAYS[d.weekday()]} {d:%d %b}. {len(appts)} appointment(s) that day will "
                         + (f"move to {WEEKDAYS[target.weekday()]} {target:%d %b} at the same time where free "
                            f"(others cancelled and asked to rebook); customers get a WhatsApp."
                            if target else "be cancelled; customers get a WhatsApp."),
            "next": READBACK_NEXT}


def do_close_day(ctx, s, a):
    biz = business(s, ctx)
    d = parse_date(a["date"])
    s.add(models.Closure(business_id=biz.id, day=d, note=a.get("note")))
    s.flush()
    target = parse_date(a["target"]) if a.get("target") else None
    start, end = datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())
    appts = s.scalars(select(models.Appointment).where(
        models.Appointment.business_id == biz.id, models.Appointment.status == "booked",
        models.Appointment.start_at >= start, models.Appointment.start_at < end)).all()
    moved = cancelled = 0
    for appt in appts:
        notify.cancel_reminders(s, appt.id)
        new_start = datetime.combine(target, appt.start_at.time()) if target else None
        try:
            if not new_start:
                raise ToolError("no target")
            _, person, new_end = check_booking(s, biz, appt.service_id, None, new_start, ignore=appt.id)
            appt.start_at, appt.end_at, appt.staff_id, appt.updated_at = new_start, new_end, person.id, ctx.now()
            s.flush()
            s.refresh(appt)
            notify.appointment_messages(s, biz, appt, "change")
            moved += 1
        except ToolError:
            appt.status, appt.updated_at = "cancelled", ctx.now()
            notify.queue(s, biz, appt.customer.phone, "cancellation",
                         f"Sorry, {biz.name} is closed on {d:%a %d %b}, so booking {appt.ref} is cancelled. "
                         f"Reply here or call to pick a new time.", appointment_id=appt.id)
            cancelled += 1
    return {"done": "closed", "moved": moved, "cancelled": cancelled}


SKILL = Skill(
    key="owner",
    name="Owner assistant",
    goal="You are talking to the business OWNER, not a customer. Help them run the day.",
    fields=[],
    rules=[
        "Answer questions about today's numbers and schedule with get_stats / list_schedule.",
        "For 'shop band hai' / closing a day: prepare_close_day, read back, confirm_action after yes.",
        "When the owner tells you a new price, new item, new timing or something to tell customers, update it right "
        "away with update_item / add_item / set_hours / remember_fact and confirm in one line what changed.",
        "Update order status or stock when asked; if the owner doesn't give an order number, find it with "
        "list_open_orders (if only one fits, use it). Be brief; the owner is busy.",
    ],
    tools=[
        Tool("get_stats", "Numbers for a day: bookings, orders, value, leads, open tickets.",
             {"date": {"type": "string", "description": "YYYY-MM-DD; default today"}}, [], get_stats),
        Tool("list_schedule", "Appointments and deliveries on a day.",
             {"date": {"type": "string", "description": "YYYY-MM-DD; default today"}}, [], list_schedule),
        Tool("list_open_orders", "Orders not yet delivered, with their refs, slots and payment status.",
             {}, [], list_open_orders),
        Tool("update_order_status", "Change an order's status; the customer is told on WhatsApp.",
             {"order_ref": {"type": "string"}, "status": {"type": "string", "enum": list(ORDER_STATUSES)},
              "note": {"type": "string"}}, ["order_ref", "status"], update_order_status),
        Tool("set_stock", "Set stock for a catalog product (-1 = stop tracking).",
             {"product_id": {"type": "integer"}, "stock": {"type": "integer"}}, ["product_id", "stock"], set_stock),
        Tool("update_item", "Change a service's or product's price or duration, or mark it unavailable / available.",
             {"name": {"type": "string", "description": "Item name as the owner says it"},
              "price_inr": {"type": "integer"}, "duration_min": {"type": "integer"},
              "available": {"type": "boolean"}}, ["name"], update_item),
        Tool("add_item", "Add a new service (bookable) or product (orderable).",
             {"name": {"type": "string"}, "price_inr": {"type": "integer"},
              "kind": {"type": "string", "enum": ["service", "product", "auto"]},
              "duration_min": {"type": "integer"}, "unit": {"type": "string"}}, ["name", "price_inr"], add_item),
        Tool("remember_fact", "Save a fact for Alaap to tell customers (parking, offers, policies).",
             {"topic": {"type": "string", "description": "Short English topic, e.g. Parking"},
              "fact": {"type": "string", "description": "The fact, in English"}}, ["topic", "fact"], remember_fact),
        Tool("set_hours", "Set the regular opening hours for a weekday, or close it every week.",
             {"weekday": {"type": "integer", "description": "0 = Monday ... 6 = Sunday"},
              "opens": {"type": "string", "description": "HH:MM"}, "closes": {"type": "string", "description": "HH:MM"},
              "closed": {"type": "boolean"}}, ["weekday"], set_hours),
        Tool("prepare_close_day", "Plan closing the business for a day and moving its appointments. Saves nothing.",
             {"date": {"type": "string", "description": "YYYY-MM-DD"}, "note": {"type": "string"},
              "move_appointments_to": {"type": "string", "description": "YYYY-MM-DD; default next open day"}},
             ["date"], prepare_close_day),
    ],
    actions={"close_day": do_close_day},
)
