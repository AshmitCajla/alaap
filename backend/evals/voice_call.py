"""End-to-end voice test: a robot caller speaks (Gnani TTS) into a live call and listens to Alaap (Gnani STT -> LLM ->
Gnani TTS). Measures how long the caller waits after they stop talking, and checks the booking was saved.

  cd backend && ../.venv/bin/python -m evals.voice_call [slug]      # needs the API running on :8000

Costs a little Gnani + LLM credit per run."""

import asyncio
import base64
import json
import sys
import time

import websockets

from alaap import config, db, models, speech

RATE = 16000
FRAME = RATE * 2 // 50  # 20 ms of 16-bit PCM
LINES = [
    "Sat Sri Akal ji. Kal shaam saade chhe baje gents haircut ho jayega? Mera naam Rohit hai.",
    "Mera number hai nau aath ek do teen, chaar paanch chhe saat shunya.",
    "Haan ji, pakka kar do.",
    "Bas ji, bahut dhanyavaad.",
]


class Caller:
    def __init__(self, ws):
        self.ws = ws
        self.events = []          # (time, event dict)
        self.play_end = 0.0       # when the audio Alaap sent so far finishes playing
        self.last_media = 0.0
        self.conversation_id = None

    async def reader(self):
        async for raw in self.ws:
            ev = json.loads(raw)
            t = time.time()
            if ev.get("event") == "media":
                secs = len(base64.b64decode(ev["media"]["payload"])) / (RATE * 2)
                self.play_end = max(self.play_end, t) + secs
                self.last_media = t
            elif ev.get("event") == "conversation":
                self.conversation_id = ev["id"]
            self.events.append((t, ev))

    async def silence(self, seconds):
        for _ in range(int(seconds * 50)):
            await self.ws.send(json.dumps({"event": "media", "media": {"payload": base64.b64encode(bytes(FRAME)).decode()}}))
            await asyncio.sleep(0.02)

    async def say(self, pcm):
        for i in range(0, len(pcm), FRAME):
            chunk = pcm[i:i + FRAME].ljust(FRAME, b"\0")
            await self.ws.send(json.dumps({"event": "media", "media": {"payload": base64.b64encode(chunk).decode()}}))
            await asyncio.sleep(0.02)  # real time, like a microphone

    async def wait_reply_done(self, after, timeout=25):
        """Keep the line open (silence) until Alaap has answered and its audio has finished playing."""
        start = time.time()
        while time.time() - start < timeout:
            await self.silence(0.2)
            spoke = any(t > after and e.get("event") == "transcript" and e.get("role") == "alaap" for t, e in self.events)
            sounded = self.last_media > after  # the reply's audio has started arriving
            if spoke and sounded and time.time() > self.play_end + 0.7 and time.time() - self.last_media > 1.2:
                return True
        return False


async def main(slug):
    tts = speech.provider()
    clips = [tts.synthesize(line, sample_rate=RATE, container="raw", voice=None) for line in LINES]
    async with websockets.connect(f"ws://localhost:8000/ws/call/{slug}", max_size=None, ping_interval=None) as ws:
        c = Caller(ws)
        reader = asyncio.create_task(c.reader())
        await ws.send(json.dumps({"event": "start", "stream_sid": "voice-test",
                                  "start": {"media_format": {"encoding": "raw", "sample_rate": RATE}}}))
        t0 = time.time()
        await c.wait_reply_done(t0)
        greet = next((t for t, e in c.events if e.get("event") == "media"), None)
        print(f"greeting: first audio {greet - t0:.1f}s after connect\n" if greet else "greeting: NO AUDIO\n")
        waits = []
        try:
            await converse(c, clips, waits)
        except websockets.ConnectionClosed:
            print("(Alaap ended the call)\n")
        reader.cancel()
    with db.session() as s:
        appt = s.query(models.Appointment).filter_by(conversation_id=c.conversation_id).first()
        said = " ".join(e["text"] for _, e in c.events if e.get("event") == "transcript" and e.get("role") == "alaap")
        print("RESULT:", f"booking saved (ref {appt.ref}, {appt.start_at:%a %d %b %H:%M}, {appt.service.name})" if appt
              else "NO booking saved")
        if appt:
            print("Reference told to the caller correctly:", "YES" if appt.ref in said else f"NO (said: {said[-160:]})")
    if waits:
        print(f"Caller waited after speaking: avg {sum(waits) / len(waits):.1f}s, worst {max(waits):.1f}s")


async def converse(c, clips, waits):
        for line, pcm in zip(LINES, clips):
            await c.say(pcm)
            stopped = time.time()
            ok = await c.wait_reply_done(stopped)
            heard = [e["text"] for t, e in c.events if t > stopped - len(pcm) / (RATE * 2) and e.get("event") == "transcript" and e.get("role") == "customer"]
            replies = [(t, e["text"]) for t, e in c.events if t > stopped and e.get("event") == "transcript" and e.get("role") == "alaap"]
            first_sound = next((t for t, e in c.events if t > stopped and e.get("event") == "media"), None)
            print(f"caller said : {line}")
            print(f"Alaap heard : {' / '.join(heard) or '(nothing)'}")
            for t, text in replies:
                print(f"Alaap says  : {text}   [{t - stopped:.1f}s]")
            if first_sound:
                waits.append(first_sound - stopped)
                print(f"silence before Alaap made a sound: {first_sound - stopped:.1f}s{'' if ok else '  (TIMED OUT)'}\n")
            if c.events and c.events[-1][1].get("event") == "closed":
                break


if __name__ == "__main__":
    db.configure(config.DATABASE_URL)
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "glow-salon"))
