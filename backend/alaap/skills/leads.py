"""Leads: qualify, score, and hand to the owner (book a visit through Appointments)."""

from .. import models, notify
from .base import Skill, Tool, ToolError, business, normalise_phone

SOON = ("aaj", "kal", "today", "tomorrow", "this week", "is hafte", "jaldi", "abhi", "asap", "is mahine",
        "this month", "turant")


def score(lead: models.Lead) -> int:
    pts = 25 if lead.phone else 0
    pts += 20 if lead.budget else 0
    pts += 15 if lead.location else 0
    pts += 15 if lead.need and len(lead.need) > 25 else 5
    when = (lead.preferred_time or "").lower()
    pts += 25 if any(w in when for w in SOON) else (10 if when else 0)
    return min(pts, 100)


def save_lead(ctx, s, need, name=None, phone=None, budget=None, location=None, preferred_time=None):
    p = normalise_phone(phone) or normalise_phone(ctx.caller_phone)
    if not p:
        raise ToolError("Need a 10-digit mobile number for the lead. Ask for it.")
    lead = models.Lead(business_id=ctx.business_id, name=name, phone=p, need=need, budget=budget,
                       location=location, preferred_time=preferred_time, conversation_id=ctx.conversation_id,
                       created_at=ctx.now())
    lead.score = score(lead)
    s.add(lead)
    s.flush()
    biz = business(s, ctx)
    if lead.score >= 70:
        notify.owner_alert(s, biz, f"Hot lead ({lead.score}/100): {name or 'someone'} {p}: {need}. "
                                   f"Budget {budget or '-'}, {location or '-'}, wants {preferred_time or '-'}.")
    ctx.outcome = ctx.outcome or "lead"
    return {"done": "lead_saved", "score": lead.score,
            "next": "Offer to book a visit or counselling slot (Appointments) or a callback at their preferred time."}


SKILL = Skill(
    key="leads",
    name="Leads",
    goal="Qualify people interested in buying or joining, and get them to a visit or callback.",
    fields=["what they need", "budget", "location", "preferred time", "name", "mobile"],
    rules=[
        "Ask naturally, one question at a time; don't interrogate. Save the lead with save_lead once you know "
        "the need and a phone number, even if some fields are missing.",
        "Then offer a visit / demo / counselling slot if the profile has one, else a callback.",
    ],
    tools=[Tool("save_lead", "Save a qualified lead for the owner. Scores it automatically.",
                {"need": {"type": "string", "description": "What they want, in English"},
                 "name": {"type": "string"}, "phone": {"type": "string"}, "budget": {"type": "string"},
                 "location": {"type": "string"},
                 "preferred_time": {"type": "string", "description": "When they want to start / visit, as said"}},
                ["need"], save_lead)],
)

FOLLOWUPS = Skill(
    key="followups",
    name="Follow-ups",
    goal="Reorder reminders, feedback requests and win-back offers (sent by the scheduler, not in calls).",
    fields=[], rules=[], tools=[],
)
