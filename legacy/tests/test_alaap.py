"""Tests for the parts that must never be wrong: slots, validation and the
read-back-before-write rule. The engine is tested with a scripted fake model."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from alaap import db, seed
from alaap.engine import Conversation
from alaap.scheduling import BookingError, check_booking, free_slots
from alaap.skills import appointments as ap
from alaap.skills.base import Context


def next_weekday(weekday: int, min_days: int = 2) -> date:
    d = date.today() + timedelta(days=min_days)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "t.db"
    biz = seed.seed(path)
    with db.connect(path) as conn:
        conv = conn.execute("INSERT INTO conversation (business_id, channel, started_at) VALUES (?, 'web', 'x')",
                            (biz,)).lastrowid
        ids = {r["name"]: r["id"] for r in db.rows(conn, "SELECT id, name FROM service")}
        staff = {r["name"]: r["id"] for r in db.rows(conn, "SELECT id, name FROM staff")}
    ctx = Context(business_id=biz, conversation_id=conv, caller_phone="+91 98765 43210", db_path=path)
    return SimpleNamespace(path=path, biz=biz, ctx=ctx, svc=ids, staff=staff)


TUE = next_weekday(1)
MON = next_weekday(0)


def at(d: date, hm: str) -> str:
    return f"{d.isoformat()} {hm}"


def book(env, start, service="Haircut (men)", staff=None):
    env.ctx.user_turn += 1
    r = ap.prepare_booking(env.ctx, "Aman", env.svc[service], start,
                           staff_id=env.staff[staff] if staff else None)
    env.ctx.user_turn += 1  # customer says yes
    return ap.confirm_action(env.ctx, r["action_id"])


def test_closed_on_monday(env):
    with db.connect(env.path) as conn:
        assert free_slots(conn, env.biz, env.svc["Facial"], MON)["closed"]
        with pytest.raises(BookingError, match="closed"):
            check_booking(conn, env.biz, env.svc["Facial"], None, datetime.fromisoformat(at(MON, "11:00")))


def test_outside_hours_and_past(env):
    with db.connect(env.path) as conn:
        with pytest.raises(BookingError, match="outside opening hours"):
            check_booking(conn, env.biz, env.svc["Hair colour"], None, datetime.fromisoformat(at(TUE, "19:00")))
        with pytest.raises(BookingError, match="passed"):
            check_booking(conn, env.biz, env.svc["Facial"], None, datetime(2020, 1, 7, 11, 0))


def test_staff_must_do_service(env):
    with pytest.raises(BookingError, match="does not do"):
        ap.prepare_booking(env.ctx, "Aman", env.svc["Facial"], at(TUE, "11:00"), staff_id=env.staff["Gurpreet"])


def test_unknown_service(env):
    with pytest.raises(BookingError, match="no service"):
        ap.prepare_booking(env.ctx, "Aman", 999, at(TUE, "11:00"))


def test_confirm_needs_customer_reply(env):
    env.ctx.user_turn = 1
    r = ap.prepare_booking(env.ctx, "Aman", env.svc["Facial"], at(TUE, "11:00"))
    with pytest.raises(BookingError, match="not replied"):
        ap.confirm_action(env.ctx, r["action_id"])
    env.ctx.user_turn = 2
    assert ap.confirm_action(env.ctx, r["action_id"])["done"] == "booked"


def test_booking_queues_whatsapp_and_blocks_slot(env):
    res = book(env, at(TUE, "11:00"), "Facial")
    with db.connect(env.path) as conn:
        appt = db.row(conn, "SELECT * FROM appointment WHERE ref = ?", res["ref"])
        assert appt["end_at"] == at(TUE, "12:00")
        kinds = [r["kind"] for r in db.rows(conn, "SELECT kind FROM outbox WHERE appointment_id = ?", appt["id"])]
        assert kinds == ["confirmation", "reminder"]
        slots = free_slots(conn, env.biz, env.svc["Facial"], TUE)["slots"]
        assert all(not (at(TUE, "10:15") <= s["start"] < at(TUE, "12:00")) for s in slots)
    # Simran is the only one who does facials, so the overlapping slot is gone.
    with pytest.raises(BookingError, match="not free"):
        ap.prepare_booking(env.ctx, "Riya", env.svc["Facial"], at(TUE, "11:30"))


def test_any_staff_picks_free_one(env):
    first = book(env, at(TUE, "15:00"), staff="Gurpreet")
    second = book(env, at(TUE, "15:00"))
    with db.connect(env.path) as conn:
        names = [r["name"] for r in db.rows(
            conn, "SELECT st.name FROM appointment a JOIN staff st ON st.id = a.staff_id"
                  " WHERE a.ref IN (?, ?) ORDER BY a.id", first["ref"], second["ref"])]
    assert names == ["Gurpreet", "Raju"]


def test_slot_taken_between_prepare_and_confirm(env):
    env.ctx.user_turn = 1
    r = ap.prepare_booking(env.ctx, "Aman", env.svc["Facial"], at(TUE, "13:00"))
    other = Context(business_id=env.biz, conversation_id=env.ctx.conversation_id,
                    caller_phone="9999999999", db_path=env.path)
    book(SimpleNamespace(**{**vars(env), "ctx": other}), at(TUE, "13:00"), "Facial")
    env.ctx.user_turn = 2
    with pytest.raises(BookingError, match="not free"):
        ap.confirm_action(env.ctx, r["action_id"])


def test_reschedule_and_cancel(env):
    ref = book(env, at(TUE, "11:00"))["ref"]
    assert ap.find_my_appointments(env.ctx)["upcoming"][0]["ref"] == ref
    env.ctx.user_turn += 1
    r = ap.prepare_reschedule(env.ctx, ref, at(TUE, "16:00"))
    env.ctx.user_turn += 1
    assert ap.confirm_action(env.ctx, r["action_id"])["done"] == "rescheduled"
    env.ctx.user_turn += 1
    r = ap.prepare_cancellation(env.ctx, ref)
    env.ctx.user_turn += 1
    assert ap.confirm_action(env.ctx, r["action_id"])["done"] == "cancelled"
    with db.connect(env.path) as conn:
        statuses = db.rows(conn, "SELECT kind, status FROM outbox WHERE kind = 'reminder'")
        assert all(s["status"] == "cancelled" for s in statuses)
    assert ap.find_my_appointments(env.ctx)["upcoming"] == []


def test_cannot_touch_someone_elses_booking(env):
    ref = book(env, at(TUE, "11:00"))["ref"]
    with pytest.raises(BookingError, match="No booking"):
        ap.prepare_cancellation(env.ctx, ref, phone="9000000000")


# ---------- engine with a fake model ----------

def text(t):
    return SimpleNamespace(type="text", text=t)


def tool(id_, name, **inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        content, stop = self.script.pop(0)
        return SimpleNamespace(content=content, stop_reason=stop)


def test_engine_reads_back_then_books(env):
    start = at(TUE, "17:00")
    fake = FakeClient([
        # turn 1: prepare, then try to confirm in the same turn (must be refused)
        ([tool("t1", "prepare_booking", customer_name="Aman", service_id=env.svc["Haircut (men)"], start=start)],
         "tool_use"),
        ([tool("t2", "confirm_action", action_id="A1")], "tool_use"),
        ([text("Haircut, Gurpreet ke saath, Tuesday shaam 5 baje, 200 rupaye. Confirm karoon?")], "end_turn"),
        # turn 2: customer said yes
        ([tool("t3", "confirm_action", action_id="A1")], "tool_use"),
        ([text("Ho gaya ji!")], "end_turn"),
    ])
    conv = Conversation(env.biz, channel="phone", caller_phone="9876543210", db_path=env.path, client=fake)
    assert "Confirm" in conv.reply("Tuesday shaam 5 baje haircut")
    refused = fake.calls[2]["messages"][-1]["content"][0]
    assert refused["is_error"] and "not replied" in refused["content"]
    with db.connect(env.path) as conn:
        assert db.row(conn, "SELECT COUNT(*) n FROM appointment")["n"] == 0
    assert conv.reply("haan ji") == "Ho gaya ji!"
    with db.connect(env.path) as conn:
        assert db.row(conn, "SELECT start_at FROM appointment")["start_at"] == start
        assert db.row(conn, "SELECT COUNT(*) n FROM message WHERE role = 'tool'")["n"] == 3
    assert fake.calls[0]["tools"] and "Business profile" in fake.calls[0]["system"][0]["text"]
