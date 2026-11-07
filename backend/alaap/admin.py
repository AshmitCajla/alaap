"""Operator commands.

  python -m alaap.admin check                         # configuration problems and warnings
  python -m alaap.admin businesses                    # list businesses with plan and status
  python -m alaap.admin reset-password EMAIL          # set a new password (prints it once)
  python -m alaap.admin set-plan SLUG PLAN [DAYS]     # e.g. comp a founding customer: set-plan glow-salon pro 365
  python -m alaap.admin deactivate SLUG               # stop a business answering (keeps its data)
  python -m alaap.admin seed-demo                     # add the three demo businesses
  python -m alaap.admin create-operator EMAIL [NAME]  # an Alaap team login for the operator console (/ops)
  python -m alaap.admin demo-reset                    # WIPE a *demo* database and fill it with fresh demo data
"""

import secrets
import sys
from datetime import timedelta

from sqlalchemy import select

from . import auth, billing, config, db, models
from .timeutil import now


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "check":
        problems = config.check()
        print("\n".join(problems) if problems else "All good.")
        return 1 if any(p.startswith("FATAL") for p in problems) else 0
    if cmd == "demo-reset":
        if "demo" not in config.DATABASE_URL and "--force" not in args:
            print(f"Refusing: DATABASE_URL ({config.DATABASE_URL}) doesn't look like a demo database.\n"
                  "Use e.g. DATABASE_URL=sqlite:///data/demo.db, or add --force if you're sure.")
            return 1
        from . import seed

        seed.demo_reset()
        print("Demo data ready: 3 shops, a week of history, team login team@alaap.dev, 2 free numbers. "
              f"Owner logins: owner@glow.demo / owner@kirana.demo / owner@coaching.demo (password {seed.DEMO_PASSWORD})")
        return 0
    db.create_all()
    with db.session() as s:
        if cmd == "businesses":
            for b in s.scalars(select(models.Business).order_by(models.Business.id)):
                st = billing.status(b)
                owner = s.scalar(select(models.OwnerUser.email).where(models.OwnerUser.business_id == b.id))
                print(f"{b.id:>4}  {b.slug:<28} {b.plan:<9} {st['state']:<8} until {st['until'] or '-':<10} "
                      f"{'active' if b.active else 'OFF':<6} {owner or ''}")
        elif cmd == "reset-password" and args:
            user = s.scalar(select(models.OwnerUser).where(models.OwnerUser.email == args[0].lower()))
            if not user:
                print("No such email")
                return 1
            password = secrets.token_urlsafe(9)
            user.password_hash = auth.hash_password(password)
            print(f"New password for {user.email}: {password}  (share it privately; they can change it in Settings)")
        elif cmd == "set-plan" and len(args) >= 2:
            biz = s.scalar(select(models.Business).where(models.Business.slug == args[0]))
            if not biz or args[1] not in ("starter", "pro", "business"):
                print("Usage: set-plan SLUG starter|pro|business [DAYS]")
                return 1
            biz.plan = args[1]
            biz.paid_until = now(biz.timezone) + timedelta(days=int(args[2]) if len(args) > 2 else 30)
            print(f"{biz.slug}: {biz.plan} until {biz.paid_until:%Y-%m-%d}")
        elif cmd == "deactivate" and args:
            biz = s.scalar(select(models.Business).where(models.Business.slug == args[0]))
            if not biz:
                print("No such business")
                return 1
            biz.active = False
            print(f"{biz.slug} deactivated")
        elif cmd == "create-operator" and args:
            email = args[0].lower().strip()
            op = s.scalar(select(models.Operator).where(models.Operator.email == email))
            password = secrets.token_urlsafe(12)
            if op:
                op.password_hash = auth.hash_password(password)
            else:
                s.add(models.Operator(email=email, name=" ".join(args[1:]) or None,
                                      password_hash=auth.hash_password(password)))
            print(f"Operator {email} password: {password}  (sign in at {config.DASHBOARD_URL}/ops)")
        elif cmd == "seed-demo":
            from . import seed

            print("Demo businesses:", seed.seed())
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
