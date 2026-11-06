"""Tables. Times are naive datetimes in the business's own timezone."""

from datetime import date, datetime

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import now


def _now():
    return now()


class Business(Base):
    __tablename__ = "business"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(50))  # salon, clinic, kirana, restaurant, coaching, ...
    phone: Mapped[str | None] = mapped_column(String(20))
    owner_name: Mapped[str | None] = mapped_column(String(100))
    owner_phone: Mapped[str | None] = mapped_column(String(20))  # 10 digits
    owner_language: Mapped[str] = mapped_column(String(20), default="hi-IN")
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    languages: Mapped[str] = mapped_column(String(200), default="Hindi, Punjabi, English")
    about: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[str] = mapped_column(String(300), default="appointments,enquiries,complaints")
    plan: Mapped[str] = mapped_column(String(20), default="starter")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    voice: Mapped[str | None] = mapped_column(String(50))
    assistant_name: Mapped[str | None] = mapped_column(String(40), default="Riya")  # who callers talk to
    speech_speed: Mapped[float | None] = mapped_column(Float, default=1.0)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime)  # owner opened the share kit / poster
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    paid_until: Mapped[datetime | None] = mapped_column(DateTime)
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    exotel_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    hours = relationship("BusinessHours", cascade="all, delete-orphan", order_by="BusinessHours.weekday")
    services = relationship("Service", cascade="all, delete-orphan", order_by="Service.id")
    staff = relationship("Staff", cascade="all, delete-orphan", order_by="Staff.id")
    faqs = relationship("Faq", cascade="all, delete-orphan", order_by="Faq.id")
    products = relationship("Product", cascade="all, delete-orphan", order_by="Product.id")
    areas = relationship("ServiceArea", cascade="all, delete-orphan", order_by="ServiceArea.pincode")
    slots = relationship("DeliverySlot", cascade="all, delete-orphan", order_by="DeliverySlot.start")
    closures = relationship("Closure", cascade="all, delete-orphan", order_by="Closure.day")

    def skill_list(self) -> list[str]:
        return [s.strip() for s in self.skills.split(",") if s.strip()]


class OwnerUser(Base):
    __tablename__ = "owner_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(300))


class BusinessHours(Base):
    __tablename__ = "business_hours"
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"), primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0 = Monday
    opens: Mapped[str] = mapped_column(String(5))
    closes: Mapped[str] = mapped_column(String(5))


class Closure(Base):
    """A day the business is shut (holiday, 'kal shop band hai')."""
    __tablename__ = "closure"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    day: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))


staff_service = Table(
    "staff_service", Base.metadata,
    Column("staff_id", ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("service.id", ondelete="CASCADE"), primary_key=True),
)


class Service(Base):
    __tablename__ = "service"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    name: Mapped[str] = mapped_column(String(200))
    duration_min: Mapped[int] = mapped_column(Integer)
    price_inr: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    services = relationship("Service", secondary=staff_service)


class Faq(Base):
    __tablename__ = "faq"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (UniqueConstraint("business_id", "phone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    language: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    winback_sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class Appointment(Base):
    __tablename__ = "appointment"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(10), unique=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="booked")  # booked | cancelled | done | no_show
    channel: Mapped[str | None] = mapped_column(String(20))
    conversation_id: Mapped[int | None] = mapped_column(Integer)
    feedback_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    customer = relationship("Customer")
    service = relationship("Service")
    staff = relationship("Staff")


class Product(Base):
    __tablename__ = "product"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[str | None] = mapped_column(Text)  # other names customers use, comma separated
    unit: Mapped[str] = mapped_column(String(50), default="1 pc")
    price_inr: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int | None] = mapped_column(Integer)  # None = not tracked
    reorder_days: Mapped[int | None] = mapped_column(Integer)  # remind to reorder after N days
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceArea(Base):
    __tablename__ = "service_area"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    pincode: Mapped[str] = mapped_column(String(6))
    delivery_fee_inr: Mapped[int] = mapped_column(Integer, default=0)
    min_order_inr: Mapped[int] = mapped_column(Integer, default=0)


class DeliverySlot(Base):
    __tablename__ = "delivery_slot"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    start: Mapped[str] = mapped_column(String(5))
    end: Mapped[str] = mapped_column(String(5))

    @property
    def label(self) -> str:
        return f"{self.start}-{self.end}"


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(10), unique=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    address: Mapped[str] = mapped_column(Text)
    landmark: Mapped[str | None] = mapped_column(String(200))
    pincode: Mapped[str] = mapped_column(String(6))
    slot_date: Mapped[date] = mapped_column(Date)
    slot_label: Mapped[str] = mapped_column(String(20))
    subtotal_inr: Mapped[int] = mapped_column(Integer)
    delivery_fee_inr: Mapped[int] = mapped_column(Integer, default=0)
    total_inr: Mapped[int] = mapped_column(Integer)
    payment_method: Mapped[str] = mapped_column(String(10))  # upi | cod
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | paid | cod
    payment_link_id: Mapped[str | None] = mapped_column(String(100))
    payment_link_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="placed")
    # placed | preparing | out_for_delivery | delivered | cancelled
    status_note: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(20))
    conversation_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    customer = relationship("Customer")
    items = relationship("OrderItem", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    name: Mapped[str] = mapped_column(String(200))
    qty: Mapped[int] = mapped_column(Integer)
    unit_price_inr: Mapped[int] = mapped_column(Integer)
    line_total_inr: Mapped[int] = mapped_column(Integer)


class Lead(Base):
    __tablename__ = "lead"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    need: Mapped[str] = mapped_column(Text)
    budget: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    preferred_time: Mapped[str | None] = mapped_column(String(100))
    score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | contacted | visit_booked | won | lost
    notes: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[int | None] = mapped_column(Integer)
    followup_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Ticket(Base):
    """A callback request or complaint for the owner."""
    __tablename__ = "ticket"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    kind: Mapped[str] = mapped_column(String(20))  # callback | complaint
    name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    issue: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | urgent
    status: Mapped[str] = mapped_column(String(20), default="open")
    conversation_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Conversation(Base):
    __tablename__ = "conversation"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    channel: Mapped[str] = mapped_column(String(20))  # phone | whatsapp | web | owner
    caller_phone: Mapped[str | None] = mapped_column(String(20))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str | None] = mapped_column(String(30))
    # booked | rescheduled | cancelled | ordered | lead | callback | complaint | answered
    handoff: Mapped[bool] = mapped_column(Boolean, default=False)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    call_seconds: Mapped[int] = mapped_column(Integer, default=0)
    messages = relationship("Message", order_by="Message.id", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "message"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation.id"))
    role: Mapped[str] = mapped_column(String(20))  # customer | alaap | tool
    text: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Outbox(Base):
    """Messages to send (WhatsApp text/voice, outbound calls). The job runner sends them."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    to_phone: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp")  # whatsapp | whatsapp_voice | call
    kind: Mapped[str] = mapped_column(String(30))
    # confirmation | reminder | cancellation | order_summary | payment_link | owner_alert
    # | daily_summary | feedback | reorder | winback | lead_followup | reply
    body: Mapped[str] = mapped_column(Text)
    media_path: Mapped[str | None] = mapped_column(Text)
    send_after: Mapped[datetime] = mapped_column(DateTime, default=_now)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | sent | failed | cancelled | logged
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    appointment_id: Mapped[int | None] = mapped_column(Integer)
    order_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class PlanPayment(Base):
    """A business paying for its Alaap plan (Razorpay payment link)."""
    __tablename__ = "plan_payment"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business.id"))
    plan: Mapped[str] = mapped_column(String(20))
    months: Mapped[int] = mapped_column(Integer, default=1)
    amount_inr: Mapped[int] = mapped_column(Integer)
    link_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    link_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="created")  # created | paid
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
