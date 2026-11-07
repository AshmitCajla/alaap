"""Managed mode: Alaap creates the shop, lends it a number, routes calls by the number dialled, and serves many shops
from one shared WhatsApp number using shop codes."""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from alaap import config, db, managed, models, seed, timeutil
from alaap.api import main
from alaap.channels import voice, whatsapp

NOW = datetime(2026, 11, 10, 9, 0)
SHARED = "999000111"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db.configure(f"sqlite:///{tmp_path / 'm.db'}")
    timeutil.freeze(NOW)
    seed.seed()
    monkeypatch.setattr(main.config, "RUN_JOBS", False)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    with TestClient(main.app) as c:
        yield c
    timeutil.freeze(None)


def ops(c):
    r = c.post("/api/ops/auth/login", json={"email": "team@alaap.dev", "password": "demo1234"})
    return {"Authorization": "Bearer " + r.json()["token"]}


def new_shop(c, h, **kw):
    body = {"name": "Kaur Beauty Parlour", "kind": "salon", "city": "Patiala", "owner_name": "Simran",
            "owner_phone": "98140 11111", **kw}
    r = c.post("/api/ops/shops", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_shop_assign_number_and_route_calls(client):
    h = ops(client)
    client.post("/api/ops/numbers", json={"numbers": ["+91 80471 12345", "080-4711-2346"], "monthly_cost_inr": 500},
                headers=h)
    shop = new_shop(client, h)
    assert shop["code"] == "KAUR" and shop["number"] == "8047112345"
    detail = client.get(f"/api/ops/shops/{shop['id']}", headers=h).json()
    assert detail["stage"] == "setup" and detail["managed"] and detail["counts"]["samples"] > 0
    assert any("**61*8047112345#" == code for _, code in detail["links"]["forwarding"])
    # Calls to the number reach the shop in any format Exotel sends it.
    for dialled in ("08047112345", "+918047112345", "918047112345", "8047112345"):
        assert voice.business_for_call(None, dialled) == shop["id"]
    assert voice.business_for_call(None, "08047112346") is None  # still in the pool
    # Releasing frees it; the next shop gets the oldest free number.
    client.delete(f"/api/ops/shops/{shop['id']}/number", headers=h)
    assert voice.business_for_call(None, "08047112345") is None
    other = new_shop(client, h, name="Kaur Tailors", owner_phone="9814022222")
    assert other["code"] == "KAUR2" and other["number"] == "8047112345"


def test_no_free_number_is_reported_not_fatal(client):
    shop = new_shop(client, ops(client))
    assert shop["number"] is None and "No free number" in shop["note"]


def test_operator_and_owner_logins_are_separate(client):
    h = ops(client)
    owner = {"Authorization": "Bearer " + client.post(
        "/api/auth/login", json={"email": "owner@glow.demo", "password": "demo1234"}).json()["token"]}
    assert client.get("/api/ops/shops", headers=owner).status_code == 401
    assert client.get("/api/overview", headers=h).status_code == 401
    # "Open dashboard" gives the team a login into that shop only.
    shop = new_shop(client, h)
    support = {"Authorization": "Bearer " + client.post(f"/api/ops/shops/{shop['id']}/open", headers=h).json()["token"]}
    me = client.get("/api/me", headers=support).json()
    assert me["business"]["id"] == shop["id"] and me["user"]["support"]
    assert client.get("/api/ops/shops", headers=support).status_code == 401
    r = client.put("/api/me/password", json={"current": "x", "new": "longenough1"}, headers=support)
    assert r.status_code == 400


def test_import_review_apply_and_go_live(client, monkeypatch):
    h = ops(client)
    shop = new_shop(client, h)
    monkeypatch.setattr("alaap.onboarding.extract", lambda kind, text=None, image=None, image_type=None: {
        "about": None, "address": None, "phone": None, "hours": [{"weekday": 0, "opens": "10:00", "closes": "19:00"}],
        "services": [{"name": "Threading", "price_inr": 50, "duration_min": 15}], "products": [], "staff": [],
        "faqs": []})
    item = client.post(f"/api/ops/shops/{shop['id']}/import", json={"text": "Threading 50"}, headers=h).json()
    assert item["extracted"]["services"][0]["name"] == "Threading"
    r = client.post(f"/api/ops/intakes/{item['id']}/apply", json={}, headers=h)
    assert r.json()["saved"]["services"] == 1
    detail = client.get(f"/api/ops/shops/{shop['id']}", headers=h).json()
    assert detail["stage"] == "review" and detail["counts"]["samples"] == 0
    r = client.post(f"/api/ops/shops/{shop['id']}/go-live", headers=h).json()
    assert "live" in r["welcome_text"]
    with db.session() as s:
        msg = s.scalar(select(models.Outbox).where(models.Outbox.kind == "welcome"))
        assert msg.to_phone == "9814011111"
        assert s.get(models.Business, shop["id"]).stage == "live"


class FakeWA:
    def __init__(self, monkeypatch, replies="Ji, bataiye"):
        self.sent = []
        self.engine_calls = []
        monkeypatch.setattr(config, "WHATSAPP_SHARED_NUMBER_ID", SHARED)
        monkeypatch.setattr(config, "WHATSAPP_SHARED_NUMBER", "919800000000")
        monkeypatch.setattr(whatsapp, "send_text", lambda pnid, to, text: self.sent.append((pnid, to, text)))
        outer = self

        class Engine:
            def start(self, biz_id, channel, phone, owner=False, verified=False):
                c = models.Conversation(business_id=biz_id, channel=channel, caller_phone=phone, is_owner=owner)
                with db.session() as s:
                    s.add(c)
                    s.flush()
                    cid = c.id

                class R:
                    conversation_id = cid
                return R()

            def reply(self, cid, text):
                with db.session() as s:
                    conv = s.get(models.Conversation, cid)
                    outer.engine_calls.append((conv.business_id, conv.is_owner, text))

                class R:
                    pass
                r = R()
                r.text = replies
                return r

        monkeypatch.setattr(whatsapp, "get_engine", lambda: Engine())
        monkeypatch.setattr(whatsapp.speech, "provider", lambda: None)

    def text(self, sender, body):
        whatsapp._handle_message(SHARED, {"from": "91" + sender, "type": "text", "text": {"body": body}})


def test_shared_whatsapp_routes_by_shop_code(client, monkeypatch):
    wa = FakeWA(monkeypatch)
    with db.session() as s:
        glow = s.scalar(select(models.Business).where(models.Business.slug == "glow-salon"))
        glow_id, code = glow.id, glow.code
    assert code == "GLOW"
    wa.text("9876511111", "Hello")  # no code yet: explain how to reach a shop
    assert "code" in wa.sent[-1][2] and not wa.engine_calls
    wa.text("9876511111", "glow Namaste, facial kitne ka hai?")
    assert wa.engine_calls[-1] == (glow_id, False, "Namaste, facial kitne ka hai?")
    assert wa.sent[-1][2].startswith("*Glow Unisex Salon*")  # shared chat: say which shop is talking
    wa.text("9876511111", "kal 11 baje")  # sticks to the shop they chose
    assert wa.engine_calls[-1] == (glow_id, False, "kal 11 baje")
    assert len({c for c in wa.engine_calls}) == 2


def test_shared_whatsapp_join_owner_and_menu_photo(client, monkeypatch):
    wa = FakeWA(monkeypatch)
    wa.text("9814033333", "JOIN meri bakery hai Patiala mein")
    with db.session() as s:
        join = s.scalar(select(models.Intake).where(models.Intake.kind == "join"))
        assert join.from_phone == "9814033333" and join.business_id is None
    # The owner sends a menu photo before the team has created the shop.
    monkeypatch.setattr(whatsapp, "download_media", lambda mid: (b"\xff\xd8fakejpeg", "image/jpeg"))
    whatsapp._handle_message(SHARED, {"from": "919814033333", "type": "image", "image": {"id": "m1"}})
    assert "Photo mil gayi" in wa.sent[-1][2]
    # The team creates the shop from the join request: the photo and request move to it.
    h = ops(client)
    shop = new_shop(client, h, name="Patiala Bakers", kind="restaurant", owner_phone="9814033333",
                    intake_id=join.id)
    with db.session() as s:
        items = s.scalars(select(models.Intake).where(models.Intake.business_id == shop["id"])).all()
        assert {i.kind for i in items} == {"join", "photo"}
        assert {i.status for i in items if i.kind == "join"} == {"done"}
    # Now the owner's messages go to their own owner assistant...
    wa.text("9814033333", "kal shop band rahegi")
    assert wa.engine_calls[-1] == (shop["id"], True, "kal shop band rahegi")
    # ...and a new menu photo is read for that shop and queued for review.
    monkeypatch.setattr("alaap.onboarding.extract", lambda kind, text, image, image_type: {
        "services": [], "products": [{"name": "Cake", "price_inr": 400}], "hours": [], "staff": [], "faqs": []})
    whatsapp._handle_message(SHARED, {"from": "919814033333", "type": "image", "image": {"id": "m2"}})
    assert "1 items" in wa.sent[-1][2]
    items = client.get("/api/ops/intakes", headers=h).json()["intakes"]
    assert items[0]["shop"] == "Patiala Bakers" and items[0]["extracted"]["products"][0]["name"] == "Cake"


def test_outbox_uses_shared_number_with_shop_name(client, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_SHARED_NUMBER_ID", SHARED)
    with db.session() as s:
        glow = s.scalar(select(models.Business).where(models.Business.slug == "glow-salon"))
        assert whatsapp.sender_id(glow) == SHARED
        assert whatsapp.labelled(glow, "Reminder") == "*Glow Unisex Salon*\nReminder"
        glow.whatsapp_phone_number_id = "own-1"
        assert whatsapp.sender_id(glow) == "own-1" and whatsapp.labelled(glow, "Hi") == "Hi"


def test_usage_and_cost(client):
    h = ops(client)
    client.post("/api/ops/numbers", json={"numbers": ["8047112345"], "monthly_cost_inr": 500}, headers=h)
    shop = new_shop(client, h)
    with db.session() as s:
        s.add(models.Conversation(business_id=shop["id"], channel="phone", call_seconds=300, started_at=NOW))
        s.add(models.Outbox(business_id=shop["id"], to_phone="9814011111", kind="reminder", body="x", status="sent",
                            created_at=NOW))
    u = client.get("/api/ops/usage", headers=h).json()
    row = next(r for r in u["shops"] if r["id"] == shop["id"])
    assert row["calls"] == 1 and row["call_minutes"] == 5.0 and row["messages_sent"] == 1
    assert row["cost_inr"] == round(5 * config.COST_CALL_MIN_INR + config.COST_WA_MSG_INR + 500, 2)
    assert row["margin_inr"] == round(row["price_inr"] - row["cost_inr"])
    assert client.get("/api/ops/usage?month=2026-10", headers=h).json()["shops"][0]["calls"] == 0


def test_import_in_one_go_keeps_named_staff_and_never_quotes_zero(client):
    """Regression: new rows read active=None before saving, so the owner was added as a duplicate staff member,
    and 'bridal makeup on call' became a Rs 0 service the assistant would quote as free."""
    from alaap import onboarding

    with db.session() as s:
        biz, _ = managed.create_shop(s, name="Kaur Beauty", kind="salon", city="Patiala", owner_name="Simran Kaur",
                                     owner_phone="9814011111")
        counts = onboarding.apply(s, biz, {
            "services": [{"name": "Threading", "price_inr": 40, "duration_min": 15},
                         {"name": "Bridal makeup", "price_inr": 0, "duration_min": 120}],
            "staff": [{"name": "Simran", "services": []}, {"name": "Preet", "services": ["Threading"]}],
            "hours": [], "products": [], "faqs": []})
        staff = {st.name: [x.name for x in st.services] for st in biz.staff if st.active}
        assert staff == {"Simran": ["Threading"], "Preet": ["Threading"]}
        assert [sv.name for sv in biz.services if sv.active] == ["Threading"]
        assert any("Bridal makeup" in f.answer and "price on request" in f.answer for f in biz.faqs)
        assert counts["services"] == 1
