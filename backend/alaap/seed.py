"""Three demo businesses, one per customer group in the plan. All details are made up.

  python -m alaap.seed           # create tables and demo data (idempotent)
  python -m alaap.seed --reset   # drop everything first
"""

import sys

from sqlalchemy import select

from . import auth, db, models
from .skills import DEFAULT_SKILLS

DEMO_PASSWORD = "demo1234"


def _hours(days, opens, closes):
    return [models.BusinessHours(weekday=d, opens=opens, closes=closes) for d in days]


def salon() -> tuple[models.Business, str]:
    b = models.Business(
        slug="glow-salon", name="Glow Unisex Salon", kind="salon", phone="+91 98XXX XXXX0",
        owner_name="Harpreet", owner_phone="9800000001", owner_language="pa-IN",
        address="Shop 12, Leela Bhawan Market", city="Patiala", languages="Punjabi, Hindi, English",
        about="Unisex salon near Leela Bhawan. Walk-ins welcome when a stylist is free.",
        skills=DEFAULT_SKILLS["salon"], plan="pro")
    b.hours = _hours(range(1, 7), "10:00", "20:00")  # closed Mondays
    svc = {name: models.Service(name=name, duration_min=m, price_inr=p, notes=n) for name, m, p, n in [
        ("Haircut (men)", 30, 200, None),
        ("Haircut (women)", 45, 400, "Shoulder length; longer hair may cost more"),
        ("Beard trim", 15, 100, None),
        ("Hair colour", 90, 1200, "Global colour"),
        ("Facial", 60, 800, None),
        ("Threading (eyebrows)", 15, 50, None),
        ("Head massage", 30, 250, "With oil"),
    ]}
    b.services = list(svc.values())
    b.staff = [models.Staff(name=n, services=[svc[x] for x in s]) for n, s in [
        ("Gurpreet", ["Haircut (men)", "Beard trim", "Head massage"]),
        ("Simran", ["Haircut (women)", "Hair colour", "Facial", "Threading (eyebrows)"]),
        ("Raju", ["Haircut (men)", "Beard trim", "Hair colour", "Head massage"]),
    ]]
    b.faqs = [models.Faq(question=q, answer=a) for q, a in [
        ("Payment", "UPI, cash and cards accepted."),
        ("Parking", "Two-wheeler parking in front; cars at the Leela Bhawan lot."),
        ("Kids haircut", "Same price as men's haircut."),
    ]]
    return b, "owner@glow.demo"


def kirana() -> tuple[models.Business, str]:
    b = models.Business(
        slug="sharma-kirana", name="Sharma General Store", kind="kirana", phone="+91 98XXX XXXX2",
        owner_name="Rakesh Sharma", owner_phone="9800000002", owner_language="hi-IN",
        address="Main Bazaar, near Gurdwara Dukh Niwaran Sahib", city="Patiala", languages="Hindi, Punjabi, English",
        about="Groceries and daily needs, home delivery in nearby areas.",
        skills=DEFAULT_SKILLS["kirana"], plan="pro")
    b.hours = _hours(range(0, 7), "08:00", "21:00")
    b.products = [models.Product(name=n, aliases=a, unit=u, price_inr=p, stock=st, reorder_days=r) for n, a, u, p, st, r in [
        ("Aashirvaad Atta", "atta, aata, gehun ka atta, flour", "5 kg", 285, 20, 20),
        ("Fortune Soyabean Oil", "oil, tel, refined, soya oil", "1 L", 155, 30, 25),
        ("Tata Salt", "salt, namak", "1 kg", 28, 50, None),
        ("Amul Taaza Milk", "milk, doodh", "500 ml", 28, None, 1),
        ("Amul Butter", "butter, makhan", "100 g", 58, 15, None),
        ("Basmati Rice (loose)", "rice, chawal, basmati", "1 kg", 120, 40, 30),
        ("Toor Dal", "dal, arhar, toor", "1 kg", 160, 25, 30),
        ("Sugar", "cheeni, shakkar, chini", "1 kg", 46, 40, 30),
        ("Maggi Noodles", "maggi, maggie, noodles", "70 g", 15, 100, None),
        ("Parle-G Biscuits", "parle g, biscuit", "250 g", 25, 60, None),
        ("Surf Excel Detergent", "surf, detergent, washing powder", "1 kg", 140, 12, 30),
        ("Eggs", "anda, ande, egg", "6 pcs", 45, 30, 7),
    ]]
    b.areas = [models.ServiceArea(pincode=p, delivery_fee_inr=f, min_order_inr=m) for p, f, m in [
        ("147001", 0, 199), ("147002", 20, 299), ("147003", 30, 399)]]
    b.slots = [models.DeliverySlot(start=s, end=e) for s, e in [("09:00", "11:00"), ("12:00", "14:00"),
                                                               ("17:00", "19:00"), ("19:00", "21:00")]]
    b.faqs = [models.Faq(question="Payment", answer="UPI link on WhatsApp or cash on delivery.")]
    return b, "owner@kirana.demo"


def coaching() -> tuple[models.Business, str]:
    b = models.Business(
        slug="vidya-coaching", name="Vidya Coaching Centre", kind="coaching", phone="+91 98XXX XXXX3",
        owner_name="Meenu Garg", owner_phone="9800000003", owner_language="hi-IN",
        address="22 Model Town", city="Patiala", languages="Hindi, Punjabi, English",
        about="Coaching for classes 9-12 (science, maths) and JEE/NEET foundation. Batches of 20.",
        skills=DEFAULT_SKILLS["coaching"], plan="business")
    b.hours = _hours(range(0, 6), "09:00", "19:00")
    counsel = models.Service(name="Free counselling session", duration_min=30, price_inr=0,
                             notes="With the director; bring last marksheet")
    demo = models.Service(name="Free demo class", duration_min=60, price_inr=0)
    b.services = [counsel, demo]
    b.staff = [models.Staff(name="Meenu ma'am", services=[counsel]), models.Staff(name="Rohit sir", services=[demo])]
    b.faqs = [models.Faq(question=q, answer=a) for q, a in [
        ("Fees", "Class 11-12 science: Rs 3,500 per month per subject group; JEE/NEET foundation: Rs 4,500 per month."),
        ("Batch timings", "Morning 7-9 AM and evening 4-6 PM, Monday to Saturday."),
        ("Scholarship", "Up to 30% off for 90%+ in the previous class."),
    ]]
    return b, "owner@coaching.demo"


def seed(reset: bool = False) -> list[int]:
    if reset:
        from . import models as m  # noqa: F401
        db.Base.metadata.drop_all(db.engine())
    db.create_all()
    ids = []
    with db.session() as s:
        for make in (salon, kirana, coaching):
            biz, email = make()
            existing = s.scalar(select(models.Business).where(models.Business.slug == biz.slug))
            if existing:
                ids.append(existing.id)
                continue
            s.add(biz)
            s.flush()
            # In production the demo owners get random passwords (the demos stay public; their logins don't).
            from . import config
            import secrets

            password = secrets.token_urlsafe(12) if config.PRODUCTION else DEMO_PASSWORD
            s.add(models.OwnerUser(business_id=biz.id, email=email, name=biz.owner_name,
                                   password_hash=auth.hash_password(password)))
            if config.PRODUCTION:
                print(f"demo owner {email}: {password}")
            ids.append(biz.id)
    return ids


def demo_activity() -> None:
    """Sample bookings, an order, a lead and a callback, made through the real skill code
    (so the dashboard has something to show before the first real call)."""
    from datetime import timedelta

    from .scheduling import next_open_day
    from .skills import appointments as ap, leads, orders, support
    from .skills.base import Context
    from .timeutil import now

    def run(biz_slug, phone, steps, channel="phone"):
        with db.session() as s:
            biz = s.scalar(select(models.Business).where(models.Business.slug == biz_slug))
            conv = models.Conversation(business_id=biz.id, channel=channel, caller_phone=phone, started_at=now(),
                                       last_at=now())
            s.add(conv)
            s.flush()
            ctx = Context(business_id=biz.id, conversation_id=conv.id, caller_phone=phone, channel=channel)
            for said, fn, args in steps:
                s.add(models.Message(conversation_id=conv.id, role="customer", text=said))
                ctx.user_turn += 2
                result = fn(ctx, s, **args(s, biz))
                if "action_id" in result:
                    action = ctx.pending[result["action_id"]]
                    action["user_turn"] = 0
                    kinds = {"book": ap.do_book, "order": orders.do_order}
                    result = kinds[action["kind"]](ctx, s, action)
                s.add(models.Message(conversation_id=conv.id, role="alaap", text=result.get("say", "Ji, ho gaya.")))
            conv.outcome = ctx.outcome

    def svc(name):
        return lambda s, biz: s.scalar(select(models.Service.id).where(models.Service.business_id == biz.id,
                                                                     models.Service.name == name))

    def day(s, biz):
        return next_open_day(s, biz, now().date())

    run("glow-salon", "9876500001", [("Kal shaam haircut karwana hai, naam Aman", ap.prepare_booking,
        lambda s, b: {"customer_name": "Aman", "service_id": svc("Haircut (men)")(s, b),
                      "start": f"{day(s, b)} 17:00"})])
    run("glow-salon", "9876500002", [("Facial book karna hai Simran ke saath", ap.prepare_booking,
        lambda s, b: {"customer_name": "Priya", "service_id": svc("Facial")(s, b), "start": f"{day(s, b)} 11:00"})],
        channel="whatsapp")
    run("sharma-kirana", "9876500003", [("2 packet atta aur 1 oil bhej do", orders.prepare_order, lambda s, b: {
        "items": [{"product_id": s.scalar(select(models.Product.id).where(models.Product.name == "Aashirvaad Atta")),
                   "qty": 2},
                  {"product_id": s.scalar(select(models.Product.id).where(models.Product.name == "Fortune Soyabean Oil")),
                   "qty": 1}],
        "customer_name": "Neha", "address": "14 Tripuri Town", "landmark": "near water tank", "pincode": "147002",
        "slot_date": (now().date() + timedelta(days=1)).isoformat(), "slot": "17:00-19:00", "payment_method": "upi"})])
    run("vidya-coaching", "9876500004", [("Bete ke liye class 11 non-medical aur JEE coaching", leads.save_lead,
        lambda s, b: {"need": "Class 11 non-medical with JEE foundation for son", "name": "Mr Bansal",
                      "budget": "4,000 a month", "location": "Model Town", "preferred_time": "this week"})])
    run("glow-salon", "9876500005", [("Bridal makeup package hai kya?", support.request_callback,
        lambda s, b: {"reason": "Asks about bridal makeup packages", "name": "Kiran"})])


if __name__ == "__main__":
    print("Seeded businesses", seed(reset="--reset" in sys.argv), f"(owner password: {DEMO_PASSWORD})")
    if "--demo-data" in sys.argv:
        demo_activity()
        print("Added sample activity")
