"""A sample salon for the demo. All details are made up."""

from pathlib import Path

from . import db

SALON = {
    "name": "Glow Unisex Salon",
    "kind": "salon",
    "phone": "+91 98XXX XXXXX",
    "owner_phone": "+91 98XXX XXXX1",
    "address": "Shop 12, Leela Bhawan Market",
    "city": "Patiala",
    "languages": "Punjabi, Hindi, English",
    "about": "Unisex salon near Leela Bhawan. Walk-ins welcome when a stylist is free.",
    "skills": "appointments,enquiries",
}

# weekday 0 = Monday. Closed on Mondays.
HOURS = {d: ("10:00", "20:00") for d in range(1, 7)}

SERVICES = [
    # name, minutes, price, notes
    ("Haircut (men)", 30, 200, None),
    ("Haircut (women)", 45, 400, "Price for shoulder-length hair; longer hair may cost more"),
    ("Beard trim", 15, 100, None),
    ("Hair colour", 90, 1200, "Global colour; product brand on request"),
    ("Facial", 60, 800, None),
    ("Threading (eyebrows)", 15, 50, None),
    ("Head massage", 30, 250, "With oil"),
]

STAFF = {
    "Gurpreet": ["Haircut (men)", "Beard trim", "Head massage"],
    "Simran": ["Haircut (women)", "Hair colour", "Facial", "Threading (eyebrows)"],
    "Raju": ["Haircut (men)", "Beard trim", "Hair colour", "Head massage"],
}

FAQS = [
    ("Payment methods", "UPI, cash and cards are accepted."),
    ("Parking", "Two-wheeler parking in front of the market; car parking at the Leela Bhawan lot."),
    ("Walk-ins", "Walk-ins are welcome, but booking avoids waiting."),
    ("Kids haircut", "Kids' haircuts are charged the same as men's haircut."),
]


def seed(path: Path | None = None) -> int:
    """Create the schema and the sample salon if it is not there. Returns its id."""
    db.init(path)
    with db.connect(path) as conn:
        existing = db.row(conn, "SELECT id FROM business WHERE name = ?", SALON["name"])
        if existing:
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO business (name, kind, phone, owner_phone, address, city, languages, about, skills)"
            " VALUES (:name, :kind, :phone, :owner_phone, :address, :city, :languages, :about, :skills)",
            SALON,
        )
        biz = cur.lastrowid
        for day, (opens, closes) in HOURS.items():
            conn.execute(
                "INSERT INTO business_hours VALUES (?, ?, ?, ?)", (biz, day, opens, closes)
            )
        service_ids = {}
        for name, minutes, price, notes in SERVICES:
            cur = conn.execute(
                "INSERT INTO service (business_id, name, duration_min, price_inr, notes) VALUES (?, ?, ?, ?, ?)",
                (biz, name, minutes, price, notes),
            )
            service_ids[name] = cur.lastrowid
        for person, services in STAFF.items():
            cur = conn.execute("INSERT INTO staff (business_id, name) VALUES (?, ?)", (biz, person))
            for s in services:
                conn.execute(
                    "INSERT INTO staff_service VALUES (?, ?)", (cur.lastrowid, service_ids[s])
                )
        for q, a in FAQS:
            conn.execute(
                "INSERT INTO faq (business_id, question, answer) VALUES (?, ?, ?)", (biz, q, a)
            )
        return biz


if __name__ == "__main__":
    print("Seeded business id", seed())
