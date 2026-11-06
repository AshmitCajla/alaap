"""What a skill is: fields to collect, rules to follow, and the tools it may call.

The engine changes data only through tools. Anything that writes something a
customer cares about (a booking, an order) is two steps: a prepare_* tool checks
it and returns a read-back, and confirm_action saves it, which is refused until
the customer has replied after hearing the read-back."""

import random
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..errors import ToolError  # noqa: F401  (re-exported)
from ..timeutil import now


@dataclass
class Context:
    business_id: int
    conversation_id: int
    tz: str = "Asia/Kolkata"
    channel: str = "web"
    caller_phone: str | None = None
    is_owner: bool = False
    user_turn: int = 0                 # customer messages so far
    pending: dict[str, dict] = field(default_factory=dict)
    next_action: int = 1
    outcome: str | None = None         # what this conversation achieved
    handoff: bool = False              # a human should take over (urgent call transfer)
    end_call: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Context":
        return cls(**d)

    def now(self):
        return now(self.tz)


Handler = Callable[..., dict]


@dataclass
class Tool:
    name: str
    description: str
    properties: dict[str, Any]
    required: list[str]
    handler: Handler

    def schema(self) -> dict:
        """OpenAI-style function tool (works with Gemini, Groq and Ollama)."""
        return {"type": "function", "function": {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": self.properties, "required": self.required},
        }}


@dataclass
class Skill:
    key: str
    name: str
    goal: str
    fields: list[str]
    rules: list[str]
    tools: list[Tool]
    # Executors for confirm_action, keyed by the action kind a prepare_* tool stashes.
    actions: dict[str, Handler] = field(default_factory=dict)
    # Extra profile text this skill needs in the system prompt (catalog, areas, ...).
    profile: Callable[[models.Business], str] | None = None

    def prompt(self) -> str:
        out = [f"## Skill: {self.name}", self.goal]
        if self.fields:
            out.append("Collect: " + "; ".join(self.fields) + ".")
        out.extend(f"- {r}" for r in self.rules)
        return "\n".join(out)


# ---------- helpers shared by skills ----------

def normalise_phone(value: str | None) -> str | None:
    """Last 10 digits of an Indian mobile number, or None."""
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits[-10:] if len(digits) >= 10 else None


def phone_or_caller(ctx: Context, phone: str | None) -> str:
    p = normalise_phone(phone) or normalise_phone(ctx.caller_phone)
    if not p:
        raise ToolError("Need the customer's 10-digit mobile number. Ask for it.")
    return p


def business(s: Session, ctx: Context) -> models.Business:
    return s.get(models.Business, ctx.business_id)


def upsert_customer(s: Session, ctx: Context, name: str | None, phone: str) -> models.Customer:
    c = s.scalar(select(models.Customer).where(models.Customer.business_id == ctx.business_id,
                                               models.Customer.phone == phone))
    if c is None:
        c = models.Customer(business_id=ctx.business_id, name=(name or "Customer").strip(), phone=phone)
        s.add(c)
    elif name and name.strip():
        c.name = name.strip()
    c.last_seen_at = ctx.now()
    s.flush()
    return c


def new_ref(s: Session, model) -> str:
    """A 4-digit reference that is easy to say on a call."""
    for _ in range(50):
        ref = str(random.randint(1000, 9999))
        if not s.scalar(select(model.id).where(model.ref == ref)):
            return ref
    return str(random.randint(100000, 999999))


def stash(ctx: Context, kind: str, payload: dict) -> str:
    """Remember a prepared action. Only the latest one can be confirmed."""
    action_id = f"A{ctx.next_action}"
    ctx.next_action += 1
    ctx.pending = {action_id: {"kind": kind, "user_turn": ctx.user_turn, **payload}}
    return action_id


READBACK_NEXT = ("Read this back to the customer in their language and ask them to confirm. "
                 "Call confirm_action only after they clearly say yes.")
