"""Background jobs, run every minute by the API process (or `python -m alaap.jobs`):
send the outbox, mark finished appointments, follow-ups, and the owner's daily voice summary."""

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select

from . import config, db, models, notify, speech
from .channels import whatsapp
from .llm import LLM
from .skills import owner as owner_skill
from .skills.base import Context
from .spoken import for_speech
from .timeutil import now

log = logging.getLogger("alaap.jobs")
LANG_NAMES = {"hi-IN": "Hindi", "pa-IN": "Punjabi", "en-IN": "English", "ta-IN": "Tamil", "te-IN": "Telugu",
              "bn-IN": "Bengali", "mr-IN": "Marathi", "gu-IN": "Gujarati", "kn-IN": "Kannada", "ml-IN": "Malayalam"}


# ---------- outbox ----------

def send_outbox(limit: int = 50) -> int:
    sent = 0
    with db.session() as s:
        items = s.scalars(select(models.Outbox).where(models.Outbox.status == "queued")
                          .order_by(models.Outbox.id).limit(limit)).all()
        for item in items:
            biz = s.get(models.Business, item.business_id)
            if item.send_after > now(biz.timezone):
                continue
            pnid = whatsapp.sender_id(biz)
            if not (whatsapp.enabled() and pnid):
                item.status = "logged"  # nowhere to send; stays visible on the dashboard
                continue
            body = whatsapp.labelled(biz, item.body)
            item.attempts += 1
            try:
                try:
                    if item.channel == "whatsapp_voice" and item.media_path:
                        with open(item.media_path, "rb") as f:
                            whatsapp.send_audio(pnid, item.to_phone, f.read())
                    whatsapp.send_text(pnid, item.to_phone, body)
                except Exception as e:
                    # Outside WhatsApp's 24-hour window only approved templates may be sent.
                    if not (whatsapp.needs_template(e) and config.WHATSAPP_TEMPLATE_NAME):
                        raise
                    whatsapp.send_template(pnid, item.to_phone, biz.name, item.body)
                item.status, item.sent_at = "sent", now(biz.timezone)
                sent += 1
            except Exception as e:  # e.g. outside the 24-hour window without an approved template
                item.error = str(e)[:500]
                item.status = "failed" if item.attempts >= 3 else "queued"
                log.warning("outbox %s failed: %s", item.id, e)
    return sent


# ---------- follow-ups ----------

def _has_followups(biz: models.Business) -> bool:
    return "followups" in biz.skill_list()


def mark_done_and_feedback() -> None:
    with db.session() as s:
        for biz in s.scalars(select(models.Business).where(models.Business.active.is_(True))):
            t = now(biz.timezone)
            appts = s.scalars(select(models.Appointment).where(
                models.Appointment.business_id == biz.id, models.Appointment.status == "booked",
                models.Appointment.end_at <= t)).all()
            for a in appts:
                a.status = "done"
                if _has_followups(biz) and not a.feedback_sent and a.end_at >= t - timedelta(hours=6):
                    notify.queue(s, biz, a.customer.phone, "feedback",
                                 f"Thank you for visiting {biz.name}! How was your {a.service.name} with {a.staff.name}? "
                                 f"Reply with 1 to 5 stars.", send_after=a.end_at + timedelta(hours=1),
                                 appointment_id=a.id)
                    a.feedback_sent = True


def reorder_reminders() -> None:
    with db.session() as s:
        for biz in s.scalars(select(models.Business).where(models.Business.active.is_(True))):
            if not _has_followups(biz):
                continue
            t = now(biz.timezone)
            rows = s.execute(
                select(models.Customer, models.Product, func.max(models.Order.created_at))
                .join(models.Order, models.Order.customer_id == models.Customer.id)
                .join(models.OrderItem, models.OrderItem.order_id == models.Order.id)
                .join(models.Product, models.Product.id == models.OrderItem.product_id)
                .where(models.Order.business_id == biz.id, models.Order.status != "cancelled",
                       models.Product.reorder_days.is_not(None))
                .group_by(models.Customer.id, models.Product.id)).all()
            for cust, prod, last in rows:
                due = last + timedelta(days=prod.reorder_days)
                if not (due <= t < due + timedelta(days=3)):
                    continue
                already = s.scalar(select(models.Outbox.id).where(
                    models.Outbox.business_id == biz.id, models.Outbox.to_phone == cust.phone,
                    models.Outbox.kind == "reorder", models.Outbox.created_at >= last,
                    models.Outbox.body.contains(prod.name)))
                if not already:
                    notify.queue(s, biz, cust.phone, "reorder",
                                 f"Namaste {cust.name}! Running low on {prod.name}? Reply 'haan' and {biz.name} "
                                 f"will deliver it again.")


def winback_and_leads() -> None:
    with db.session() as s:
        for biz in s.scalars(select(models.Business).where(models.Business.active.is_(True))):
            if not _has_followups(biz):
                continue
            t = now(biz.timezone)
            lost = s.scalars(select(models.Customer).where(
                models.Customer.business_id == biz.id, models.Customer.last_seen_at < t - timedelta(days=60),
                (models.Customer.winback_sent_at.is_(None)) | (models.Customer.winback_sent_at < t - timedelta(days=90)))
                .limit(20)).all()
            for c in lost:
                notify.queue(s, biz, c.phone, "winback",
                             f"We miss you at {biz.name}, {c.name}! Reply here to book or order; we'll take care of you.")
                c.winback_sent_at = t
            for lead in s.scalars(select(models.Lead).where(
                    models.Lead.business_id == biz.id, models.Lead.status == "new", models.Lead.followup_sent.is_(False),
                    models.Lead.created_at < t - timedelta(hours=24))):
                notify.queue(s, biz, lead.phone, "lead_followup",
                             f"Namaste{' ' + lead.name if lead.name else ''}! {biz.name} here about your enquiry. "
                             f"Would you like to book a visit? Reply with a day and time that suits you.")
                notify.owner_alert(s, biz, f"Lead still new after a day: {lead.name or ''} {lead.phone} - {lead.need}")
                lead.followup_sent = True


# ---------- privacy and billing ----------

def purge_old_data() -> int:
    """Delete conversations and transcripts older than RETENTION_DAYS (bookings and orders stay)."""
    if config.RETENTION_DAYS <= 0:
        return 0
    cutoff = now() - timedelta(days=config.RETENTION_DAYS)
    with db.session() as s:
        ids = list(s.scalars(select(models.Conversation.id).where(models.Conversation.started_at < cutoff).limit(5000)))
        if ids:
            s.execute(models.Message.__table__.delete().where(models.Message.conversation_id.in_(ids)))
            s.execute(models.Conversation.__table__.delete().where(models.Conversation.id.in_(ids)))
    for f in config.MEDIA_DIR.glob("*") if config.MEDIA_DIR.exists() else []:
        if f.is_file() and f.stat().st_mtime < time.time() - config.RETENTION_DAYS * 86400:
            f.unlink(missing_ok=True)
    return len(ids)


def billing_reminders() -> None:
    """Remind the owner on WhatsApp 3 days and 1 day before the trial or plan ends."""
    from . import billing

    with db.session() as s:
        for biz in s.scalars(select(models.Business).where(models.Business.active.is_(True))):
            st = billing.status(biz)
            if st["state"] not in ("trial", "active") or st["days_left"] not in (1, 3):
                continue
            since = now(biz.timezone) - timedelta(hours=20)
            if s.scalar(select(models.Outbox.id).where(models.Outbox.business_id == biz.id,
                                                       models.Outbox.kind == "billing",
                                                       models.Outbox.created_at >= since)):
                continue
            what = "free trial" if st["state"] == "trial" else f"{biz.plan.title()} plan"
            notify.queue(s, biz, biz.owner_phone, "billing",
                         f"Your Alaap {what} ends in {st['days_left']} day(s). Renew from the dashboard "
                         f"({config.DASHBOARD_URL}/billing) so customers keep getting answers.")


# ---------- owner's daily summary ----------

def daily_summaries(llm: LLM | None = None, force: bool = False) -> int:
    done = 0
    with db.session() as s:
        businesses = s.scalars(select(models.Business).where(models.Business.active.is_(True))).all()
        todo = []
        for biz in businesses:
            t = now(biz.timezone)
            if not force and t.hour < config.DAILY_SUMMARY_HOUR:
                continue
            start = datetime.combine(t.date(), datetime.min.time())
            if not force and s.scalar(select(models.Outbox.id).where(
                    models.Outbox.business_id == biz.id, models.Outbox.kind == "daily_summary",
                    models.Outbox.created_at >= start)):
                continue
            ctx = Context(business_id=biz.id, conversation_id=0, tz=biz.timezone, is_owner=True)
            todo.append((biz.id, owner_skill.get_stats(ctx, s), owner_skill.list_schedule(
                ctx, s, (t + timedelta(days=1)).date().isoformat())))
    for biz_id, stats, tomorrow in todo:
        with db.session() as s:
            biz = s.get(models.Business, biz_id)
            lang = LANG_NAMES.get(biz.owner_language, "Hindi")
            text = _summary_text(llm, biz, stats, tomorrow, lang)
            media = None
            tts = speech.provider()
            if tts:
                try:
                    ogg = tts.synthesize(for_speech(text), sample_rate=24000, container="ogg", encoding="oggopus",
                                         voice=biz.voice, speed=biz.speech_speed)
                    path = config.MEDIA_DIR / f"summary-{biz.id}-{stats['date']}.ogg"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(ogg)
                    media = str(path)
                except Exception:
                    log.exception("summary TTS failed")
            notify.queue(s, biz, biz.owner_phone, "daily_summary", text,
                         channel="whatsapp_voice" if media else "whatsapp", media_path=media)
            done += 1
    return done


def _summary_text(llm, biz, stats, tomorrow, lang) -> str:
    fallback = (f"Aaj {stats['appointments_booked_by_alaap']} booking aur {stats['orders']} order aaye, "
                f"kul {stats['order_value_inr']} rupaye. {stats['new_leads']} naye leads, "
                f"{stats['open_callbacks_and_complaints']} callback ya complaint baaki. "
                f"Kal {len(tomorrow['appointments'])} appointment aur {len(tomorrow['deliveries'])} delivery hain.")
    try:
        llm = llm or LLM()
        return llm.text(
            f"Today's numbers for {biz.name}: {stats}. Tomorrow: {tomorrow}.",
            system=f"You write a 20-second spoken end-of-day update for the owner {biz.owner_name or ''} of a small "
                   f"Indian business, in {lang} (Roman script is fine for Hindi/Punjabi). Three or four short "
                   f"sentences: what Alaap handled today, money, anything needing attention, tomorrow's first item. "
                   f"Spell numbers as spoken. No lists or markdown.") or fallback
    except Exception as e:
        log.warning("summary LLM failed, using template: %s", e)
        return fallback


JOBS_LOCK = 724_105  # any constant; Postgres advisory lock id for "Alaap jobs"


def run_once() -> None:
    """Run all jobs once. With Postgres, an advisory lock makes sure only one server runs them at a time."""
    eng = db.engine()
    if eng.dialect.name == "postgresql":
        from sqlalchemy import text

        with eng.connect() as conn:
            if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": JOBS_LOCK}).scalar():
                return  # another worker is on it
            try:
                _run_jobs()
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": JOBS_LOCK})
                conn.commit()
    else:
        _run_jobs()


def _run_jobs() -> None:
    for job in (mark_done_and_feedback, reorder_reminders, winback_and_leads, daily_summaries, purge_old_data,
                billing_reminders, send_outbox):
        try:
            job()
        except Exception:
            log.exception("job %s failed", job.__name__)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.create_all()
    log.info("Alaap jobs worker started")
    while True:
        run_once()
        time.sleep(60)
