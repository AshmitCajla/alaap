"""Enquiries (answer from the profile, offer a callback) and complaints / handoff."""

from .. import models, notify
from .base import Context, Skill, Tool, ToolError, business, normalise_phone


def _ticket(ctx: Context, s, kind: str, issue: str, name=None, phone=None, urgency="normal") -> models.Ticket:
    p = normalise_phone(phone) or normalise_phone(ctx.caller_phone)
    if not p:
        raise ToolError("Need a 10-digit mobile number so the owner can call back. Ask for it.")
    t = models.Ticket(business_id=ctx.business_id, kind=kind, name=name, phone=p, issue=issue,
                      urgency=urgency if urgency in ("low", "normal", "urgent") else "normal",
                      conversation_id=ctx.conversation_id, created_at=ctx.now())
    s.add(t)
    s.flush()
    return t


def request_callback(ctx, s, reason, name=None, phone=None):
    t = _ticket(ctx, s, "callback", reason, name, phone)
    notify.owner_alert(s, business(s, ctx), f"Callback wanted: {name or 'customer'} ({t.phone}): {reason}")
    ctx.outcome = ctx.outcome or "callback"
    return {"done": "callback_logged", "say": "The owner will call back."}


def log_complaint(ctx, s, issue, urgency="normal", name=None, phone=None):
    t = _ticket(ctx, s, "complaint", issue, name, phone, urgency)
    biz = business(s, ctx)
    tag = "URGENT complaint" if t.urgency == "urgent" else "Complaint"
    notify.owner_alert(s, biz, f"{tag} from {name or 'customer'} ({t.phone}): {issue}")
    ctx.outcome = "complaint"
    if t.urgency == "urgent" and ctx.channel == "phone":
        ctx.handoff = True
        return {"done": "complaint_logged", "transfer": True,
                "say": "Tell the caller you are connecting them to the owner now."}
    return {"done": "complaint_logged", "say": "Logged; the owner has been told and will call back."}


ENQUIRIES = Skill(
    key="enquiries",
    name="Enquiries",
    goal="Answer questions about prices, hours, location, services, products and staff.",
    fields=["the question"],
    rules=[
        "Answer only from the business profile. If the answer is not there, say you are not sure and offer "
        "a callback from the owner (request_callback). Never guess prices, offers or availability.",
    ],
    tools=[Tool("request_callback", "Ask the owner to call the customer back.",
                {"reason": {"type": "string", "description": "What the customer wants, in English"},
                 "name": {"type": "string"},
                 "phone": {"type": "string", "description": "10-digit mobile; leave out to use the caller's"}},
                ["reason"], request_callback)],
)

COMPLAINTS = Skill(
    key="complaints",
    name="Complaints and handoff",
    goal="Handle unhappy customers and anything that needs a human.",
    fields=["the issue", "how urgent it is"],
    rules=[
        "Apologise sincerely once, don't argue, don't promise refunds or discounts.",
        "Log it with log_complaint. Urgency 'urgent' only for safety, health, or a customer stuck right now "
        "(e.g. wrong medicine, order not delivered and waiting); on a phone call that transfers to the owner.",
        "If the caller asks for a human, log a callback, or a complaint if they are unhappy.",
    ],
    tools=[Tool("log_complaint", "Record a complaint and alert the owner on WhatsApp.",
                {"issue": {"type": "string", "description": "The problem, in English"},
                 "urgency": {"type": "string", "enum": ["low", "normal", "urgent"]},
                 "name": {"type": "string"},
                 "phone": {"type": "string", "description": "10-digit mobile; leave out to use the caller's"}},
                ["issue"], log_complaint)],
)
