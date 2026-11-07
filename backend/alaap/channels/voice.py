"""Live voice calls over a WebSocket media stream, built to feel like talking to a person.

Serves two callers with one protocol:
- Exotel's Voicebot applet (phone calls): 8 kHz 16-bit PCM, base64 in JSON events
  (`connected`, `start`, `media`, `stop`; we send `media`, `mark`, `clear`).
- The web widget's call screen: the same events at 16 kHz, plus `state` and `transcript` events for the UI.

What makes it feel human:
- Listening: Gnani's streaming STT ends each utterance with its own voice detection, so the transcript
  arrives as the caller stops talking (falls back to local endpointing + REST).
- Speaking early: the reply is streamed from the LLM sentence by sentence, and each sentence is streamed
  from Gnani's WebSocket TTS (~0.2 s to first audio), so Alaap starts talking while it is still thinking.
- Small acknowledgements: if the answer takes a moment, a short "achha" / "ek second ji" fills the gap.
- Interruptions: if the caller talks over Alaap, it stops mid-sentence and listens (noise-aware, so a
  fan or traffic doesn't cut it off).
- Silence: if the line goes quiet, Alaap checks in once, then says goodbye.
- Numbers are spoken as words ("saade chhe baje", "do sau rupaye")."""

import asyncio
import base64
import re
import json
import logging
import math
import random
import struct
import time

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from .. import config, db, models, speech
from ..engine import get_engine, is_female
from ..spoken import for_speech

log = logging.getLogger("alaap.voice")

FRAME_MS = 20
MIN_SPEECH_RMS = 450          # quietest level counted as speech
NOISE_FACTOR = 3.0            # speech must be this many times louder than the background
END_SILENCE_MS = 650          # local endpointing (fallback when STT streaming is unavailable)
MIN_SPEECH_MS = 250
MAX_UTTERANCE_MS = 25_000     # Gnani REST takes up to 30 s
BARGE_IN_MS = 350             # caller must talk this long over Alaap to interrupt
MERGE_WINDOW_S = 0.35         # wait this long for the rest of a sentence the STT split in two
SHORT_MERGE_S = 1.0           # ...longer after a short opener like "haan ji," that usually continues
MAX_MERGE_S = 4.0
GOODBYE_IN = re.compile(r"\b(bye|bas|thank|thanks|shukriya|dhanyavaad|dhanyawad|theek hai ji bas|alvida|"
                        r"rakhti|rakhta|chalo)\b|बस|धन्यवाद|शुक्रिया|thank|ਧੰਨਵਾਦ|ਬੱਸ", re.I)
GOODBYE_OUT = re.compile(r"(sat sri akal|alvida|phir milte|dhanyavaad|shukriya|namaste|bye|good ?day|take care)"
                         r"[^?]*[.!]?\s*$", re.I)
# A caller who only greets ("Sat Sri Akal ji." ... "kal haircut ho jayega?") is about to say why they called.
GREETING_ONLY = re.compile(r"^\W*((sat|saat|साठ|सत|ਸਤਿ|ਸਾਟ)\W*(sri|shri|श्री|श्रि|ਸ\S{0,3}ਰੀ)\W*(akal|अकाल|ਅਕਾਲ)|namaste|namaskar|"
                           r"नमस्ते|नमस्कार|ਨਮਸਤੇ|hello|hi|हेलो|हैलो|ਹੈਲੋ|haan ji|हाँ जी|हां जी|ਹਾਂ ਜੀ|ji|जी)"
                           r"(\W+(ji|जी|ਜੀ|sir|सर))*\W*$", re.I)
GREETING_MERGE_S = 1.8
ACK_AFTER_S = 1.1             # say "achha" if nothing has been said by then
FILLER_AFTER_S = 3.2          # say "ek second ji" if still nothing
SILENCE_PROMPT_S = 9.0        # "aap line par hain?"
SILENCE_HANGUP_S = 8.0        # ...then goodbye

ACKS = ["Achha.", "Haan ji.", "Ji.", "Hmm, achha."]
FILLERS_F = ["Ek second ji, dekh leti hoon.", "Ji, bas ek minute.", "Haan ji, check kar rahi hoon."]
FILLERS_M = ["Ek second ji, dekh leta hoon.", "Ji, bas ek minute.", "Haan ji, check kar raha hoon."]
_CLIPS: dict[tuple, bytes] = {}  # (text, voice, rate, speed) -> PCM, shared across calls


def rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if not n:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    return math.sqrt(sum(x * x for x in samples) / n)


class Endpointer:
    """Loudness-based speech detection with an adaptive noise floor.

    Used for barge-in always, and to cut utterances when streaming STT isn't available."""

    def __init__(self, sample_rate: int):
        self.rate = sample_rate
        self.frame_bytes = sample_rate * 2 * FRAME_MS // 1000
        self.buf = b""
        self.utt = bytearray()
        self.speech_ms = 0
        self.silence_ms = 0
        self.noise = 150.0  # running estimate of background loudness
        self.loud_run_ms = 0  # consecutive loud milliseconds (for barge-in)

    def threshold(self, strict: bool = False) -> float:
        t = max(MIN_SPEECH_RMS, self.noise * NOISE_FACTOR)
        return t * 1.5 if strict else t  # strict while Alaap is talking: ignore echo of our own voice

    def feed(self, pcm: bytes, strict: bool = False) -> list[bytes | str]:
        """Returns events: 'speech' when speech starts, and bytes for each finished utterance."""
        out: list[bytes | str] = []
        self.buf += pcm
        while len(self.buf) >= self.frame_bytes:
            frame, self.buf = self.buf[: self.frame_bytes], self.buf[self.frame_bytes:]
            level = rms(frame)
            loud = level > self.threshold(strict)
            if not loud:
                self.noise = 0.95 * self.noise + 0.05 * level  # only learn the floor from quiet frames
                self.loud_run_ms = 0
            else:
                self.loud_run_ms += FRAME_MS
            if loud:
                if self.speech_ms == 0:
                    out.append("speech")
                self.speech_ms += FRAME_MS
                self.silence_ms = 0
                self.utt += frame
            elif self.speech_ms:
                self.silence_ms += FRAME_MS
                self.utt += frame
            total = len(self.utt) * 1000 // (self.rate * 2)
            if self.speech_ms and (self.silence_ms >= END_SILENCE_MS or total >= MAX_UTTERANCE_MS):
                if self.speech_ms >= MIN_SPEECH_MS:
                    out.append(bytes(self.utt))
                self.utt, self.speech_ms, self.silence_ms = bytearray(), 0, 0
        return out


class CallSession:
    def __init__(self, ws: WebSocket, business_id: int | None, trust_caller_id: bool = False):
        self.ws = ws
        self.business_id = business_id
        # Only Exotel (authenticated by EXOTEL_WS_TOKEN) supplies a real caller number. A browser could claim anything.
        self.trust_caller_id = trust_caller_id
        self.rate = 8000
        self.stream_sid: str | None = None
        self.conversation_id: int | None = None
        self.started = time.time()
        self.voice: str | None = None
        self.speed: float | None = None
        self.female = True
        self.closing = False
        self.send_lock = asyncio.Lock()

        self.endpointer: Endpointer | None = None
        self.stt: speech.StreamingSTT | None = None
        self.tts: speech.StreamingTTS | None = None

        self.say_queue: asyncio.Queue = asyncio.Queue()
        self.speaker_task: asyncio.Task | None = None
        self.playing_until = 0.0     # when the audio already sent will have finished playing
        self.generation = 0          # bumps on barge-in; stale sentences are dropped
        self.turn_task: asyncio.Task | None = None
        self.pending_text: list[str] = []
        self.merge_task: asyncio.Task | None = None
        self.last_activity = time.time()
        self.prompted_silence = False
        self.caller_talking = False  # from the STT stream: between speech_start and its transcript

    # ---------- sending ----------
    async def _send(self, payload: dict) -> None:
        if self.closing:
            return
        async with self.send_lock:
            await self.ws.send_text(json.dumps(payload))

    async def _state(self, state: str) -> None:
        await self._send({"event": "state", "state": state})

    async def _send_pcm(self, pcm: bytes) -> None:
        chunk = self.rate * 2 // 10  # 100 ms; a multiple of 320 bytes as Exotel needs
        for i in range(0, len(pcm), chunk):
            piece = pcm[i:i + chunk]
            await self._send({"event": "media", "stream_sid": self.stream_sid,
                              "media": {"payload": base64.b64encode(piece).decode()}})
            self.playing_until = max(self.playing_until, time.time()) + len(piece) / (self.rate * 2)

    @property
    def speaking(self) -> bool:
        return time.time() < self.playing_until

    # ---------- speaking ----------
    def say(self, text: str, show: bool = True) -> None:
        """Queue a sentence to be spoken (thread-safe via call_soon_threadsafe from the engine)."""
        self.say_queue.put_nowait((self.generation, text, show))

    async def _speaker(self) -> None:
        """Speak queued sentences one after another, streaming each from TTS as it is produced."""
        while True:
            gen, text, show = await self.say_queue.get()
            if gen != self.generation or self.closing:
                continue
            await self._state("speaking")
            if show:
                await self._send({"event": "transcript", "role": "alaap", "text": text})
            spoken = for_speech(text)
            try:
                if self.tts:
                    async for pcm in self.tts.stream(spoken):
                        if gen != self.generation:
                            break  # interrupted
                        await self._send_pcm(pcm)
                else:
                    raise RuntimeError("no streaming TTS")
            except Exception as e:
                if gen != self.generation:
                    continue
                log.warning("streaming TTS failed (%s); using REST", e)
                pcm = await asyncio.to_thread(speech.provider().synthesize, spoken, sample_rate=self.rate,
                                              container="raw", voice=self.voice, speed=self.speed)
                if gen == self.generation:
                    await self._send_pcm(pcm)
            if gen == self.generation:
                await self._send({"event": "mark", "stream_sid": self.stream_sid, "mark": {"name": f"s{gen}"}})
            self.last_activity = max(self.last_activity, self.playing_until)

    async def clip(self, text: str) -> bytes:
        """Short fixed phrases (acks, fillers) are synthesised once and reused."""
        key = (text, self.voice, self.rate, self.speed)
        if key not in _CLIPS:
            _CLIPS[key] = await asyncio.to_thread(speech.provider().synthesize, text, sample_rate=self.rate,
                                                  container="raw", voice=self.voice, speed=self.speed)
        return _CLIPS[key]

    async def interrupt(self) -> None:
        """The caller started talking over Alaap: stop at once and listen."""
        self.generation += 1
        while not self.say_queue.empty():
            self.say_queue.get_nowait()
        self.playing_until = 0
        await self._send({"event": "clear", "stream_sid": self.stream_sid})
        await self._state("listening")

    # ---------- a caller turn ----------
    def heard(self, text: str) -> None:
        """A finished utterance. Wait briefly in case the STT split one sentence in two."""
        text = text.strip()
        if not text:
            return
        self.pending_text.append(text)
        self.caller_talking = False
        self.last_activity = time.time()
        self.prompted_silence = False
        self.caller_talking = False  # from the STT stream: between speech_start and its transcript
        if self.merge_task and not self.merge_task.done():
            self.merge_task.cancel()
        self.merge_task = asyncio.create_task(self._after_merge_window())

    async def _after_merge_window(self) -> None:
        so_far = " ".join(self.pending_text)
        # Short openers ("haan ji", "Sat Sri Akal ji") are usually followed by the actual request after a pause.
        if GREETING_ONLY.match(so_far):
            await asyncio.sleep(GREETING_MERGE_S)
        else:
            await asyncio.sleep(SHORT_MERGE_S if len(so_far.split()) <= 4 else MERGE_WINDOW_S)
        waited = time.time()
        while (self.caller_talking or self._mid_speech()) and time.time() - waited < MAX_MERGE_S:
            await asyncio.sleep(0.1)  # they're still talking; wait for the rest of the sentence
        if self.turn_task and not self.turn_task.done():
            await self.turn_task  # one turn at a time; the new words join the next turn
        text, self.pending_text = " ".join(self.pending_text), []
        if text:
            self.turn_task = asyncio.create_task(self.turn(text))

    def _mid_speech(self) -> bool:
        """The local detector hears the caller talking right now."""
        e = self.endpointer
        return bool(e and e.speech_ms)  # inside an utterance until 650 ms of silence

    async def turn(self, text: str) -> None:
        await self._send({"event": "transcript", "role": "customer", "text": text})
        await self._state("thinking")
        loop = asyncio.get_running_loop()
        gen = self.generation
        said = asyncio.Event()

        def on_sentence(sentence: str) -> None:  # called from the engine's thread
            loop.call_soon_threadsafe(said.set)
            loop.call_soon_threadsafe(self.say_queue.put_nowait, (gen, sentence, True))

        job = asyncio.create_task(asyncio.to_thread(get_engine().reply, self.conversation_id, text, on_sentence))
        first_words = asyncio.create_task(said.wait())
        # Fill the gap the way a person does while the answer is being worked out.
        for wait, phrases in ((ACK_AFTER_S, ACKS), (FILLER_AFTER_S - ACK_AFTER_S,
                                                   FILLERS_F if self.female else FILLERS_M)):
            await asyncio.wait({job, first_words}, timeout=wait, return_when=asyncio.FIRST_COMPLETED)
            if said.is_set() or job.done() or gen != self.generation:
                break
            try:
                await self._send_pcm(await self.clip(random.choice(phrases)))
            except Exception:
                log.exception("filler failed")
        first_words.cancel()
        reply = await job
        # Hang up after a goodbye even if the model forgot to call end_call.
        goodbye = GOODBYE_IN.search(text) and GOODBYE_OUT.search(reply.text or "") and "?" not in reply.text[-3:]
        if reply.handoff or reply.end or goodbye:
            await self._finish_after_speaking()

    async def _finish_after_speaking(self) -> None:
        while not self.say_queue.empty() or self.speaking:
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.4)
        await self.hangup()

    async def hangup(self) -> None:
        if not self.closing:
            self.closing = True
            try:
                await self.ws.close()
            except Exception:
                pass

    # ---------- watching for silence ----------
    async def _silence_watch(self) -> None:
        while not self.closing:
            await asyncio.sleep(1)
            if time.time() - self.started > config.MAX_CALL_MINUTES * 60:
                self.say("Maaf kijiye, call ka samay poora ho gaya. Baaki baat WhatsApp par ya dobara call karke "
                         "kar sakte hain. Dhanyavaad!")
                await self._finish_after_speaking()
                return
            busy = self.speaking or (self.turn_task and not self.turn_task.done()) or self.pending_text
            if busy:
                continue
            quiet = time.time() - max(self.last_activity, self.playing_until)
            if not self.prompted_silence and quiet > SILENCE_PROMPT_S:
                self.prompted_silence = True
                self.last_activity = time.time()
                self.say("Hello ji, aap line par hain?")
            elif self.prompted_silence and quiet > SILENCE_HANGUP_S:
                self.say("Lagta hai line kat gayi. Koi baat nahi ji, aap kabhi bhi dobara call kijiye. Dhanyavaad!")
                await self._finish_after_speaking()

    # ---------- streaming STT ----------
    async def _stt_reader(self) -> None:
        try:
            async for ev in self.stt.events():
                kind = ev.get("type")
                if kind == "transcript" and ev.get("text"):
                    self.heard(ev["text"])
                elif kind == "speech_start":
                    self.caller_talking = True
                    self.last_activity = time.time()
                elif kind == "error":
                    log.warning("STT stream error: %s", ev.get("message"))
        except Exception as e:
            if not self.closing:
                log.warning("STT stream closed (%s); switching to local endpointing", e)
        self.stt = None

    async def _rest_transcribe(self, utterance: bytes) -> None:
        heard = await asyncio.to_thread(speech.provider().transcribe, speech.pcm_to_wav(utterance, self.rate))
        self.heard(heard.text)

    # ---------- main loop ----------
    async def run(self) -> None:
        if not speech.provider():
            await self.ws.close(code=1011, reason="GNANI_API_KEY not set")
            return
        tasks: list[asyncio.Task] = []
        try:
            while not self.closing:
                event = json.loads(await self.ws.receive_text())
                kind = event.get("event")
                if kind == "start":
                    await self._start(event, tasks)
                elif kind == "media" and self.endpointer:
                    await self._media(base64.b64decode(event["media"]["payload"]))
                elif kind == "stop":
                    break
        except WebSocketDisconnect:
            pass
        except RuntimeError as e:  # socket closed by us
            if not self.closing:
                log.warning("call socket: %s", e)
        except Exception:
            log.exception("call failed")
        finally:
            self.closing = True
            for t in tasks + [self.turn_task, self.merge_task]:
                if t and not t.done():
                    t.cancel()
            for c in (self.stt, self.tts):
                if c:
                    try:
                        await c.close()
                    except Exception:
                        pass
            if self.conversation_id:
                await asyncio.to_thread(get_engine().end, self.conversation_id, int(time.time() - self.started))

    async def _start(self, event: dict, tasks: list) -> None:
        start = event.get("start", {})
        self.stream_sid = event.get("stream_sid") or start.get("stream_sid")
        self.rate = int(start.get("media_format", {}).get("sample_rate", 8000))
        self.endpointer = Endpointer(self.rate)
        custom = start.get("custom_parameters") or {}
        caller = (start.get("from") or custom.get("from")) if self.trust_caller_id else None
        if self.business_id is None:  # shared Exotel flow: route by the number the caller dialled
            dialled = start.get("to") or custom.get("to") or start.get("exophone") or custom.get("exophone")
            self.business_id = business_for_call(None, dialled)
            if not self.business_id:
                log.warning("Call to unknown number %s", dialled)
                self.closing = True
                await self.ws.close(code=1008, reason="number not assigned to a shop")
                raise WebSocketDisconnect(code=1008)
        keyterms = []
        with db.session() as s:
            biz = s.get(models.Business, self.business_id)
            self.voice, self.speed, self.female = biz.voice, biz.speech_speed, is_female(biz)
            # Bias recognition toward service and product words. Not people's names: that made the STT hear
            # a caller's own name ("Gurdeep") as a staff name ("Gurpreet").
            keyterms = [x.name for x in biz.services] + [x.name for x in biz.products]
        key = config.GNANI_API_KEY
        self.tts = speech.StreamingTTS(key, self.rate, self.voice, self.speed)
        self.tts.warm()
        try:
            self.stt = speech.StreamingSTT(key, self.rate, keyterms)
            await self.stt.connect()
            tasks.append(asyncio.create_task(self._stt_reader()))
        except Exception as e:
            log.warning("STT streaming unavailable (%s); using local endpointing", e)
            self.stt = None
        hello = await asyncio.to_thread(get_engine().start, self.business_id, "phone", caller, False,
                                        bool(caller and self.trust_caller_id))
        self.conversation_id = hello.conversation_id
        await self._send({"event": "conversation", "id": self.conversation_id})
        self.speaker_task = asyncio.create_task(self._speaker())
        tasks += [self.speaker_task, asyncio.create_task(self._silence_watch())]
        self.say(hello.text)
        # Warm the acknowledgement clips in the background so the first one plays instantly.
        tasks.append(asyncio.create_task(self._warm_clips()))

    async def _warm_clips(self) -> None:
        for text in ACKS + (FILLERS_F if self.female else FILLERS_M):
            try:
                await self.clip(text)
            except Exception:
                return

    async def _media(self, pcm: bytes) -> None:
        if self.stt:
            try:
                await self.stt.send(pcm)
            except Exception:
                self.stt = None
        strict = self.speaking
        for ev in self.endpointer.feed(pcm, strict=strict):
            if ev == "speech":
                self.last_activity = time.time()
            elif isinstance(ev, bytes) and not self.stt:
                asyncio.create_task(self._rest_transcribe(ev))
        if self.speaking and self.endpointer.loud_run_ms >= BARGE_IN_MS:
            self.endpointer.loud_run_ms = 0
            await self.interrupt()


def business_for_call(slug: str | None, to_number: str | None) -> int | None:
    with db.session() as s:
        q = select(models.Business.id)
        if slug:
            return s.scalar(q.where(models.Business.slug == slug))
        digits = re.sub(r"\D", "", to_number or "")
        if len(digits) >= 10:
            return s.scalar(q.where(models.Business.exotel_number == digits[-10:],
                                    models.Business.active.is_(True)))
    return None
