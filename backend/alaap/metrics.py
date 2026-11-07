"""The plan's metrics, computed from the database."""

from datetime import datetime, timedelta

from sqlalchemy import func, select

from . import models
from .skills import PLANS
from .timeutil import now

DONE = {"booked", "rescheduled", "cancelled", "ordered", "lead", "callback", "complaint"}


def overview(s, biz: models.Business, days: int = 7) -> dict:
    t = now(biz.timezone)
    since = datetime.combine((t - timedelta(days=days - 1)).date(), datetime.min.time())
    C, M = models.Conversation, models.Message
    # Only plain columns, and "the customer said something" as an EXISTS: no per-conversation message loading.
    spoke = select(M.id).where(M.conversation_id == C.id, M.role == "customer").exists()
    talked = s.execute(select(C.id, C.channel, C.outcome, C.handoff, C.errors, C.started_at).where(
        C.business_id == biz.id, C.is_owner.is_(False), C.started_at >= since, spoke)).all()
    # A conversation counts as completed if a skill finished something, or it ended without errors or handoff
    # (an enquiry that was answered).
    completed = [c for c in talked if c.outcome in DONE or (not c.handoff and c.errors == 0)]
    latencies = sorted(s.scalars(select(M.latency_ms).join(C, C.id == M.conversation_id).where(
        C.business_id == biz.id, C.is_owner.is_(False), C.started_at >= since, M.latency_ms.is_not(None))).all())
    p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else None

    def count(model, col, *where):
        return s.scalar(select(func.count(model.id)).where(model.business_id == biz.id, col >= since, *where)) or 0

    bookings = count(models.Appointment, models.Appointment.created_at, models.Appointment.conversation_id.is_not(None))
    orders = count(models.Order, models.Order.created_at, models.Order.conversation_id.is_not(None))
    order_value = s.scalar(select(func.coalesce(func.sum(models.Order.total_inr), 0)).where(
        models.Order.business_id == biz.id, models.Order.created_at >= since, models.Order.status != "cancelled")) or 0
    booking_value = s.scalar(select(func.coalesce(func.sum(models.Service.price_inr), 0))
                             .join(models.Appointment, models.Appointment.service_id == models.Service.id)
                             .where(models.Appointment.business_id == biz.id, models.Appointment.created_at >= since,
                                    models.Appointment.status != "cancelled")) or 0

    series = []
    for i in range(days):
        d = (since + timedelta(days=i)).date()
        day_convs = [c for c in talked if c.started_at.date() == d]
        series.append({"date": d.isoformat(), "conversations": len(day_convs),
                       "completed": sum(1 for c in day_convs if c.outcome in DONE)})

    month_start = datetime.combine(t.date().replace(day=1), datetime.min.time())
    call_seconds = s.scalar(select(func.coalesce(func.sum(models.Conversation.call_seconds), 0)).where(
        models.Conversation.business_id == biz.id, models.Conversation.started_at >= month_start)) or 0
    plan = PLANS.get(biz.plan, PLANS["starter"])
    channels = {}
    for c in talked:
        channels[c.channel] = channels.get(c.channel, 0) + 1
    return {
        "days": days,
        "north_star": bookings + orders,
        "bookings_by_alaap": bookings,
        "orders_by_alaap": orders,
        "value_inr": int(order_value) + int(booking_value),
        "conversations": len(talked),
        "task_completion_rate": round(len(completed) / len(talked), 3) if talked else None,
        "handoff_rate": round(sum(1 for c in talked if c.handoff) / len(talked), 3) if talked else None,
        "latency_p95_ms": p95,
        "open_tickets": s.scalar(select(func.count(models.Ticket.id)).where(
            models.Ticket.business_id == biz.id, models.Ticket.status == "open")) or 0,
        "new_leads": count(models.Lead, models.Lead.created_at),
        "channels": channels,
        "series": series,
        "usage": {"plan": biz.plan, "price_inr": plan["price_inr"], "included_minutes": plan["minutes"],
                  "used_minutes": round(call_seconds / 60, 1)},
    }
