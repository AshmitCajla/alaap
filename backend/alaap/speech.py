"""Speech-to-text and text-to-speech behind one interface (Gnani by default),
so a second provider can be added later (Risks: depending on Gnani's API).

Gnani docs: https://docs.gnani.ai  (STT: Prisma, TTS: Timbre)."""

import io
import logging
import threading
import time
import wave
from dataclasses import dataclass
from typing import Protocol

import httpx

from . import config

log = logging.getLogger("alaap.speech")


@dataclass
class Transcript:
    text: str
    language: str | None = None


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes, filename: str = "audio.wav", content_type: str = "audio/wav",
                   keyterms: list[str] | None = None) -> Transcript: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str, *, sample_rate: int = 24000, container: str = "wav",
                   encoding: str = "linear_pcm", language: str = "auto", voice: str | None = None) -> bytes: ...


class SpeechError(RuntimeError):
    pass


class Gnani:
    """Gnani Vachana REST APIs. The account allows one request at a time, so calls are serialised."""

    _lock = threading.Lock()

    def __init__(self, api_key: str, base_url: str = config.GNANI_BASE_URL):
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(timeout=60, headers={"X-API-Key-ID": api_key})

    def _post(self, path: str, **kwargs) -> httpx.Response:
        for attempt in range(4):
            with self._lock:
                r = self.http.post(f"{self.base}{path}", **kwargs)
            if r.status_code != 429:
                break
            time.sleep(0.5 * (attempt + 1))  # RATE_LIMITED: no Retry-After header
        if r.status_code >= 400:
            raise SpeechError(f"Gnani {path} {r.status_code}: {r.text[:300]}")
        return r

    # Prisma speech-to-text: POST /stt/v3 (multipart, max 30 s of audio)
    def transcribe(self, audio: bytes, filename: str = "audio.wav", content_type: str = "audio/wav",
                   keyterms: list[str] | None = None) -> Transcript:
        data = {"language_code": config.GNANI_STT_LANGUAGE, "format": config.GNANI_STT_FORMAT}
        if config.GNANI_STT_MODEL and config.GNANI_STT_MODEL != "prisma-v2.5":
            data["model"] = config.GNANI_STT_MODEL
        if keyterms and data.get("model") == "prisma-v3.0":
            data["keyterms"] = ",".join(k for k in keyterms[:200] if k)
        r = self._post("/stt/v3", files={"audio_file": (filename, audio, content_type)}, data=data)
        body = r.json()
        if body.get("success") is False:
            raise SpeechError(f"Gnani STT: {body.get('error')}")
        return Transcript(body.get("transcript", "").strip(), body.get("detected_language_code"))

    # Timbre text-to-speech: POST /api/v1/tts/inference (returns raw audio bytes)
    def synthesize(self, text: str, *, sample_rate: int = 24000, container: str = "wav",
                   encoding: str = "linear_pcm", language: str = "auto", voice: str | None = None,
                   speed: float | None = None) -> bytes:
        body = {"text": text, "voice": voice or config.GNANI_TTS_VOICE, "model": config.GNANI_TTS_MODEL,
                "language": language, "speed": speed or 1.0,
                "audio_config": {"sample_rate": sample_rate, "num_channels": 1, "sample_width": 2,
                                 "encoding": encoding, "container": container}}
        return self._post("/api/v1/tts/inference", json=body).content


_gnani: Gnani | None = None


def provider() -> Gnani | None:
    """The configured speech provider, or None (then the web widget uses the browser's own speech)."""
    global _gnani
    if _gnani is None and config.GNANI_API_KEY:
        _gnani = Gnani(config.GNANI_API_KEY)
    return _gnani


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


# ---------- streaming (live calls) ----------

import asyncio  # noqa: E402
import base64  # noqa: E402
import json  # noqa: E402
from typing import AsyncIterator  # noqa: E402

import websockets  # noqa: E402


class StreamingTTS:
    """Gnani Timbre over WebSocket: first audio in ~0.2 s instead of ~1.4 s over REST.

    One request per connection (a second request on the same socket returns no audio), so we keep a
    spare connection open and swap it in for the next sentence."""

    URL = "wss://api.vachana.ai/api/v1/tts"

    def __init__(self, api_key: str, sample_rate: int, voice: str | None, speed: float | None):
        self.key, self.rate = api_key, sample_rate
        self.voice, self.speed = voice or config.GNANI_TTS_VOICE, speed or 1.0
        self._spare: asyncio.Task | None = None

    async def _connect(self):
        return await websockets.connect(self.URL, additional_headers={"X-API-Key-ID": self.key}, max_size=None,
                                        open_timeout=5)

    def warm(self) -> None:
        if self._spare is None or self._spare.done() and self._spare.exception():
            self._spare = asyncio.create_task(self._connect())

    async def _take(self):
        task, self._spare = self._spare, None
        ws = None
        if task:
            try:
                ws = await task
            except Exception:
                ws = None
        ws = ws or await self._connect()
        self.warm()
        return ws

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield raw 16-bit PCM chunks as Gnani produces them."""
        ws = await self._take()
        try:
            await ws.send(json.dumps({
                "text": text, "voice": self.voice, "model": config.GNANI_TTS_MODEL, "language": "auto",
                "speed": self.speed, "audio_config": {"sample_rate": self.rate, "num_channels": 1, "sample_width": 2,
                                                      "encoding": "linear_pcm", "container": "raw"}}))
            async for msg in ws:
                if isinstance(msg, bytes):
                    yield msg
                    continue
                data = json.loads(msg)
                kind = data.get("type")
                audio = (data.get("data") or {}).get("audio") if isinstance(data.get("data"), dict) else data.get("audio")
                if audio:
                    yield base64.b64decode(audio)
                if kind == "error":
                    raise SpeechError(f"Gnani TTS stream: {data.get('message')}")
                if kind in ("complete", "completed"):
                    break
        finally:
            await ws.close()

    async def close(self) -> None:
        if self._spare:
            self._spare.cancel()
            try:
                ws = await self._spare
                await ws.close()
            except BaseException:
                pass


class StreamingSTT:
    """Gnani Prisma over WebSocket. Gnani's own voice-activity detection ends each utterance, and the
    transcript arrives about as soon as the caller stops talking."""

    URL = "wss://api.vachana.ai/stt/v3/stream"
    FRAME = 1024  # the API wants 1,024-byte frames of 16-bit mono PCM

    def __init__(self, api_key: str, sample_rate: int, keyterms: list[str] | None = None):
        self.headers = {"x-api-key-id": api_key, "language_code": config.GNANI_STT_LANGUAGE,
                        "x-sample-rate": str(sample_rate), "format": config.GNANI_STT_FORMAT,
                        "x-idle-timeout-sec": "300", "x-min-silence-ms": "650"}
        if config.GNANI_STT_MODEL and config.GNANI_STT_MODEL != "prisma-v2.5":
            self.headers["model"] = config.GNANI_STT_MODEL
            if keyterms:
                self.headers["keyterms"] = ",".join(k for k in keyterms[:100] if k and k.isascii())
        self.ws = None
        self.buf = b""

    async def connect(self) -> None:
        self.ws = await websockets.connect(self.URL, additional_headers=self.headers, max_size=None, open_timeout=5)
        first = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=5))
        if first.get("type") == "error":
            raise SpeechError(f"Gnani STT stream: {first.get('message')}")

    async def send(self, pcm: bytes) -> None:
        self.buf += pcm
        while len(self.buf) >= self.FRAME:
            frame, self.buf = self.buf[: self.FRAME], self.buf[self.FRAME:]
            await self.ws.send(frame)

    async def events(self) -> AsyncIterator[dict]:
        async for msg in self.ws:
            if isinstance(msg, str):
                yield json.loads(msg)

    async def close(self) -> None:
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "commit"}))
            except Exception:
                pass
            await self.ws.close()
