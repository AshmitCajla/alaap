"""Speech-to-text and text-to-speech behind one interface, so Gnani can be
swapped or a second provider added (see Risks: depending on Gnani's API).

The Gnani classes are placeholders: fill them in from the Prisma (STT) and
Timbre (TTS) API docs once you have keys. Until then the app runs text-only."""

import os
from typing import Protocol


class SpeechToText(Protocol):
    def transcribe(self, audio_path: str, language: str | None = None) -> str: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str, language: str | None = None) -> str:
        """Return a path to an audio file."""
        ...


class GnaniSTT:
    """Gnani Prisma speech-to-text. TODO: implement from Gnani's API docs."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio_path: str, language: str | None = None) -> str:
        raise NotImplementedError("Wire up Gnani Prisma here.")


class GnaniTTS:
    """Gnani Timbre text-to-speech. TODO: implement from Gnani's API docs."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def synthesize(self, text: str, language: str | None = None) -> str:
        raise NotImplementedError("Wire up Gnani Timbre here.")


def providers() -> tuple[SpeechToText | None, TextToSpeech | None]:
    """Configured providers, or (None, None) when no keys are set."""
    key = os.getenv("GNANI_API_KEY")
    if not key or os.getenv("ALAAP_VOICE", "0") != "1":
        return None, None
    return GnaniSTT(key), GnaniTTS(key)
