"""Simultaneous customers can't double-book a slot or oversell stock. Needs Postgres (row locks):
set TEST_POSTGRES_URL, e.g. postgresql+psycopg://alaap:alaap@localhost:5432/alaap (CI does)."""

import os
import threading
from datetime import datetime

import pytest
from sqlalchemy import func, select

from alaap import db, models, seed, timeutil
from alaap.errors import ToolError
from alaap.skills import appointments as ap
from alaap.skills import orders
from alaap.skills.base import Context

PG = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG, reason="set TEST_POSTGRES_URL to run against Postgres")
N = 20


@pytest.fixture(autouse=True)
def pg():
    db.configure(PG)
    timeutil.freeze(datetime(2026, 11, 10, 9, 0))
    seed.seed(reset=True)
    yield
    timeutil.freeze(None)


def ctx(biz, i):
    with db.session() as s:
        c = models.Conversation(business_id=biz, channel="web")
        s.add(c)
        s.flush()
        cid = c.id
    c = Context(business_id=biz, conversation_id=cid, caller_phone=f"98000{i:05d}")
    c.user_turn = 1
    return c


def race(prepare):
    won, refused = [], []
    barrier = threading.Barrier(N)

    def run(i):
        c, action = prepare(i)
        barrier.wait()
        try:
            with db.session() as s:
                {"book": ap.do_book, "order": orders.do_order}[action["kind"]](c, s, action)
            won.append(i)
        except ToolError:
            refused.append(i)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(N)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return len(won), len(refused)


def test_one_slot_one_booking():
    def prepare(i):
        c = ctx(1, i)
        with db.session() as s:
            r = ap.prepare_booking(c, s, customer_name=f"C{i}", service_id=5, start="2026-11-10 15:00")  # facial
        return c, c.pending[r["action_id"]]
    assert race(prepare) == (1, N - 1)


def test_no_overselling():
    with db.session() as s:
        butter = s.scalar(select(models.Product).where(models.Product.name == "Amul Butter"))
        butter.stock, bid = 5, butter.id

    def prepare(i):
        c = ctx(2, i)
        with db.session() as s:
            r = orders.prepare_order(c, s, items=[{"product_id": bid, "qty": 1}, {"product_id": 1, "qty": 1}],
                                     customer_name=f"C{i}", address="x", pincode="147001", slot_date="2026-11-10",
                                     slot="12:00-14:00", payment_method="cod")
        return c, c.pending[r["action_id"]]
    assert race(prepare) == (5, N - 5)
    with db.session() as s:
        assert s.get(models.Product, bid).stock == 0
        assert s.scalar(select(func.sum(models.OrderItem.qty)).where(models.OrderItem.product_id == bid)) == 5
