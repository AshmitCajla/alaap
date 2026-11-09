"""The conversation engine: one LLM tool-use loop over the business's skills.

The model talks; skills decide what is true. Data changes only through skill
tools, and anything a customer cares about needs a read-back and their yes.

To sound like a person rather than a bot, the prompt gives Alaap a name and a speaking style per
channel, tells it who is calling (name, past visits, upcoming bookings), and hands it today's free
time up front so most questions are answered without a tool round trip. Replies can be streamed
sentence by sentence so a call can start speaking before the whole answer is written."""

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from . import billing, config, db, models
from .errors import ToolError
from .llm import LLM, LLMNotConfigured, parse_args
from .scheduling import hours_on, next_open_day
from .skills import REGISTRY, Context, for_business
from .skills.base import normalise_phone
from .spoken import SentenceSplitter
from .state import store
from .timeutil import FMT, WEEKDAYS, now

log = logging.getLogger("alaap.engine")
BYE = re.compile(r"\b(bye|bas|thank|thanks|shukriya|dhanyavaad|dhanyawad|alvida|rakhta|rakhti|chalo|ok bye)\b|"
                 r"बस|धन्यवाद|शुक्रिया|ਧੰਨਵਾਦ|ਬੱਸ", re.I)
MAX_TOOL_ROUNDS = 8
# Tools whose success needs no further words: if Alaap already spoke in the same message (the read-back,
# "ho gaya ji"), the turn ends without a second LLM request. That halves the wait on most turns.
# Orders are left out on purpose: their total must come from the tool, not from the model.
# confirm_action is left out too: after "Ji, ho gaya!" the caller must hear their booking/order number, which only
# exists once the tool has run.
SELF_SPOKEN_OK = {"prepare_booking", "prepare_reschedule", "prepare_cancellation", "prepare_order_cancellation",
                  "end_call", "save_lead", "request_callback", "log_complaint",
                  "send_payment_link", "update_order_status", "set_stock"}

FEMALE_VOICES = {"Shivani", "Lakshmi", "Kalpana", "Chetana", "Vasudha", "Riyaa", "Tarika", "Nalini", "Kaveri",
                 "Bhavna", "Yashvi", "Urmila", "Poorvi", "Mehuli"}

PERSONA = """You are {assistant}, who answers the phone, WhatsApp and website chat for {name}, a {kind} in {city}.
You are the shop's AI assistant. Never pretend to be human: if someone asks whether you are a robot or AI, say \
warmly and plainly that you are {name}'s AI assistant, and that you can still help or get {owner} to call back.
Talk about yourself as a {gender} ({verbs}).

Language: reply in the language and script of the customer's latest message (Hindi, Punjabi, English, Tamil or a \
mix, with the same mix of English words they use). If they write Hindi or Punjabi in Roman letters, reply in Roman \
letters. If they write plain English sentences, reply fully in English, even though you greeted them in Hindi.
Understand Indian time words exactly: "saade 6" = 6:30, "sava 6" = 6:15, "paune 6" = 5:45, "dedh" = 1:30, \
"dhaai" = 2:30; "shaam/raat" = PM, "subah" = AM, "dopahar" = about 12-3 PM.

{style}

Ground rules:
- Use only the business profile, the free time below and tool results. Never invent prices, items, services, \
staff, slots, offers, orders or bookings.
- Data changes only through tools. Before anything is saved, read it back in one natural sentence and wait for a \
clear yes; then call confirm_action.
- Use ids from the profile in tool calls; never say ids aloud (booking and order numbers are fine).
- If a tool returns an error, explain it simply and offer the nearest alternative.
- If you can't help, offer a callback from {owner}.
- Never say you have noted, logged, saved, alerted {owner} or passed something on unless you call the matching \
tool (log_complaint, save_lead, request_callback, ...) in that same reply. Saying "main note kar leti hoon" means \
calling the tool right then.
- When the customer's mobile number is already known (caller ID), never ask for it. Log a complaint as soon as you \
know what went wrong, and save a lead as soon as you know what they need; a name is nice but never required, add \
it later if they give it.
"""

VOICE_STYLE = """This is a live phone call. Sound like a warm, experienced receptionist from {city}, not a bot:
- Keep turns short: usually one sentence, at most two, under about 25 words. Let the caller talk.
- Use the small words people use: "ji", "haan ji", "achha", "bilkul", "theek hai", "zaroor". Vary them; never start \
two replies the same way. No formal phrases like "How may I assist you" or "aapki kya sahayata kar sakti hoon".
- Don't repeat back what the caller just said, except in the final read-back before saving.
- If you need to check something, you may first say a few words ("Ek second ji, dekh leti hoon.") and then call \
the tool.
- Offer at most two options at a time ("5 baje ya 6:30?").
- The read-back is one easy sentence: "Toh kal shaam 6:30 baje, Gurpreet ke saath haircut, Rs 200. \
Pakka kar doon?" Say it in the same message as the prepare_* call (for orders, wait for prepare_order's total).
- When the customer says yes, say a short "Ji, ho gaya!" style line in the same message as confirm_action; once it \
returns, give them the booking or order number in one short sentence ("Booking number 8725 hai, WhatsApp par \
confirmation aa jayega.").
- Write every number in digits, copied exactly from the profile or tool result: prices "Rs 200", times "6:30", \
booking and order numbers "8725". They are turned into natural spoken words automatically ("do sau rupaye", \
"saade chhe baje", "aath saat do paanch"), so never spell numbers out yourself: that's how digits get wrong.
- If you didn't catch something, ask the way a person would: "Maaf kijiye, line thodi saaf nahi thi, phir se \
bataenge?" If the caller sounds upset, slow down and apologise once, sincerely.
- Use the caller's name now and then once you know it, not in every sentence.
- When everything is done and the caller says bye or thanks, say a short warm goodbye AND call end_call in the \
same reply.
- Don't ask "aur kuch?" after every answer; ask it once, when the main task is done.
- You have already greeted the caller; never say hello / Sat Sri Akal / Namaste again until the goodbye.
- Say days the way people do: "aaj", "kal", "parson", "Saturday ko". Never read out full dates like \
"Saturday, November 7th" unless the caller asks for the date."""

TEXT_STYLE = """This is a {channel} chat. Write like a friendly person on WhatsApp: one to three short lines, \
no headings or bullet lists, no markdown. Use the customer's name now and then. Numbers can be digits here."""

OWNER_PERSONA = """You are {assistant}, the AI front desk of {name}. Right now you are talking to the owner, {owner}, \
not a customer. Be brief and practical, like a trusted manager, in the owner's language (Hindi/Punjabi/English/ \
Hinglish). No markdown. Read numbers clearly. Talk about yourself as a {gender} ({verbs}).
"""

CONFIRM_TOOL = {"type": "function", "function": {
    "name": "confirm_action",
    "description": "Save the action prepared by a prepare_* tool. Only after the customer said yes to the read-back.",
    "parameters": {"type": "object", "properties": {"action_id": {"type": "string"}}, "required": ["action_id"]}}}

END_CALL_TOOL = {"type": "function", "function": {
    "name": "end_call",
    "description": "Hang up after you have said goodbye, when the caller has nothing else.",
    "parameters": {"type": "object", "properties": {}}}}


@dataclass
class Reply:
    text: str
    handoff: bool = False
    end: bool = False
    conversation_id: int | None = None


def is_female(biz: models.Business) -> bool:
    return (biz.voice or config.GNANI_TTS_VOICE) in FEMALE_VOICES


def assistant_name(biz: models.Business) -> str:
    return biz.assistant_name or ("Riya" if is_female(biz) else "Arjun")


def greeting(biz: models.Business, channel: str, owner: bool = False, customer: str | None = None) -> str:
    me = assistant_name(biz)
    speaking = "bol rahi hoon" if is_female(biz) else "bol raha hoon"
    if owner:
        return f"Namaste {biz.owner_name or 'ji'}! Bataiye, aaj kya dekhna hai?"
    punjabi = biz.languages.lower().startswith("punjabi")
    who = f" {customer} ji" if customer else " ji"
    hello = f"Sat Sri Akal{who}!" if punjabi else f"Namaste{who}!"
    if channel == "phone":
        # Calls are recorded (see Risks in the plan), so say so - briefly, the way a person would.
        ask = "Bataiye, aaj kya karwana hai?" if customer else "Bataiye, kya seva karoon?"
        return f"{hello} {biz.name} se {me} {speaking}, call record ho rahi hai. {ask}"
    return f"{hello} Main {me}, {biz.name} se. Bataiye, kaise madad karoon?"


def profile_text(biz: models.Business, today) -> str:
    lines = [f"Name: {biz.name} ({biz.kind})", f"Address: {biz.address or '-'}, {biz.city or ''}",
             f"Phone: {biz.phone or '-'}", f"Languages: {biz.languages}"]
    if biz.about:
        lines.append(f"About: {biz.about}")
    hours = {h.weekday: h for h in biz.hours}
    lines.append("Opening hours: " + "; ".join(
        f"{d}: {hours[i].opens}-{hours[i].closes}" if i in hours else f"{d}: closed" for i, d in enumerate(WEEKDAYS)))
    closed = [c for c in biz.closures if c.day >= today]
    if closed:
        lines.append("Closed on: " + ", ".join(f"{c.day:%a %d %b}" + (f" ({c.note})" if c.note else "") for c in closed))
    if biz.faqs:
        lines.append("Other facts:")
        lines += [f"  {f.question}: {f.answer}" for f in biz.faqs]
    return "\n".join(lines)


def free_time(s, biz: models.Business, current: datetime) -> str:
    """Each staff member's free windows today and on the next open day, so the model can offer times
    without calling a tool. prepare_booking still checks every booking."""
    days = [current.date()]
    nxt = next_open_day(s, biz, current.date())
    if nxt:
        days.append(nxt)
    earliest = current + timedelta(minutes=config.MIN_LEAD_MINUTES)
    lines = []
    for day in days:
        hours = hours_on(s, biz, day)
        label = f"{WEEKDAYS[day.weekday()]} {day:%d %b}" + (" (today)" if day == current.date() else "")
        if not hours:
            lines.append(f"{label}: closed")
            continue
        per_staff = []
        for person in biz.staff:
            if not person.active:
                continue
            booked = s.scalars(select(models.Appointment).where(
                models.Appointment.staff_id == person.id, models.Appointment.status == "booked",
                models.Appointment.start_at < hours[1], models.Appointment.end_at > hours[0])
                .order_by(models.Appointment.start_at)).all()
            t, windows = max(hours[0], earliest), []
            # round up to the next 15 minutes
            t += timedelta(minutes=(-t.minute) % 15)
            for a in booked + [None]:
                stop = a.start_at if a else hours[1]
                if stop - t >= timedelta(minutes=15):
                    windows.append(f"{t:%H:%M}-{stop:%H:%M}")
                if a:
                    t = max(t, a.end_at)
            per_staff.append(f"{person.name}: {', '.join(windows) or 'fully booked'}")
        lines.append(f"{label}: " + "; ".join(per_staff))
    return "\n".join(lines)


def customer_memory(s, biz: models.Business, phone: str, current: datetime) -> str:
    c = s.scalar(select(models.Customer).where(models.Customer.business_id == biz.id, models.Customer.phone == phone))
    if not c:
        return "New caller (not in our records)."
    out = [f"Returning customer: {c.name}."]
    past = s.scalars(select(models.Appointment).where(
        models.Appointment.customer_id == c.id, models.Appointment.start_at < current,
        models.Appointment.status.in_(("booked", "done"))).order_by(models.Appointment.start_at.desc()).limit(3)).all()
    if past:
        out.append("Recent visits: " + "; ".join(f"{a.service.name} with {a.staff.name} on {a.start_at:%d %b}"
                                                 for a in past) + ". Offer the same service/staff if it fits.")
    upcoming = s.scalars(select(models.Appointment).where(
        models.Appointment.customer_id == c.id, models.Appointment.start_at >= current,
        models.Appointment.status == "booked").order_by(models.Appointment.start_at)).all()
    if upcoming:
        out.append("Upcoming bookings: " + "; ".join(f"ref {a.ref}: {a.service.name} with {a.staff.name}, "
                                                     f"{a.start_at:%a %d %b %H:%M}" for a in upcoming) + ".")
    last_order = s.scalar(select(models.Order).where(models.Order.customer_id == c.id)
                          .order_by(models.Order.id.desc()).limit(1))
    if last_order:
        out.append(f"Last order {last_order.ref} ({last_order.created_at:%d %b}, {last_order.status}): "
                   + ", ".join(f"{i.qty} x {i.name}" for i in last_order.items)
                   + f". Address: {last_order.address}, {last_order.pincode}. Offer to repeat it if it fits.")
    return " ".join(out)


def clean_text(text: str) -> str:
    text = re.sub(r"[*#`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


class Engine:
    def __init__(self, llm: LLM | None = None, state=None):
        self.llm = llm or LLM()
        self.state = state or store()

    # ---------- lifecycle ----------

    def start(self, business_id: int, channel: str = "web", caller_phone: str | None = None,
              owner: bool = False, verified: bool = False) -> Reply:
        """verified=True only when caller_phone comes from real caller ID (Exotel, WhatsApp)."""
        phone = normalise_phone(caller_phone)
        with db.session() as s:
            biz = s.get(models.Business, business_id)
            if not biz or not biz.active:
                raise LookupError(f"No active business {business_id}")
            stamp = now(biz.timezone)
            known = phone and verified and not owner and s.scalar(select(models.Customer.name).where(
                models.Customer.business_id == biz.id, models.Customer.phone == phone))
            conv = models.Conversation(business_id=biz.id, channel="owner" if owner else channel,
                                       caller_phone=phone, phone_verified=bool(phone and verified), is_owner=owner,
                                       started_at=stamp, last_at=stamp)
            s.add(conv)
            s.flush()
            hello = greeting(biz, channel, owner, known or None)
            s.add(models.Message(conversation_id=conv.id, role="alaap", text=hello, created_at=stamp))
            ctx = Context(business_id=biz.id, conversation_id=conv.id, tz=biz.timezone, channel=channel,
                          caller_phone=phone, phone_verified=bool(phone and verified), is_owner=owner)
            cid = conv.id
        self.state.set(f"conv:{cid}", {"ctx": ctx.to_dict(), "messages": [{"role": "assistant", "content": hello}]})
        return Reply(hello, conversation_id=cid)

    def end(self, conversation_id: int, call_seconds: int = 0) -> None:
        with db.session() as s:
            conv = s.get(models.Conversation, conversation_id)
            if conv:
                biz = s.get(models.Business, conv.business_id)
                conv.ended_at = now(biz.timezone)
                conv.call_seconds = max(conv.call_seconds, int(call_seconds))
        self.state.delete(f"conv:{conversation_id}")

    # ---------- a turn ----------

    def reply(self, conversation_id: int, text: str, on_sentence=None) -> Reply:
        """Answer one customer message. With on_sentence(str), each sentence is passed on as soon as the
        model has written it (used by live calls to start speaking early)."""
        text = (text or "").strip()
        if not text:
            return Reply("", conversation_id=conversation_id)
        t0 = time.perf_counter()
        saved = self.state.get(f"conv:{conversation_id}") or self._rebuild(conversation_id)
        ctx = Context.from_dict(saved["ctx"])
        if not ctx.is_owner:
            with db.session() as s:
                biz = s.get(models.Business, ctx.business_id)
                if not billing.can_serve(biz):  # plan lapsed and ENFORCE_BILLING is on
                    notice = billing.suspended_message(biz)
                    if on_sentence:
                        on_sentence(notice)
                    return Reply(notice, end=True, conversation_id=conversation_id)
        history: list[dict] = saved["messages"]
        ctx.user_turn += 1
        self._log(ctx, "customer", text)
        history.append({"role": "user", "content": text})

        system, tools, handlers, actions = self._setup(ctx)
        spoken: list[str] = []

        def say(sentence: str) -> None:
            sentence = clean_text(sentence)
            if sentence:
                spoken.append(sentence)
                if on_sentence:
                    on_sentence(sentence)

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                splitter = SentenceSplitter()
                stream = (lambda chunk: [say(x) for x in splitter.feed(chunk)]) if on_sentence else None
                msg = self.llm.chat([{"role": "system", "content": system}] + history, tools, on_text=stream)
                if not msg.get("content") and not msg.get("tool_calls"):
                    # Free-tier models occasionally return nothing; try once more, then another model.
                    log.warning("empty LLM reply; retrying")
                    msg = self.llm.chat([{"role": "system", "content": system}] + history, tools, on_text=stream)
                    if not msg.get("content") and not msg.get("tool_calls") and len(self.llm.models) > 1:
                        self.llm.model = next(m for m in self.llm.models if m != self.llm.model)
                        msg = self.llm.chat([{"role": "system", "content": system}] + history, tools, on_text=stream)
                history.append(msg)
                if on_sentence:
                    for rest in splitter.flush():
                        say(rest)
                elif msg.get("content"):
                    say(msg["content"])
                calls = msg.get("tool_calls") or []
                if not calls:
                    break
                results = [self._refuse_hangup(ctx, call) if self._early_hangup(call, calls, spoken, text)
                           else self._run_tool(ctx, call, handlers, actions) for call in calls]
                history += results
                if ctx.end_call:
                    break
                names = {c.get("function", {}).get("name") for c in calls}
                if msg.get("content") and names <= SELF_SPOKEN_OK and \
                        not any('"error"' in r["content"][:12] for r in results):
                    break  # already said what needed saying
            else:
                say("Ek minute, main owner se aapki baat karwati hoon.")
                ctx.handoff = True
        except LLMNotConfigured as e:
            log.warning("%s", e)
            self._count_error(ctx)
            say(f"[Alaap is not connected to an LLM yet: {e}]")
            history.append({"role": "assistant", "content": spoken[-1]})
        except Exception:
            log.exception("LLM turn failed")
            self._count_error(ctx)
            say("Maaf kijiye, line par thodi dikkat aa gayi. Kya aap phir se bataenge?")
            history.append({"role": "assistant", "content": spoken[-1]})

        answer = " ".join(spoken).strip()
        if not answer:
            say("Maaf kijiye, ek baar phir se bataenge?") if not ctx.end_call else None
            answer = " ".join(spoken).strip()
        latency = int((time.perf_counter() - t0) * 1000)
        self._log(ctx, "alaap", answer or "(call ended)", latency)
        self._save_outcome(ctx)
        self.state.set(f"conv:{conversation_id}", {"ctx": ctx.to_dict(), "messages": history[-60:]})
        return Reply(answer, handoff=ctx.handoff, end=ctx.end_call, conversation_id=conversation_id)

    # ---------- internals ----------

    @staticmethod
    def _early_hangup(call: dict, calls: list, spoken: list, text: str) -> bool:
        """end_call only when the caller is saying goodbye, and never in the same step as another action (e.g. a silent
        confirm-and-hang-up that never tells the caller their booking number, or "milte hain!" and gone before the
        caller had finished)."""
        if call.get("function", {}).get("name") != "end_call":
            return False
        return len(calls) > 1 or not BYE.search(text or "")

    def _refuse_hangup(self, ctx: Context, call: dict) -> dict:
        result = {"error": "Don't hang up yet: the caller hasn't said bye. Tell them the result if you haven't "
                           "(e.g. 'Ho gaya ji, booking number ...') and ask if there's anything else."}
        self._log(ctx, "tool", f"end_call({{}}) -> {json.dumps(result, ensure_ascii=False)}")
        return {"role": "tool", "tool_call_id": call["id"], "name": "end_call", "content": json.dumps(result)}

    def _setup(self, ctx: Context):
        with db.session() as s:
            biz = s.get(models.Business, ctx.business_id)
            active = for_business(biz.skill_list(), biz.plan, owner_mode=ctx.is_owner)
            current = now(biz.timezone)
            female = is_female(biz)
            words = dict(assistant=assistant_name(biz), name=biz.name, owner=biz.owner_name or "the owner",
                         gender="woman" if female else "man",
                         verbs="karti hoon, bol rahi hoon, dekh leti hoon" if female else
                               "karta hoon, bol raha hoon, dekh leta hoon")
            if ctx.is_owner:
                parts = [OWNER_PERSONA.format(**words)]
            else:
                style = VOICE_STYLE if ctx.channel == "phone" else TEXT_STYLE
                parts = [PERSONA.format(kind=biz.kind.replace("_", " "), city=biz.city or "",
                                        style=style.format(city=biz.city or "your town", channel=ctx.channel), **words)]
            parts += [sk.prompt() for sk in active if sk.tools]
            parts.append("# Business profile\n" + profile_text(biz, current.date()))
            parts += [sk.profile(biz) for sk in active if sk.profile]
            if any(sk.key == "appointments" for sk in active) and biz.staff:
                parts.append("# Free time (staff: free windows; offer starts inside these, the booking must fit "
                             "before the window ends)\n" + free_time(s, biz, current))
            if ctx.caller_phone and ctx.phone_verified:
                caller = f"Caller's mobile (verified caller ID): {ctx.caller_phone}."
            elif ctx.caller_phone:
                caller = f"Caller gave the mobile {ctx.caller_phone} (not verified; fine for new bookings)."
            else:
                caller = "Caller's mobile is unknown; ask for it when it's needed."
            if ctx.caller_phone and ctx.phone_verified and not ctx.is_owner:
                caller += " " + customer_memory(s, biz, ctx.caller_phone, current)
            parts.append(f"# This conversation\nNow: {current.strftime(FMT)} ({WEEKDAYS[current.weekday()]}). "
                         f"Channel: {ctx.channel}. {caller}")
        tools = [t.schema() for sk in active for t in sk.tools]
        handlers = {t.name: t.handler for sk in active for t in sk.tools}
        actions = {k: fn for sk in active for k, fn in sk.actions.items()}
        if actions:
            tools.append(CONFIRM_TOOL)
        if ctx.channel == "phone":
            tools.append(END_CALL_TOOL)
        return "\n\n".join(parts), tools, handlers, actions

    def _run_tool(self, ctx: Context, call: dict, handlers: dict, actions: dict) -> dict:
        fn = call.get("function", {})
        name = fn.get("name", "")
        args = parse_args(fn.get("arguments"))
        try:
            if "__invalid__" in args:
                raise ToolError("Arguments were not valid JSON. Call the tool again.")
            if name == "end_call":
                ctx.end_call = True
                result = {"done": "ending call"}
            else:
                with db.session() as s:
                    if name == "confirm_action":
                        result = self._confirm(ctx, s, args.get("action_id", ""), actions)
                    elif name in handlers:
                        args = {k: v for k, v in args.items() if v is not None}
                        result = handlers[name](ctx, s, **args)
                    else:
                        raise ToolError(f"Unknown tool {name}.")
        except ToolError as e:
            result = {"error": str(e)}
        except TypeError as e:
            result = {"error": f"Bad arguments: {e}"}
        except Exception:
            log.exception("tool %s failed", name)
            self._count_error(ctx)
            result = {"error": "Internal error. Apologise and offer a callback from the owner."}
        self._log(ctx, "tool", f"{name}({json.dumps(args, ensure_ascii=False, default=str)}) -> "
                               f"{json.dumps(result, ensure_ascii=False, default=str)}")
        return {"role": "tool", "tool_call_id": call["id"], "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str)}

    @staticmethod
    def _confirm(ctx: Context, s, action_id: str, actions: dict) -> dict:
        action = ctx.pending.get(action_id)
        if not action:
            raise ToolError("Unknown or expired action_id. Prepare the action again.")
        if ctx.user_turn <= action["user_turn"]:
            raise ToolError("The customer has not replied to the read-back yet. Read it back and wait for their yes.")
        fn = actions.get(action["kind"])
        if not fn:
            raise ToolError("That action is not available here.")
        result = fn(ctx, s, action)
        ctx.pending.clear()
        return result

    def _rebuild(self, conversation_id: int) -> dict:
        """State expired (or the server restarted): rebuild from the transcript."""
        with db.session() as s:
            conv = s.get(models.Conversation, conversation_id)
            if not conv:
                raise LookupError(f"No conversation {conversation_id}")
            biz = s.get(models.Business, conv.business_id)
            msgs = [{"role": "user" if m.role == "customer" else "assistant", "content": m.text}
                    for m in conv.messages if m.role in ("customer", "alaap")]
            turns = sum(1 for m in conv.messages if m.role == "customer")
            ctx = Context(business_id=conv.business_id, conversation_id=conv.id, tz=biz.timezone,
                          channel="web" if conv.channel == "owner" else conv.channel,
                          caller_phone=conv.caller_phone, phone_verified=bool(conv.phone_verified),
                          is_owner=conv.is_owner, user_turn=turns,
                          outcome=conv.outcome, handoff=conv.handoff)
        return {"ctx": ctx.to_dict(), "messages": msgs}

    def _log(self, ctx: Context, role: str, text: str, latency_ms: int | None = None) -> None:
        with db.session() as s:
            stamp = now(ctx.tz)
            s.add(models.Message(conversation_id=ctx.conversation_id, role=role, text=text, latency_ms=latency_ms,
                                 created_at=stamp))
            conv = s.get(models.Conversation, ctx.conversation_id)
            conv.last_at = stamp

    def _save_outcome(self, ctx: Context) -> None:
        with db.session() as s:
            conv = s.get(models.Conversation, ctx.conversation_id)
            conv.outcome, conv.handoff = ctx.outcome, ctx.handoff

    def _count_error(self, ctx: Context) -> None:
        with db.session() as s:
            conv = s.get(models.Conversation, ctx.conversation_id)
            conv.errors += 1


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


__all__ = ["Engine", "Reply", "get_engine", "REGISTRY"]
