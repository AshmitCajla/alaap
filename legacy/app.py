"""Alaap contest demo: talk to the front desk, then see what the owner sees."""

import os

import gradio as gr
import pandas as pd

from alaap import db, seed
from alaap.engine import Conversation
from alaap.scheduling import FMT, now, profile, profile_text

BUSINESS_ID = seed.seed()
HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


# ---------- customer side ----------

def start(channel: str, phone: str):
    conv = Conversation(BUSINESS_ID, channel=channel, caller_phone=phone or None)
    return conv, [{"role": "assistant", "content": conv.greeting}], ""


def send(text: str, history: list, conv: Conversation | None, channel: str, phone: str):
    if not text.strip():
        return history, conv, ""
    if conv is None:
        conv, history, _ = start(channel, phone)
    history = history + [{"role": "user", "content": text}]
    try:
        answer = conv.reply(text)
    except Exception as e:  # show API/auth problems in the chat instead of a stack trace
        answer = f"[error: {type(e).__name__}: {e}]"
    return history + [{"role": "assistant", "content": answer}], conv, ""


# ---------- owner side ----------

def dashboard():
    with db.connect() as conn:
        appts = db.rows(
            conn,
            "SELECT a.ref, a.start_at AS time, s.name AS service, st.name AS staff, c.name AS customer,"
            " c.phone, a.status, a.channel FROM appointment a JOIN service s ON s.id = a.service_id"
            " JOIN staff st ON st.id = a.staff_id JOIN customer c ON c.id = a.customer_id"
            " WHERE a.business_id = ? AND a.start_at >= ? ORDER BY a.start_at",
            BUSINESS_ID, now().strftime("%Y-%m-%d 00:00"))
        outbox = db.rows(
            conn,
            "SELECT send_after, kind, to_phone, body, status FROM outbox WHERE business_id = ?"
            " ORDER BY id DESC LIMIT 50", BUSINESS_ID)
        callbacks = db.rows(
            conn,
            "SELECT created_at, name, phone, reason, status FROM callback WHERE business_id = ?"
            " ORDER BY id DESC", BUSINESS_ID)
        convs = db.rows(
            conn,
            "SELECT c.id, c.started_at, c.channel, c.caller_phone, COUNT(m.id) AS n FROM conversation c"
            " LEFT JOIN message m ON m.conversation_id = c.id WHERE c.business_id = ?"
            " GROUP BY c.id HAVING n > 1 ORDER BY c.id DESC LIMIT 30", BUSINESS_ID)
        today = now().strftime("%Y-%m-%d")
        stats = db.row(
            conn,
            "SELECT (SELECT COUNT(*) FROM appointment WHERE business_id = ? AND status = 'booked'"
            "        AND substr(created_at, 1, 10) = ?) AS booked_today,"
            " (SELECT COUNT(*) FROM appointment WHERE business_id = ? AND status = 'booked'"
            "        AND start_at >= ?) AS upcoming,"
            " (SELECT COUNT(*) FROM callback WHERE business_id = ? AND status = 'open') AS callbacks",
            BUSINESS_ID, today, BUSINESS_ID, now().strftime(FMT), BUSINESS_ID)
    summary = (f"**Booked by Alaap today:** {stats['booked_today']} · "
               f"**Upcoming:** {stats['upcoming']} · **Open callbacks:** {stats['callbacks']}")
    choices = [(f"#{c['id']} · {c['started_at']} · {c['channel']} · {c['caller_phone'] or 'unknown'}", c["id"])
               for c in convs]
    return (summary, _table(appts), _table(outbox), _table(callbacks),
            gr.update(choices=choices, value=choices[0][1] if choices else None))


def transcript(conversation_id):
    if not conversation_id:
        return ""
    with db.connect() as conn:
        msgs = db.rows(conn, "SELECT role, text FROM message WHERE conversation_id = ? ORDER BY id",
                       conversation_id)
    label = {"customer": "**Customer:**", "alaap": "**Alaap:**", "tool": "`tool`"}
    return "\n\n".join(f"{label[m['role']]} {m['text']}" for m in msgs)


def _table(items: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(items) if items else pd.DataFrame({"": ["(none yet)"]})


def business_profile():
    with db.connect() as conn:
        return "```\n" + profile_text(profile(conn, BUSINESS_ID)) + "\n```"


# ---------- UI ----------

with gr.Blocks(title="Alaap") as demo:
    gr.Markdown("# Alaap\nAI front desk for Indian businesses · demo salon in Patiala (sample data)")
    if not HAS_KEY:
        gr.Markdown("> **Set `ANTHROPIC_API_KEY`** (in `.env` or your shell) and restart to talk to Alaap.")

    with gr.Tab("Talk to Alaap"):
        conv_state = gr.State(None)
        with gr.Row():
            channel = gr.Radio(["phone", "whatsapp", "web"], value="phone", label="Channel")
            phone = gr.Textbox(label="Caller ID (mobile)", value="9876543210",
                               placeholder="Leave empty to make Alaap ask")
            new_btn = gr.Button("New call", variant="secondary")
        chat = gr.Chatbot(height=460, label="Conversation")
        msg = gr.Textbox(placeholder="Try: kal shaam 5 baje haircut book karna hai", show_label=False)
        gr.Examples(
            ["kal shaam haircut karwana hai", "Facial kitne ka hai?", "Parso Simran ke saath threading",
             "Mera appointment cancel kar do", "Tusi Monday nu khulle ho?"],
            inputs=msg)
        new_btn.click(start, [channel, phone], [conv_state, chat, msg])
        msg.submit(send, [msg, chat, conv_state, channel, phone], [chat, conv_state, msg])

    with gr.Tab("Owner dashboard") as owner_tab:
        refresh = gr.Button("Refresh")
        summary = gr.Markdown()
        gr.Markdown("### Upcoming appointments")
        appts = gr.Dataframe(interactive=False, wrap=True)
        gr.Markdown("### WhatsApp outbox (sending is Phase 1)")
        outbox = gr.Dataframe(interactive=False, wrap=True)
        gr.Markdown("### Callbacks requested")
        callbacks = gr.Dataframe(interactive=False, wrap=True)
        gr.Markdown("### Transcripts")
        pick = gr.Dropdown(label="Conversation", choices=[])
        text = gr.Markdown()
        outputs = [summary, appts, outbox, callbacks, pick]
        refresh.click(dashboard, None, outputs)
        owner_tab.select(dashboard, None, outputs)
        pick.change(transcript, pick, text)

    with gr.Tab("Business profile"):
        gr.Markdown("Alaap answers only from this profile.")
        gr.Markdown(business_profile())


if __name__ == "__main__":
    demo.launch()
