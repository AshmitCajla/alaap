"""Tests for what must never be wrong: slots, orders, the read-back-before-write rule,
owner actions, follow-ups and the API. The LLM is a scripted fake."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from alaap import db, jobs, models, seed, timeutil
from alaap.engine import Engine
from alaap.errors import ToolError
from alaap.skills import appointments as ap
from alaap.skills import leads, orders, owner
from alaap.skills.base import Context
from alaap.state import MemoryStore

NOW = datetime(2026, 11, 10, 9, 0)  # a Tuesday
SALON, KIRANA, COACHING = 1, 2, 3


@pytest.fixture(autouse=True)
def database(tmp_path):
    db.configure(f"sqlite:///{tmp_path / 't.db'}")
    timeutil.freeze(NOW)
    seed.seed()
    yield
    timeutil.freeze(None)


def ctx(biz=SALON, phone="9876543210", **kw):
    with db.session() as s:
        conv = models.Conversation(business_id=biz, channel=kw.pop("channel", "web"), caller_phone=phone)
        s.add(conv)
        s.flush()
        cid = conv.id
    return Context(business_id=biz, conversation_id=cid, caller_phone=phone, **kw)


def call(fn, c, **args):
    with db.session() as s:
        return fn(c, s, **args)


def confirm(c, result):
    """Simulate the customer saying yes, then run the stashed action like confirm_action does."""
    c.user_turn += 1
    action = c.pending[result["action_id"]]
    assert c.user_turn > action["user_turn"]
    from alaap.skills import REGISTRY
    fn = {k: f for sk in REGISTRY.values() for k, f in sk.actions.items()}[action["kind"]]
    with db.session() as s:
        return fn(c, s, action)


def ids(model, name, biz):
    with db.session() as s:
        return s.scalar(select(model.id).where(model.name == name, model.business_id == biz))


# ---------- appointments ----------

def test_slots_respect_hours_closures_and_lead_time():
    c = ctx()
    facial = ids(models.Service, "Facial", SALON)
    r = call(ap.find_free_slots, c, service_id=facial, date="2026-11-10")
    assert r["slots"][0]["start"] == "2026-11-10 10:00"
    monday = call(ap.find_free_slots, c, service_id=facial, date="2026-11-16")
    assert monday["closed"] and monday["next_open_day"] == "2026-11-17"
    with pytest.raises(ToolError, match="outside opening hours"):
        call(ap.prepare_booking, c, customer_name="A", service_id=ids(models.Service, "Hair colour", SALON),
             start="2026-11-10 19:00")
    with pytest.raises(ToolError, match="passed"):
        call(ap.prepare_booking, c, customer_name="A", service_id=facial, start="2026-11-10 08:30")


def test_booking_flow_double_booking_and_messages():
    c = ctx()
    facial = ids(models.Service, "Facial", SALON)
    c.user_turn = 1
    r = call(ap.prepare_booking, c, customer_name="Aman", service_id=facial, start="2026-11-10 12:00")
    done = confirm(c, r)
    assert done["done"] == "booked" and c.outcome == "booked"
    with db.session() as s:
        kinds = [o.kind for o in s.scalars(select(models.Outbox).order_by(models.Outbox.id))]
    assert kinds == ["confirmation", "reminder"]
    other = ctx(phone="9999999999")
    with pytest.raises(ToolError, match="not free"):  # only Simran does facials
        call(ap.prepare_booking, other, customer_name="Riya", service_id=facial, start="2026-11-10 12:30")


def test_reschedule_cancel_and_ownership():
    c = ctx()
    cut = ids(models.Service, "Haircut (men)", SALON)
    ref = confirm(c, call(ap.prepare_booking, c, customer_name="Aman", service_id=cut, start="2026-11-11 15:00"))["ref"]
    with pytest.raises(ToolError, match="No booking"):
        call(ap.prepare_cancellation, ctx(phone="9000000000"), appointment_ref=ref)
    assert confirm(c, call(ap.prepare_reschedule, c, appointment_ref=ref, new_start="2026-11-11 17:00"))["done"] == "rescheduled"
    assert confirm(c, call(ap.prepare_cancellation, c, appointment_ref=ref))["done"] == "cancelled"
    with db.session() as s:
        assert all(o.status == "cancelled" for o in s.scalars(select(models.Outbox).where(models.Outbox.kind == "reminder")))


# ---------- orders ----------

def test_catalog_search_handles_hinglish():
    c = ctx(KIRANA)
    names = [m["name"] for m in call(orders.search_catalog, c, query="aata")["matches"]]
    assert names[0] == "Aashirvaad Atta"
    assert call(orders.search_catalog, c, query="cheeni")["matches"][0]["name"] == "Sugar"
    assert call(orders.search_catalog, c, query="iphone")["matches"] == []


def test_order_flow_stock_pincode_and_payment():
    c = ctx(KIRANA)
    atta = ids(models.Product, "Aashirvaad Atta", KIRANA)
    with pytest.raises(ToolError, match="not in the delivery area"):
        call(orders.check_delivery, c, pincode="110001")
    d = call(orders.check_delivery, c, pincode="147002")
    assert d["delivery_fee_inr"] == 20 and d["slots"][0]["slots"][0] == "12:00-14:00"  # 9-11 too soon at 9:00
    with pytest.raises(ToolError, match="Minimum order"):
        call(orders.prepare_order, c, items=[{"product_id": atta, "qty": 1}], customer_name="Neha", address="12 Tripuri",
             pincode="147002", slot_date="2026-11-10", slot="12:00-14:00", payment_method="upi")
    c.user_turn = 1
    r = call(orders.prepare_order, c, items=[{"product_id": atta, "qty": 2}], customer_name="Neha",
             address="12 Tripuri", landmark="near water tank", pincode="147002", slot_date="2026-11-10",
             slot="12:00-14:00", payment_method="upi")
    assert "total Rs 590" in r["read_back"] and "Items Rs 570" in r["read_back"]
    done = confirm(c, r)
    assert done["total_inr"] == 590 and c.outcome == "ordered"
    with db.session() as s:
        assert s.get(models.Product, atta).stock == 18
        o = s.scalar(select(models.Order))
        assert o.payment_link_url.endswith(f"/pay/mock/mock_{o.ref}")
        kinds = {x.kind for x in s.scalars(select(models.Outbox))}
    assert {"order_summary", "payment_link", "owner_alert"} <= kinds
    status = call(orders.get_order_status, c)["orders"][0]
    assert status["status"].startswith("received") and status["payment"] == "pending"


def test_out_of_stock_and_unknown_product():
    c = ctx(KIRANA)
    butter = ids(models.Product, "Amul Butter", KIRANA)
    with pytest.raises(ToolError, match="Only 15"):
        call(orders.prepare_order, c, items=[{"product_id": butter, "qty": 16}], customer_name="N", address="x",
             pincode="147001", slot_date="2026-11-10", slot="12:00-14:00", payment_method="cod")
    with pytest.raises(ToolError, match="not in the catalog"):
        call(orders.prepare_order, c, items=[{"product_id": 999, "qty": 1}], customer_name="N", address="x",
             pincode="147001", slot_date="2026-11-10", slot="12:00-14:00", payment_method="cod")


# ---------- leads, owner, follow-ups ----------

def test_lead_scoring_alerts_owner_for_hot_leads():
    c = ctx(COACHING)
    r = call(leads.save_lead, c, need="Class 11 non-medical with JEE foundation for my son", name="Mr Bansal",
             budget="4000 per month", location="Model Town", preferred_time="this week")
    assert r["score"] >= 70
    with db.session() as s:
        assert s.scalar(select(models.Outbox.kind)) == "owner_alert"


def test_owner_close_day_moves_appointments():
    c = ctx()
    cut = ids(models.Service, "Haircut (men)", SALON)
    confirm(c, call(ap.prepare_booking, c, customer_name="Aman", service_id=cut, start="2026-11-11 15:00"))
    o = ctx(phone="9800000001", is_owner=True)
    r = call(owner.prepare_close_day, o, date="2026-11-11", note="family function")
    assert "1 appointment" in r["read_back"] and "Thursday 12 Nov" in r["read_back"]
    assert confirm(o, r) == {"done": "closed", "moved": 1, "cancelled": 0}
    with db.session() as s:
        assert s.scalar(select(models.Appointment.start_at)) == datetime(2026, 11, 12, 15, 0)
    assert call(ap.find_free_slots, c, service_id=cut, date="2026-11-11")["closed"]
    stats = call(owner.get_stats, o)
    assert stats["appointments_booked_by_alaap"] == 1


def test_feedback_after_visit_and_outbox_logging():
    c = ctx()
    cut = ids(models.Service, "Haircut (men)", SALON)
    confirm(c, call(ap.prepare_booking, c, customer_name="Aman", service_id=cut, start="2026-11-10 10:00"))
    timeutil.freeze(datetime(2026, 11, 10, 11, 0))
    jobs.mark_done_and_feedback()
    timeutil.freeze(datetime(2026, 11, 10, 12, 0))
    jobs.send_outbox()
    with db.session() as s:
        assert s.scalar(select(models.Appointment.status)) == "done"
        fb = s.scalar(select(models.Outbox).where(models.Outbox.kind == "feedback"))
        assert fb.status == "logged"  # no WhatsApp token in tests: kept for the dashboard


# ---------- engine ----------

class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def chat(self, messages, tools=None, temperature=None, on_text=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        msg = self.script.pop(0)
        if on_text and msg.get("content"):
            text = msg["content"]
            for i in range(0, len(text), 7):  # stream in small pieces like a real API
                on_text(text[i:i + 7])
        return msg

    def text(self, prompt, system=None):
        return "Aaj ka summary."


def tc(id_, name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def say(text):
    return {"role": "assistant", "content": text}


def test_engine_refuses_confirm_before_customer_reply():
    cut = ids(models.Service, "Haircut (men)", SALON)
    llm = FakeLLM([
        tc("1", "prepare_booking", customer_name="Aman", service_id=cut, start="2026-11-10 17:00"),
        tc("2", "confirm_action", action_id="A1"),
        say("Haircut, Gurpreet ke saath, aaj shaam 5 baje, 200 rupaye. Pakka karoon?"),
        tc("3", "confirm_action", action_id="A1"),
        say("Ho gaya ji! **Booking** number WhatsApp pe aa raha hai."),
    ])
    e = Engine(llm=llm, state=MemoryStore())
    cid = e.start(SALON, "phone", "9876543210").conversation_id
    assert "Pakka" in e.reply(cid, "aaj shaam 5 baje haircut, naam Aman").text
    refused = llm.calls[2]["messages"][-1]
    assert refused["role"] == "tool" and "not replied" in refused["content"]
    with db.session() as s:
        assert s.scalar(select(func.count(models.Appointment.id))) == 0
    assert e.reply(cid, "haan ji").text == "Ho gaya ji! Booking number WhatsApp pe aa raha hai."
    with db.session() as s:
        assert s.scalar(select(func.count(models.Appointment.id))) == 1
        assert s.get(models.Conversation, cid).outcome == "booked"
    names = {t["function"]["name"] for t in llm.calls[0]["tools"]}
    assert {"prepare_booking", "confirm_action", "log_complaint"} <= names and "prepare_order" not in names


def test_engine_rebuilds_lost_state_and_survives_llm_errors():
    class Broken(FakeLLM):
        def chat(self, *a, **k):
            raise RuntimeError("rate limited")
    e = Engine(llm=Broken([]), state=MemoryStore())
    cid = e.start(SALON, "web").conversation_id
    e.state.delete(f"conv:{cid}")
    assert "dikkat" in e.reply(cid, "hello").text
    with db.session() as s:
        assert s.get(models.Conversation, cid).errors == 1


def test_owner_mode_gets_owner_tools_only():
    llm = FakeLLM([say("Aaj 0 orders.")])
    e = Engine(llm=llm, state=MemoryStore())
    cid = e.start(KIRANA, "whatsapp", "9800000002", owner=True).conversation_id
    e.reply(cid, "aaj kitne orders aaye?")
    names = {t["function"]["name"] for t in llm.calls[0]["tools"]}
    assert "get_stats" in names and "prepare_order" not in names


# ---------- API ----------

def test_api_login_overview_and_settings(monkeypatch):
    from alaap.api import main
    from alaap import engine as engine_mod
    monkeypatch.setattr(main.config, "RUN_JOBS", False)
    engine_mod._engine = Engine(llm=FakeLLM([say("Ji, bataiye.")]), state=MemoryStore())
    with TestClient(main.app) as client:
        assert client.post("/api/auth/login", json={"email": "owner@glow.demo", "password": "nope"}).status_code == 401
        token = client.post("/api/auth/login", json={"email": "owner@glow.demo", "password": "demo1234"}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        start = client.post("/api/chat/glow-salon/start", json={}).json()
        r = client.post(f"/api/chat/{start['conversation_id']}/message", json={"text": "hi", "token": start["token"]})
        assert r.json()["text"] == "Ji, bataiye."
        assert client.post(f"/api/chat/{start['conversation_id']}/message",
                           json={"text": "hi", "token": "forged"}).status_code == 403
        ov = client.get("/api/overview", headers=h).json()
        assert ov["conversations"] == 1 and ov["usage"]["plan"] == "pro"
        settings = client.get("/api/settings", headers=h).json()
        services = settings["services"] + [{"name": "Manicure", "duration_min": 40, "price_inr": 350}]
        updated = client.put("/api/settings/services", json=services, headers=h).json()
        assert any(x["name"] == "Manicure" for x in updated["services"])
        assert client.get("/api/settings").status_code == 401
        signup = client.post("/api/auth/signup", json={
            "business_name": "Dr Kaur Dental", "kind": "clinic", "city": "Patiala", "owner_name": "Dr Kaur",
            "owner_phone": "98765 11111", "email": "kaur@example.com", "password": "longpassword"})
        assert signup.json()["slug"] == "dr-kaur-dental"
        assert client.get("/demo/glow-salon").status_code == 200


def test_streaming_reply_speaks_sentence_by_sentence_and_end_call():
    llm = FakeLLM([say("Ji bilkul. Kal shaam saade chhe baje Gurpreet free hain. Pakka kar doon?"),
                   {"role": "assistant", "content": "Dhanyavaad ji, phir milte hain!", "tool_calls": [
                       {"id": "9", "type": "function", "function": {"name": "end_call", "arguments": "{}"}}]}])
    e = Engine(llm=llm, state=MemoryStore())
    cid = e.start(SALON, "phone", "9876543210").conversation_id
    heard = []
    e.reply(cid, "kal shaam haircut", on_sentence=heard.append)
    assert heard == ["Ji bilkul. Kal shaam saade chhe baje Gurpreet free hain.", "Pakka kar doon?"]
    r = e.reply(cid, "nahi bas, thank you", on_sentence=heard.append)
    assert r.end and heard[-1] == "Dhanyavaad ji, phir milte hain!"
    system = llm.calls[0]["messages"][0]["content"]
    assert "Riya" in system and "Free time" in system and "Gurpreet:" in system and "end_call" in str(llm.calls[0]["tools"])


def test_returning_caller_is_greeted_by_name_and_remembered():
    c = ctx()
    cut = ids(models.Service, "Haircut (men)", SALON)
    confirm(c, call(ap.prepare_booking, c, customer_name="Aman", service_id=cut, start="2026-11-10 17:00"))
    llm = FakeLLM([say("Ji Aman ji.")])
    e = Engine(llm=llm, state=MemoryStore())
    hello = e.start(SALON, "phone", "9876543210", verified=True)  # real caller ID
    assert "Aman ji" in hello.text and "Riya" in hello.text
    e.reply(hello.conversation_id, "haan")
    assert "Upcoming bookings: ref" in llm.calls[0]["messages"][0]["content"]


def test_numbers_are_spoken_like_a_person():
    from alaap.spoken import for_speech
    assert for_speech("Kal 18:30 baje, Rs 200 lagenge. Ref 6717 hai.") == \
        "Kal saade chhe baje, do sau rupaye lagenge. Ref chhe saat ek saat hai."
    assert for_speech("Slot 17:00-19:00 hai aur total Rs 1,245 hoga.") == \
        "Slot paanch se saat baje hai aur total ek hazaar do sau paintaalees rupaye hoga."
    assert for_speech("Your table is at 7:15 PM, Rs 450.") == "Your table is at seven fifteen p m, four hundred fifty rupees."


def test_read_back_with_tool_call_needs_one_llm_request():
    cut = ids(models.Service, "Haircut (men)", SALON)
    msg = tc("1", "prepare_booking", customer_name="Aman", service_id=cut, start="2026-11-10 17:00")
    msg["content"] = "Toh aaj shaam paanch baje Gurpreet ke saath haircut, do sau rupaye. Pakka kar doon?"
    llm = FakeLLM([msg, say("Ji, ek second.")])  # second reply must not be needed
    e = Engine(llm=llm, state=MemoryStore())
    cid = e.start(SALON, "phone", "9876543210").conversation_id
    r = e.reply(cid, "aaj shaam paanch baje haircut, naam Aman")
    assert len(llm.calls) == 1 and r.text.endswith("Pakka kar doon?")


def test_owner_updates_business_by_talking():
    o = ctx(phone="9800000001", is_owner=True)
    assert call(owner.update_item, o, name="facial", price_inr=900)["price"] == 900
    assert call(owner.add_item, o, name="Manicure", price_inr=350, kind="service", duration_min=40)["done"] == "added service"
    call(owner.remember_fact, o, topic="Parking", fact="Parking is behind the shop.")
    call(owner.set_hours, o, weekday=0, opens="11:00", closes="18:00")
    with db.session() as s:
        assert s.scalar(select(models.Service.price_inr).where(models.Service.name == "Facial")) == 900
        mani = s.scalar(select(models.Service).where(models.Service.name == "Manicure"))
        assert len([p for p in s.scalars(select(models.Staff).where(models.Staff.business_id == SALON)) if mani in p.services]) == 3
        assert s.scalar(select(models.Faq.answer).where(models.Faq.question == "Parking")) == "Parking is behind the shop."
    c = ctx()
    assert not call(ap.find_free_slots, c, service_id=mani.id, date="2026-11-16")["closed"]  # Monday now open
    with pytest.raises(ToolError, match="No service or product"):
        call(owner.update_item, o, name="helicopter ride", price_inr=1)


def test_signup_template_then_import_replaces_samples(monkeypatch):
    from fastapi.testclient import TestClient
    from alaap.api import main
    monkeypatch.setattr(main.config, "RUN_JOBS", False)
    from alaap import onboarding
    with TestClient(main.app) as client:
        r = client.post("/api/auth/signup", json={
            "business_name": "Royal Mens Parlour", "kind": "salon", "city": "Rajpura", "owner_name": "Vicky",
            "owner_phone": "9811111111", "email": "vicky@example.com", "password": "longpassword"}).json()
        h = {"Authorization": f"Bearer {r['token']}"}
        st = client.get("/api/settings", headers=h).json()
        assert len(st["services"]) == 7 and st["hours"]  # works from minute one
        status = client.get("/api/setup/status", headers=h).json()
        assert not status["items"][0]["done"]  # still sample prices
        imported = onboarding.clean({"services": [{"name": "Cutting", "price_inr": "150", "duration_min": 30},
                                                  {"name": "Shave", "price_inr": 80}],
                                     "staff": [{"name": "Sunny", "services": ["Cutting", "Shave"]}],
                                     "hours": [{"weekday": 0, "opens": "9:00", "closes": "21:00"}],
                                     "faqs": [{"question": "Payment", "answer": "Only GPay and Paytm."}]})
        res = client.post("/api/setup/apply", json=imported, headers=h).json()
        live = [x["name"] for x in res["settings"]["services"] if x["active"]]
        assert live == ["Cutting", "Shave"] and res["settings"]["hours"] == [{"weekday": 0, "opens": "09:00", "closes": "21:00"}]
        assert client.get("/api/setup/status", headers=h).json()["items"][0]["done"]
        assert [f["answer"] for f in res["settings"]["faqs"]] == ["Only GPay and Paytm."]  # samples gone


# ---------- production pieces ----------

def test_trial_payment_and_enforcement(monkeypatch):
    from alaap import billing, config
    from alaap.timeutil import now as tnow
    with db.session() as s:
        biz = s.get(models.Business, SALON)
        biz.trial_ends_at = tnow() + timedelta(days=3)
        assert billing.status(biz)["state"] == "trial" and billing.status(biz)["days_left"] == 3
        pay = billing.checkout(s, biz, "pro", months=2)
        assert pay.amount_inr == 4998 and pay.link_id.startswith("mockplan_")
        billing.mark_paid(s, pay.link_id)
        assert billing.status(biz)["state"] == "active"
        assert biz.paid_until == tnow() + timedelta(days=3 + 60)  # trial days are kept
        biz.paid_until, biz.trial_ends_at = tnow() - timedelta(days=1), tnow() - timedelta(days=20)
        assert billing.status(biz)["state"] == "expired"
    monkeypatch.setattr(config, "ENFORCE_BILLING", True)
    llm = FakeLLM([say("should not be called")])
    e = Engine(llm=llm, state=MemoryStore())
    cid = e.start(SALON, "web").conversation_id
    r = e.reply(cid, "haircut book karna hai")
    assert "online booking band" in r.text and r.end and llm.calls == []


def test_rate_limit_and_retention():
    from alaap import config, jobs, ratelimit
    assert all(ratelimit.hit("test:1.2.3.4", 3) for _ in range(3)) and not ratelimit.hit("test:1.2.3.4", 3)
    with db.session() as s:
        old = models.Conversation(business_id=SALON, channel="web", started_at=NOW - timedelta(days=400))
        s.add(old)
        s.flush()
        s.add(models.Message(conversation_id=old.id, role="customer", text="purana"))
    assert jobs.purge_old_data() == 1


def test_production_config_refuses_unsafe_defaults(monkeypatch):
    from alaap import config
    monkeypatch.setattr(config, "PRODUCTION", True)
    monkeypatch.setattr(config, "SECRET_KEY", config.DEFAULT_SECRET)
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///x.db")
    monkeypatch.setattr(config, "PUBLIC_URL", "http://example.com")
    fatal = [p for p in config.check() if p.startswith("FATAL")]
    assert len(fatal) == 3


def test_whatsapp_template_fallback(monkeypatch):
    import httpx
    from alaap import config, jobs
    from alaap.channels import whatsapp
    monkeypatch.setattr(config, "WHATSAPP_TOKEN", "t")
    monkeypatch.setattr(config, "WHATSAPP_TEMPLATE_NAME", "alaap_update")
    sent = []

    def text(*a):
        raise httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://x"),
                                    response=httpx.Response(400, json={"error": {"code": 131047}}))
    monkeypatch.setattr(whatsapp, "send_text", text)
    monkeypatch.setattr(whatsapp, "send_template", lambda pnid, to, name, body: sent.append((name, body)))
    with db.session() as s:
        biz = s.get(models.Business, SALON)
        biz.whatsapp_phone_number_id = "123"
        s.add(models.Outbox(business_id=SALON, to_phone="9876543210", kind="reminder", body="Reminder: haircut",
                            send_after=NOW))
    assert jobs.send_outbox() == 1 and sent == [("Glow Unisex Salon", "Reminder: haircut")]


def test_signup_with_real_clock(monkeypatch):
    """Signup computes the trial end from the real clock (the other tests freeze time)."""
    from fastapi.testclient import TestClient
    from alaap.api import main
    monkeypatch.setattr(main.config, "RUN_JOBS", False)  # no background jobs (they'd call real APIs)
    timeutil.freeze(None)
    with TestClient(main.app) as client:
        r = client.post("/api/auth/signup", json={
            "business_name": "Clock Test Clinic", "kind": "clinic", "city": "Patiala", "owner_name": "Dr K",
            "owner_phone": "9800011111", "email": "clock@example.com", "password": "longpassword"})
        assert r.status_code == 200
        st = client.get("/api/billing", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()["status"]
        assert st["state"] == "trial" and st["days_left"] in (13, 14)


def test_no_silent_hang_up_after_confirming():
    """Live voice test found: confirm_action + end_call in one step hung up without telling the caller the result."""
    cut = ids(models.Service, "Haircut (men)", SALON)
    hang = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "confirm_action", "arguments": '{"action_id": "A1"}'}},
        {"id": "e", "type": "function", "function": {"name": "end_call", "arguments": "{}"}}]}
    llm = FakeLLM([{**tc("1", "prepare_booking", customer_name="Rohit", service_id=cut, start="2026-11-10 17:00"),
                    "content": "Kal paanch baje haircut, pakka kar doon?"},
                   hang, say("Ho gaya ji! Booking number ek do teen chaar.")])
    e = Engine(llm=llm, state=MemoryStore())
    cid = e.start(SALON, "phone", "9876543210", verified=True).conversation_id
    e.reply(cid, "kal 5 baje haircut, naam Rohit")
    r = e.reply(cid, "haan ji pakka kar do")
    assert not r.end and "Ho gaya" in r.text
    with db.session() as s:
        assert s.scalar(select(func.count(models.Appointment.id)).where(models.Appointment.conversation_id == cid)) == 1


def test_no_hang_up_before_the_caller_says_bye():
    llm = FakeLLM([{"role": "assistant", "content": "Milte hain kal!", "tool_calls": [
                       {"id": "e", "type": "function", "function": {"name": "end_call", "arguments": "{}"}}]},
                   say("Aur kuch madad karoon?")])
    e = Engine(llm=llm, state=MemoryStore())
    cid = e.start(SALON, "phone", "9876543210", verified=True).conversation_id
    r = e.reply(cid, "haan ji theek hai")
    assert not r.end and "Aur kuch" in r.text
