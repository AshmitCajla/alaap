"""Gnani client request shapes (against the documented API) and call endpointing."""

import json
import math
import struct

import httpx

from alaap import config, speech
from alaap.channels.voice import Endpointer


def tone(ms, rate=8000, amp=6000):
    n = rate * ms // 1000
    return struct.pack(f"<{n}h", *(int(amp * math.sin(2 * math.pi * 300 * i / rate)) for i in range(n)))


def silence(ms, rate=8000):
    return b"\x00\x00" * (rate * ms // 1000)


def test_endpointer_finds_one_utterance():
    ep = Endpointer(8000)
    events = ep.feed(silence(300) + tone(600) + silence(800))
    assert events[0] == "speech" and isinstance(events[1], bytes) and len(events) == 2
    assert ep.feed(tone(100) + silence(800)) == ["speech"]  # too short to count


def test_gnani_requests_match_docs(monkeypatch):
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if request.url.path == "/stt/v3":
            return httpx.Response(200, json={"success": True, "transcript": "kal shaam 5 baje",
                                             "detected_language_code": "hi-IN"})
        return httpx.Response(200, content=b"RIFFfakewav", headers={"content-type": "audio/wav"})

    g = speech.Gnani("test-key")
    g.http = httpx.Client(transport=httpx.MockTransport(handler), headers={"X-API-Key-ID": "test-key"})
    t = g.transcribe(b"RIFF....", keyterms=["Gurpreet", "Facial"])
    assert (t.text, t.language) == ("kal shaam 5 baje", "hi-IN")
    stt = seen[0]
    assert stt.headers["X-API-Key-ID"] == "test-key"
    body = stt.content.decode(errors="ignore")
    for field in ('name="audio_file"', 'name="language_code"', config.GNANI_STT_LANGUAGE, 'name="model"', "prisma-v3.0",
                  'name="keyterms"', "Gurpreet,Facial"):
        assert field in body

    audio = g.synthesize("Namaste", sample_rate=8000, container="raw", voice="Avinash")
    assert audio == b"RIFFfakewav"
    tts = json.loads(seen[1].content)
    assert seen[1].url.path == "/api/v1/tts/inference"
    assert tts["model"] == "timbre-v3.0" and tts["voice"] == "Avinash" and tts["language"] == "auto"
    assert tts["audio_config"] == {"sample_rate": 8000, "num_channels": 1, "sample_width": 2,
                                   "encoding": "linear_pcm", "container": "raw"}
