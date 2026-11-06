"""Orders and delivery, payments, and order status."""

import difflib
import logging
from datetime import timedelta

from sqlalchemy import select

from .. import models, notify, payments
from ..scheduling import hours_on, parse_date
from ..timeutil import WEEKDAYS, now
from .base import (READBACK_NEXT, Context, Skill, Tool, ToolError, business, new_ref, phone_or_caller, stash,
                   upsert_customer)

log = logging.getLogger("alaap.orders")


# ---------- catalog and delivery ----------

def _product_view(p: models.Product) -> dict:
    return {"product_id": p.id, "name": p.name, "unit": p.unit, "price_inr": p.price_inr,
            "in_stock": p.stock is None or p.stock > 0}


def search_catalog(ctx, s, query):
    q = str(query).lower().strip()
    products = s.scalars(select(models.Product).where(models.Product.business_id == ctx.business_id,
                                                      models.Product.active.is_(True))).all()
    scored = []
    for p in products:
        names = [p.name.lower()] + [a.strip().lower() for a in (p.aliases or "").split(",") if a.strip()]
        best = max(1.0 if q in n or n in q else difflib.SequenceMatcher(None, q, n).ratio() for n in names)
        word = max((difflib.SequenceMatcher(None, w, n).ratio() for w in q.split() for n in names), default=0)
        scored.append((max(best, word), p))
    hits = [_product_view(p) for score, p in sorted(scored, key=lambda x: -x[0]) if score >= 0.6][:6]
    return {"query": query, "matches": hits,
            "note": None if hits else "Not in the catalog. Say so; don't offer items that aren't listed."}


def _area(s, ctx, pincode) -> models.ServiceArea:
    pin = "".join(ch for ch in str(pincode) if ch.isdigit())
    area = s.scalar(select(models.ServiceArea).where(models.ServiceArea.business_id == ctx.business_id,
                                                     models.ServiceArea.pincode == pin))
    if len(pin) != 6:
        raise ToolError("A pincode has 6 digits. Ask again.")
    if not area:
        raise ToolError(f"Pincode {pin} is not in the delivery area. Offer pickup from the shop instead.")
    return area


def _slots_on(s, biz, day):
    hours = hours_on(s, biz, day)
    if not hours:
        return []
    cutoff = now(biz.timezone) + timedelta(minutes=30)  # need time to pack
    out = []
    for slot in biz.slots:
        start = hours[0].replace(hour=int(slot.start[:2]), minute=int(slot.start[3:]))
        if start >= cutoff:
            out.append(slot.label)
    return out


def check_delivery(ctx, s, pincode):
    biz = business(s, ctx)
    area = _area(s, ctx, pincode)
    today = ctx.now().date()
    days = []
    for i in range(3):
        d = today + timedelta(days=i)
        slots = _slots_on(s, biz, d)
        if slots:
            days.append({"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "slots": slots})
    return {"pincode": area.pincode, "delivers": True, "delivery_fee_inr": area.delivery_fee_inr,
            "min_order_inr": area.min_order_inr, "slots": days}


def prepare_order(ctx, s, items, customer_name, address, pincode, slot_date, slot, payment_method,
                  landmark=None, customer_phone=None):
    biz = business(s, ctx)
    phone = phone_or_caller(ctx, customer_phone)
    if not str(customer_name or "").strip():
        raise ToolError("Need the customer's name.")
    if not str(address or "").strip():
        raise ToolError("Need the delivery address.")
    if payment_method not in ("upi", "cod"):
        raise ToolError("payment_method must be 'upi' or 'cod'.")
    if not items:
        raise ToolError("The order has no items.")
    area = _area(s, ctx, pincode)
    day = parse_date(slot_date)
    if slot not in _slots_on(s, biz, day):
        raise ToolError(f"Slot {slot} on {day} is not available. Use check_delivery for open slots.")
    lines, subtotal = [], 0
    for it in items:
        p = s.get(models.Product, int(it.get("product_id", 0)))
        qty = int(it.get("qty", 1))
        if not p or p.business_id != biz.id or not p.active:
            raise ToolError(f"Product {it.get('product_id')} is not in the catalog. Use search_catalog.")
        if qty < 1:
            raise ToolError("Quantity must be at least 1.")
        if p.stock is not None and p.stock < qty:
            raise ToolError(f"Only {p.stock} of {p.name} in stock.")
        lines.append({"product_id": p.id, "name": p.name, "unit": p.unit, "qty": qty, "price": p.price_inr,
                      "total": p.price_inr * qty})
        subtotal += p.price_inr * qty
    if subtotal < area.min_order_inr:
        raise ToolError(f"Minimum order for this pincode is Rs {area.min_order_inr}; it is Rs {subtotal} now.")
    total = subtotal + area.delivery_fee_inr
    action_id = stash(ctx, "order", {
        "name": customer_name.strip(), "phone": phone, "address": address.strip(), "landmark": landmark,
        "pincode": area.pincode, "slot_date": day.isoformat(), "slot": slot, "payment_method": payment_method,
        "lines": lines, "subtotal": subtotal, "fee": area.delivery_fee_inr, "total": total})
    items_text = ", ".join(f"{l['qty']} x {l['name']} ({l['unit']})" for l in lines)
    money = (f"Items Rs {subtotal} + delivery Rs {area.delivery_fee_inr} = total Rs {total} (say the total)"
             if area.delivery_fee_inr else f"Total Rs {total}, free delivery")
    return {"action_id": action_id,
            "read_back": f"{items_text}. {money}. Deliver to {address.strip()}"
                         f"{', near ' + landmark if landmark else ''}, {area.pincode}, on "
                         f"{WEEKDAYS[day.weekday()]} {day:%d %b} between {slot}. "
                         f"Payment: {'UPI link on WhatsApp' if payment_method == 'upi' else 'cash on delivery'}.",
            "next": READBACK_NEXT}


def do_order(ctx: Context, s, a: dict) -> dict:
    biz = business(s, ctx)
    for l in a["lines"]:  # stock may have changed since the read-back
        p = s.get(models.Product, l["product_id"])
        if p.stock is not None:
            if p.stock < l["qty"]:
                raise ToolError(f"{p.name} just went out of stock ({p.stock} left). Tell the customer.")
            p.stock -= l["qty"]
    cust = upsert_customer(s, ctx, a["name"], a["phone"])
    stamp = ctx.now()
    order = models.Order(
        ref=new_ref(s, models.Order), business_id=biz.id, customer_id=cust.id, address=a["address"],
        landmark=a.get("landmark"), pincode=a["pincode"], slot_date=parse_date(a["slot_date"]), slot_label=a["slot"],
        subtotal_inr=a["subtotal"], delivery_fee_inr=a["fee"], total_inr=a["total"],
        payment_method=a["payment_method"], payment_status="pending" if a["payment_method"] == "upi" else "cod",
        channel=ctx.channel, conversation_id=ctx.conversation_id, created_at=stamp, updated_at=stamp)
    order.items = [models.OrderItem(product_id=l["product_id"], name=l["name"], qty=l["qty"],
                                    unit_price_inr=l["price"], line_total_inr=l["total"]) for l in a["lines"]]
    s.add(order)
    s.flush()
    s.refresh(order)
    items = "\n".join(f"- {l['qty']} x {l['name']}: Rs {l['total']}" for l in a["lines"])
    notify.queue(s, biz, cust.phone, "order_summary",
                 f"Order {order.ref} at {biz.name}\n{items}\nDelivery: Rs {order.delivery_fee_inr}\n"
                 f"Total: Rs {order.total_inr}\nSlot: {order.slot_date:%a %d %b}, {order.slot_label}\n"
                 f"Address: {order.address}", order_id=order.id)
    say = f"Order placed, number {order.ref}. Summary sent on WhatsApp."
    if order.payment_method == "upi":
        try:
            order.payment_link_id, order.payment_link_url = payments.create_link(biz, order)
            notify.queue(s, biz, cust.phone, "payment_link",
                         f"Pay Rs {order.total_inr} for order {order.ref}: {order.payment_link_url}", order_id=order.id)
            say += " The UPI payment link is on WhatsApp too."
        except Exception:
            log.exception("payment link failed for order %s", order.ref)
            say += " The payment link will follow shortly."
    notify.owner_alert(s, biz, f"New order {order.ref}: Rs {order.total_inr}, {order.slot_date:%d %b} "
                               f"{order.slot_label}, {order.payment_method.upper()}")
    ctx.outcome = "ordered"
    return {"done": "ordered", "ref": order.ref, "total_inr": order.total_inr, "say": say}


# ---------- status and payments ----------

def _orders_for(s, ctx, order_ref=None, phone=None):
    q = select(models.Order).where(models.Order.business_id == ctx.business_id)
    if order_ref:
        q = q.where(models.Order.ref == str(order_ref).strip())
    else:
        q = q.join(models.Customer).where(models.Customer.phone == phone_or_caller(ctx, phone))
    found = s.scalars(q.order_by(models.Order.id.desc()).limit(3)).all()
    if not found:
        raise ToolError("No order found. Ask for the order number or the phone number used.")
    if order_ref and not ctx.is_owner:
        caller = phone_or_caller(ctx, phone)
        found = [o for o in found if o.customer.phone == caller]
        if not found:
            raise ToolError("That order number doesn't match this phone number.")
    return found


STATUS_TEXT = {"placed": "received, being packed soon", "preparing": "being packed",
               "out_for_delivery": "out for delivery", "delivered": "delivered", "cancelled": "cancelled"}


def get_order_status(ctx, s, order_ref=None, phone=None):
    return {"orders": [{
        "ref": o.ref, "status": STATUS_TEXT.get(o.status, o.status), "slot": f"{o.slot_date:%a %d %b} {o.slot_label}",
        "total_inr": o.total_inr, "payment": o.payment_status, "note_from_shop": o.status_note,
        "items": [f"{i.qty} x {i.name}" for i in o.items]} for o in _orders_for(s, ctx, order_ref, phone)]}


def send_payment_link(ctx, s, order_ref, phone=None):
    o = _orders_for(s, ctx, order_ref, phone)[0]
    if o.payment_status == "paid":
        return {"already_paid": True}
    biz = business(s, ctx)
    if not o.payment_link_url:
        o.payment_link_id, o.payment_link_url = payments.create_link(biz, o)
        o.payment_method, o.payment_status = "upi", "pending"
    notify.queue(s, biz, o.customer.phone, "payment_link",
                 f"Pay Rs {o.total_inr} for order {o.ref}: {o.payment_link_url}", order_id=o.id)
    return {"done": "link_sent", "say": "Payment link sent on WhatsApp."}


def prepare_order_cancellation(ctx, s, order_ref, phone=None):
    o = _orders_for(s, ctx, order_ref, phone)[0]
    if o.status not in ("placed", "preparing"):
        raise ToolError(f"Order {o.ref} is {STATUS_TEXT.get(o.status)}; it can't be cancelled now. Offer a callback.")
    action_id = stash(ctx, "cancel_order", {"order_id": o.id})
    return {"action_id": action_id, "read_back": f"Cancel order {o.ref} (Rs {o.total_inr})", "next": READBACK_NEXT}


def do_cancel_order(ctx, s, a):
    o = s.get(models.Order, a["order_id"])
    o.status, o.updated_at = "cancelled", ctx.now()
    for i in o.items:
        p = s.get(models.Product, i.product_id)
        if p and p.stock is not None:
            p.stock += i.qty
    biz = business(s, ctx)
    paid = " Your payment will be refunded by the shop." if o.payment_status == "paid" else ""
    notify.queue(s, biz, o.customer.phone, "cancellation", f"Order {o.ref} at {biz.name} is cancelled.{paid}",
                 order_id=o.id)
    notify.owner_alert(s, biz, f"Order {o.ref} cancelled by customer.{' Refund needed.' if paid else ''}")
    ctx.outcome = "cancelled"
    return {"done": "cancelled", "ref": o.ref}


def profile(biz: models.Business) -> str:
    lines = ["Catalog (id | name | unit | price | stock):"]
    for p in biz.products:
        if p.active:
            stock = "" if p.stock is None else (" | out of stock" if p.stock <= 0 else f" | {p.stock} left")
            lines.append(f"  {p.id} | {p.name} | {p.unit} | Rs {p.price_inr}{stock}")
    lines.append("Delivery pincodes (pincode | fee | minimum order): " + "; ".join(
        f"{a.pincode} | Rs {a.delivery_fee_inr} | Rs {a.min_order_inr}" for a in biz.areas))
    lines.append("Delivery slots: " + ", ".join(sl.label for sl in biz.slots))
    return "\n".join(lines)


_phone = {"type": "string", "description": "10-digit mobile; leave out to use the caller's"}

ORDERS = Skill(
    key="orders",
    name="Orders and delivery",
    goal="Take delivery orders from the catalog.",
    fields=["items and quantities", "name", "mobile", "address with a landmark", "pincode", "delivery slot",
            "payment method (UPI link or cash on delivery)"],
    rules=[
        "Match what the customer says to catalog items with search_catalog; confirm the exact item when unsure "
        "(brand, size). Never add items that are not in the catalog.",
        "Check the pincode with check_delivery before promising delivery, and offer its slots.",
        "Ask for a landmark; Indian addresses need one.",
        "Then prepare_order, read back items, total and slot, and confirm_action only after a clear yes.",
    ],
    tools=[
        Tool("search_catalog", "Find catalog items matching what the customer asked for.",
             {"query": {"type": "string"}}, ["query"], search_catalog),
        Tool("check_delivery", "Whether a pincode is served, the fee, minimum order and open slots.",
             {"pincode": {"type": "string"}}, ["pincode"], check_delivery),
        Tool("prepare_order", "Check an order, compute the total and get the read-back. Saves nothing.",
             {"items": {"type": "array", "items": {"type": "object", "properties": {
                 "product_id": {"type": "integer"}, "qty": {"type": "integer"}},
                 "required": ["product_id", "qty"]}},
              "customer_name": {"type": "string"}, "customer_phone": _phone,
              "address": {"type": "string"}, "landmark": {"type": "string"}, "pincode": {"type": "string"},
              "slot_date": {"type": "string", "description": "YYYY-MM-DD"},
              "slot": {"type": "string", "description": "A slot label from check_delivery, e.g. 10:00-12:00"},
              "payment_method": {"type": "string", "enum": ["upi", "cod"]}},
             ["items", "customer_name", "address", "pincode", "slot_date", "slot", "payment_method"], prepare_order),
    ],
    actions={"order": do_order},
    profile=profile,
)

PAYMENTS = Skill(
    key="payments",
    name="Payments",
    goal="Send UPI payment links and say whether an order is paid.",
    fields=["order number"],
    rules=["For UPI, the link is sent on WhatsApp automatically when the order is placed; use send_payment_link "
           "only if the customer asks again or wants to switch from cash to UPI."],
    tools=[Tool("send_payment_link", "(Re)send a UPI payment link for an order on WhatsApp.",
                {"order_ref": {"type": "string"}, "phone": _phone}, ["order_ref"], send_payment_link)],
)

ORDER_STATUS = Skill(
    key="order_status",
    name="Order status",
    goal="Tell customers where their order is, and cancel it if it hasn't left.",
    fields=["order number or phone"],
    rules=["Use get_order_status; say the status and slot simply. Don't invent delivery times beyond the slot.",
           "To cancel, prepare_order_cancellation, read back, confirm_action after a yes."],
    tools=[
        Tool("get_order_status", "Recent orders and their status, by order number or phone.",
             {"order_ref": {"type": "string"}, "phone": _phone}, [], get_order_status),
        Tool("prepare_order_cancellation", "Check cancelling an order and get the read-back. Saves nothing.",
             {"order_ref": {"type": "string"}, "phone": _phone}, ["order_ref"], prepare_order_cancellation),
    ],
    actions={"cancel_order": do_cancel_order},
)
