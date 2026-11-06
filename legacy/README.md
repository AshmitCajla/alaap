# Alaap — contest MVP (Nov 10)

An AI front desk for a sample salon in Patiala. It handles the **Appointments** and
**Enquiries** skills in Hindi, Punjabi, English or a mix, and shows the owner what happened.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your ANTHROPIC_API_KEY in it
.venv/bin/python app.py     # http://localhost:7860
.venv/bin/python -m pytest  # tests, no API key needed
```

## How it works

- `alaap/engine.py`: one conversation engine, a Claude tool-use loop. It builds its prompt and
  tools from the business's enabled skills.
- `alaap/skills/`: each skill is fields to collect, rules and tools. Add a skill to
  `skills/__init__.py` to support a new kind of business.
- `alaap/scheduling.py`: opening hours, free slots and booking checks, in plain code.
  This decides what is true; the model can't invent a slot or price.
- **Read-back before write.** `prepare_booking` / `prepare_reschedule` / `prepare_cancellation`
  only check and return a read-back. `confirm_action` saves, and refuses unless the customer has
  sent a message since the read-back. The slot is checked again at confirm time.
- `alaap/notify.py`: WhatsApp confirmations and 2-hour reminders go to an outbox table shown on
  the owner dashboard. Sending through the WhatsApp Cloud API is Phase 1.
- `alaap/speech.py`: speech-to-text and text-to-speech behind one interface. The Gnani classes
  are stubs to fill in from Gnani's API docs; until then the demo is text-only.

Settings (see `.env.example`): `ALAAP_MODEL` (default `claude-opus-5-5`), `ALAAP_EFFORT`
(default `low`, for short phone turns), `ALAAP_FALLBACKS` (server-side refusal fallback, on).

The salon, staff, prices and phone numbers in `alaap/seed.py` are made up.
