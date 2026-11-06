"""What a skill is: the fields it must collect, the rules it follows and the
tools it may call. The engine only changes data through these tools."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Context:
    """Per-conversation state that tools can read and update."""
    business_id: int
    conversation_id: int
    channel: str = "web"
    caller_phone: str | None = None
    db_path: Path | None = None
    # Number of customer messages so far. A prepared action can be confirmed
    # only after a later customer message, i.e. after they heard the read-back.
    user_turn: int = 0
    pending: dict[str, dict] = field(default_factory=dict)
    next_action: int = 1


@dataclass
class Tool:
    name: str
    description: str
    properties: dict[str, Any]
    required: list[str]
    handler: Callable[..., dict]

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": self.required,
                "additionalProperties": False,
            },
        }


@dataclass
class Skill:
    name: str
    goal: str
    fields: list[str]
    rules: list[str]
    tools: list[Tool]

    def prompt(self) -> str:
        out = [f"## Skill: {self.name}", self.goal]
        if self.fields:
            out.append("Collect: " + "; ".join(self.fields) + ".")
        out.extend(f"- {r}" for r in self.rules)
        return "\n".join(out)


def normalise_phone(value: str | None) -> str | None:
    """Keep the last 10 digits of an Indian mobile number."""
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits[-10:] if len(digits) >= 10 else None
