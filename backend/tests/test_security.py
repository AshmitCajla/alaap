"""Security checks: every owner route needs a login, one business can't touch another's data,
customer pages escape what owners type, and unverified phone numbers can't open someone's bookings."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from alaap import db, models, seed, timeutil
from alaap.api import main
from alaap.engine import Engine
from alaap.state import MemoryStore

from datetime import datetime

NOW = datetime(2026, 11, 10, 9, 0)
PUBLIC = {"/health", "/api/auth/login", "/api/ops/auth/login", "/api/auth/signup", "/widget.js", "/", "/pay/done"}
PUBLIC_PREFIX = ("/api/public/", "/api/chat/", "/demo/", "/c/", "/pay/mock/", "/webhooks/", "/ws/", "/docs", "/openapi",
                 "/redoc")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db.configure(f"sqlite:///{tmp_path / 's.db'}")
    timeutil.freeze(NOW)
    seed.seed()
    monkeypatch.setattr(main.config, "RUN_JOBS", False)
    with TestClient(main.app) as c:
        yield c
    timeutil.freeze(None)


def login(c, email):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": email, "password": "demo1234"}).json()["token"]}


def test_every_owner_route_requires_login(client):
    checked = 0
    for path, ops in main.app.openapi()["paths"].items():
        if path in PUBLIC or path.startswith(PUBLIC_PREFIX) or not path.startswith("/api/"):
            continue
        for method in (m.upper() for m in ops):
            url = path.replace("{", "").replace("}", "")  # e.g. /api/orders/order_id -> 422/401 either way
            url = "/".join("1" if p.endswith("_id") or p in ("cid", "section") else p for p in url.split("/"))
            r = client.request(method, url, json={})
            assert r.status_code == 401, f"{method} {path} answered {r.status_code} without login"
            checked += 1
    assert checked >= 25


def test_one_business_cannot_touch_another(client):
    salon, kirana = login(client, "owner@glow.demo"), login(client, "owner@kirana.demo")
    with db.session() as s:
        cust = models.Customer(business_id=1, name="Aman", phone="9876543210")
        s.add(cust)
        s.flush()
        appt = models.Appointment(ref="1111", business_id=1, customer_id=cust.id, service_id=1, staff_id=1,
                                  start_at=datetime(2026, 11, 11, 11), end_at=datetime(2026, 11, 11, 11, 30))
        s.add(appt)
        conv = models.Conversation(business_id=1, channel="web")
        s.add(conv)
        s.flush()
        appt_id, conv_id = appt.id, conv.id
    assert client.patch(f"/api/appointments/{appt_id}", json={"status": "cancelled"}, headers=kirana).status_code == 404
    assert client.get(f"/api/conversations/{conv_id}", headers=kirana).status_code == 404
    assert client.post(f"/api/owner-chat/{conv_id}", json={"text": "hi"}, headers=kirana).status_code == 404
    assert all(a["ref"] != "1111" for a in client.get("/api/appointments", headers=kirana).json())
    # Updating "services" with another business's id must not modify it
    client.put("/api/settings/services", json=[{"id": 1, "name": "Hacked", "duration_min": 5, "price_inr": 1}], headers=kirana)
    with db.session() as s:
        assert s.get(models.Service, 1).name == "Haircut (men)"
    assert client.get("/api/appointments", headers=salon).json()[0]["ref"] == "1111"


def test_customer_page_escapes_owner_text(client):
    salon = login(client, "owner@glow.demo")
    client.put("/api/settings/business", json={"name": '<script>alert(1)</script>Glow'}, headers=salon)
    html = client.get("/c/glow-salon").text
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_web_caller_cannot_open_bookings_by_saying_a_number(client):
    """On web chat the phone number is just typed, so it can't be used to look up or cancel bookings."""
    from alaap.skills import appointments as ap
    from alaap.skills.base import Context
    with db.session() as s:
        cust = models.Customer(business_id=1, name="Aman", phone="9876543210")
        s.add(cust)
        s.flush()
        s.add(models.Appointment(ref="2222", business_id=1, customer_id=cust.id, service_id=1, staff_id=1,
                                 start_at=datetime(2026, 11, 11, 11), end_at=datetime(2026, 11, 11, 11, 30)))
    web = Context(business_id=1, conversation_id=1, channel="web", caller_phone=None)
    with db.session() as s:
        r = ap.find_my_appointments(web, s, phone="9876543210")
    assert r.get("upcoming") in (None, []) and "privacy" in str(r).lower()
    # A real caller ID (phone call / WhatsApp) does see them
    phone = Context(business_id=1, conversation_id=1, channel="phone", caller_phone="9876543210", phone_verified=True)
    with db.session() as s:
        assert ap.find_my_appointments(phone, s)["upcoming"][0]["ref"] == "2222"


def test_browser_call_cannot_fake_caller_id(client):
    with client.websocket_connect("/ws/call/glow-salon") as ws:
        ws.send_json({"event": "start", "start": {"from": "9876543210", "media_format": {"sample_rate": 16000}}})
        try:
            ws.receive_text()
        except Exception:
            pass
    with db.session() as s:
        conv = s.scalar(select(models.Conversation).order_by(models.Conversation.id.desc()))
        assert conv is None or conv.caller_phone is None


def test_exotel_socket_needs_secret(client, monkeypatch):
    monkeypatch.setattr(main.config, "EXOTEL_WS_TOKEN", "s3cret")
    with client.websocket_connect("/ws/exotel?biz=glow-salon") as ws:
        with pytest.raises(Exception):
            ws.receive_text()  # closed: wrong / missing token


def test_tokens_cannot_be_forged(client):
    import jwt
    fake = jwt.encode({"sub": "1", "biz": 1, "exp": 9999999999}, "wrong-secret", algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {fake}"}).status_code == 401
    start = client.post("/api/chat/glow-salon/start", json={}).json()
    other = jwt.encode({"cid": start["conversation_id"] + 1, "exp": 9999999999}, main.config.SECRET_KEY, algorithm="HS256")
    r = client.post(f"/api/chat/{start['conversation_id']}/message", json={"text": "hi", "token": other})
    assert r.status_code == 403
