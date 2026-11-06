"""The conversation engine: one Claude tool-use loop over the enabled skills.

The model talks; skills decide what is true. Data only changes through
skill tools, and bookings need a read-back and a customer reply first."""

import json
import logging
from typing import Any

import anthropic

from . import config, db, skills
from .scheduling import FMT, BookingError, now, profile, profile_text
from .skills.base import Context, normalise_phone

log = logging.getLogger("alaap")

MAX_TOOL_ROUNDS = 8
FALLBACK_BETA = "server-side-fallback-2026-07-01"

PERSONA = """You are Alaap, the front desk for {name}, a {kind} in {city}. You answer phone calls, \
WhatsApp and web chats for the business.

How to talk:
- Reply in the language and script the customer uses: Hindi, Punjabi, English or a mix. If they write \
Hindi or Punjabi in Roman letters, reply in Roman letters.
- This is often a phone call. Keep each reply to one or two short sentences. No lists, markdown or emojis.
- Say times the way people say them, e.g. "shaam 5 baje" or "5 PM", not "17:00".
- Be warm and brief. Ask for one missing thing at a time.

Ground rules:
- Use only the business profile below and tool results. Never invent prices, services, staff, slots, \
offers or bookings.
- Data changes only through tools. Before anything is saved, read it back and get a clear yes.
- If the customer is upset, has a complaint, or asks for something you can't do, apologise and offer a \
callback from the owner.
- Use ids from the profile in tool calls; never tell the customer the ids.

{skills}

# Business profile
{profile}
"""

SESSION = """# This conversation
Now: {now} ({weekday}).
Channel: {channel}.
{caller}
You have already greeted the customer with: "{greeting}"
"""


def greeting_for(biz: dict, channel: str) -> str:
    recording = " Yeh call record ho sakti hai." if channel == "phone" else ""
    return f"Sat Sri Akal ji! {biz['name']} mein aapka swagat hai.{recording} Bataiye, main kya madad karoon?"


class Conversation:
    def __init__(self, business_id: int, channel: str = "web", caller_phone: str | None = None,
                 db_path=None, client: Any = None):
        self.client = client or anthropic.Anthropic()
        phone = normalise_phone(caller_phone)
        with db.connect(db_path) as conn:
            prof = profile(conn, business_id)
            cur = conn.execute(
                "INSERT INTO conversation (business_id, channel, caller_phone, started_at) VALUES (?, ?, ?, ?)",
                (business_id, channel, phone, now().strftime(FMT)),
            )
            conversation_id = cur.lastrowid
            known = phone and db.row(conn, "SELECT name FROM customer WHERE business_id = ? AND phone = ?",
                                     business_id, phone)
        self.ctx = Context(business_id=business_id, conversation_id=conversation_id, channel=channel,
                           caller_phone=phone, db_path=db_path)
        self.db_path = db_path
        self.greeting = greeting_for(prof, channel)

        active = skills.enabled(prof["skills"])
        self.handlers = {t.name: t.handler for s in active for t in s.tools}
        self.tools = [t.schema() for s in active for t in s.tools]

        if phone:
            caller = f"Caller's mobile (from caller ID): {phone}." + (
                f" Known customer: {known['name']}." if known else "")
        else:
            caller = "Caller's mobile is unknown; ask for it when needed."
        current = now()
        self.system = [
            {"type": "text",
             "text": PERSONA.format(name=prof["name"], kind=prof["kind"], city=prof["city"],
                                    skills="\n\n".join(s.prompt() for s in active),
                                    profile=profile_text(prof))},
            {"type": "text",
             "text": SESSION.format(now=current.strftime(FMT), weekday=current.strftime("%A"),
                                    channel=channel, caller=caller, greeting=self.greeting)},
        ]
        self.messages: list[dict] = []
        self._log("alaap", self.greeting)

    # ---------- public ----------

    def reply(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        self.ctx.user_turn += 1
        self._log("customer", text)
        self.messages.append({"role": "user", "content": text})

        spoken: list[str] = []
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._call()
            # Append the whole content unchanged (keeps thinking blocks valid).
            self.messages.append({"role": "assistant", "content": response.content})
            spoken += [b.text for b in response.content if b.type == "text" and b.text.strip()]

            if response.stop_reason == "refusal":
                spoken = ["Maaf kijiye, is baare mein main madad nahi kar sakti. Owner aapko call karenge."]
                break
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason != "tool_use":
                break  # end_turn, max_tokens, stop_sequence
            results = [self._run_tool(b) for b in response.content if b.type == "tool_use"]
            self.messages.append({"role": "user", "content": results})
        else:
            spoken.append("Ek minute, main owner se baat karwa deti hoon.")

        answer = " ".join(spoken).strip() or "Ji, kripya dobara boliye?"
        self._log("alaap", answer)
        return answer

    # ---------- internals ----------

    def _call(self):
        kwargs = dict(
            model=config.MODEL,
            max_tokens=4096,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": config.EFFORT},
            cache_control={"type": "ephemeral"},
        )
        if config.USE_FALLBACKS:
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        return self.client.beta.messages.create(**kwargs)

    def _run_tool(self, block) -> dict:
        handler = self.handlers.get(block.name)
        args = dict(block.input or {})
        try:
            if not handler:
                raise BookingError(f"Unknown tool {block.name}.")
            result = handler(self.ctx, **args)
            is_error = False
        except BookingError as e:
            result, is_error = {"error": str(e)}, True
        except TypeError as e:  # bad or missing arguments
            result, is_error = {"error": f"Bad arguments: {e}"}, True
        except Exception:
            log.exception("tool %s failed", block.name)
            result, is_error = {"error": "Internal error. Apologise and offer a callback."}, True
        self._log("tool", f"{block.name}({json.dumps(args, ensure_ascii=False)}) -> "
                          f"{json.dumps(result, ensure_ascii=False)}")
        out = {"type": "tool_result", "tool_use_id": block.id,
               "content": json.dumps(result, ensure_ascii=False)}
        if is_error:
            out["is_error"] = True
        return out

    def _log(self, role: str, text: str) -> None:
        with db.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO message (conversation_id, role, text, created_at) VALUES (?, ?, ?, ?)",
                (self.ctx.conversation_id, role, text, now().strftime(FMT)),
            )
