"""Skill registry. Supporting a new kind of business means adding a skill here."""

from . import appointments, enquiries
from .base import Context, Skill, Tool

REGISTRY: dict[str, Skill] = {
    "appointments": appointments.SKILL,
    "enquiries": enquiries.SKILL,
}


def enabled(names: str) -> list[Skill]:
    return [REGISTRY[n.strip()] for n in names.split(",") if n.strip() in REGISTRY]


__all__ = ["REGISTRY", "Context", "Skill", "Tool", "enabled"]
