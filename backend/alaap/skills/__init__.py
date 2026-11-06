"""Skill registry. Supporting a new kind of business = adding skills here."""

from . import appointments, leads, orders, owner, support
from .base import Context, Skill, Tool, ToolError

REGISTRY: dict[str, Skill] = {s.key: s for s in [
    appointments.SKILL, support.ENQUIRIES, support.COMPLAINTS, orders.ORDERS, orders.PAYMENTS,
    orders.ORDER_STATUS, leads.SKILL, leads.FOLLOWUPS, owner.SKILL,
]}

# Which skills each plan includes (see Business model in the plan).
PLANS = {
    "starter": {"price_inr": 999, "minutes": 100,
                "skills": {"appointments", "enquiries", "complaints"}},
    "pro": {"price_inr": 2499, "minutes": 500,
            "skills": {"appointments", "enquiries", "complaints", "orders", "payments", "order_status", "followups"}},
    "business": {"price_inr": 5999, "minutes": 1500, "skills": set(REGISTRY) - {"owner"}},
}

# Sensible skills per kind of business, used when onboarding.
DEFAULT_SKILLS = {
    "salon": "appointments,enquiries,complaints,followups",
    "clinic": "appointments,enquiries,complaints,followups",
    "kirana": "orders,payments,order_status,enquiries,complaints,followups",
    "restaurant": "orders,payments,order_status,enquiries,complaints,followups",
    "pharmacy": "orders,payments,order_status,enquiries,complaints,followups",
    "coaching": "leads,appointments,enquiries,complaints,followups",
    "real_estate": "leads,appointments,enquiries,complaints,followups",
    "gym": "leads,appointments,enquiries,complaints,followups",
    "home_services": "appointments,leads,enquiries,complaints,followups",
}


def for_business(skill_keys: list[str], plan: str, owner_mode: bool = False) -> list[Skill]:
    if owner_mode:
        return [REGISTRY["owner"]]
    allowed = PLANS.get(plan, PLANS["starter"])["skills"]
    return [REGISTRY[k] for k in skill_keys if k in REGISTRY and k in allowed]


__all__ = ["REGISTRY", "PLANS", "DEFAULT_SKILLS", "Context", "Skill", "Tool", "ToolError", "for_business"]
