"""LLM client for any OpenAI-compatible chat API.

Default is Google Gemini's free tier. Groq (free tier) and Ollama (local) work by
changing LLM_PROVIDER. Model names change often: set LLM_MODEL if the default
is retired (list models with `python -m alaap.llm`)."""

import json
import logging
import time

import openai
from openai import OpenAI

from . import config

log = logging.getLogger("alaap.llm")

PROVIDERS = {
    # provider: (base_url, env var holding the key, models to try in order)
    # Free tiers rate-limit each model separately and Google's endpoints are sometimes overloaded (503),
    # so a turn falls through to the next model instead of failing.
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY",
               ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3-flash-preview"]),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]),
    "ollama": ("http://localhost:11434/v1", None, ["qwen2.5:7b"]),
}
# Flash-Lite answers in ~1.5 s against ~3 s for Flash and has more free quota; for phone calls speed
# matters most, and the read-back + confirm rule keeps the data right either way.
# Worth trying another model for these; anything else (bad request, auth) is a real error.
FALLTHROUGH = (openai.RateLimitError, openai.InternalServerError, openai.NotFoundError, openai.APITimeoutError,
               openai.APIConnectionError)


class LLMNotConfigured(RuntimeError):
    pass


class LLM:
    def __init__(self, provider: str | None = None, model: str | None = None, client=None):
        self.provider = provider or config.LLM_PROVIDER
        base_url, key_env, defaults = PROVIDERS.get(self.provider, (None, None, []))
        chosen = model or config.LLM_MODEL
        self.models = [chosen] if chosen else list(defaults)
        extra = config.env("LLM_FALLBACK_MODELS")
        if extra:
            self.models += [m.strip() for m in extra.split(",") if m.strip() and m.strip() not in self.models]
        self.model = self.models[0] if self.models else None
        self._cooldown: dict[str, float] = {}
        key = config.LLM_API_KEY or (config.env(key_env) if key_env else None)
        self.ready = client is not None or bool(key) or key_env is None
        if client is not None:
            self.client = client
        else:
            key = key or "not-needed"
            self.client = OpenAI(base_url=config.LLM_BASE_URL or base_url, api_key=key, max_retries=0, timeout=6)  # fall through models instead

    def chat(self, messages: list[dict], tools: list[dict] | None = None, temperature: float | None = None,
             on_text=None) -> dict:
        """One completion. Returns the assistant message as a dict ready to append to history
        (keeps provider extras such as Gemini's thought signatures). With on_text, the reply is
        streamed and on_text(chunk) is called as text arrives, so speech can start early."""
        if not self.ready:
            raise LLMNotConfigured(f"Set {PROVIDERS.get(self.provider, (0, 'LLM_API_KEY'))[1]} in backend/.env")
        kwargs = {"messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        elif self.provider != "gemini":  # Gemini 3 works best at its default temperature
            kwargs["temperature"] = 0.3
        if self.provider == "gemini" and config.LLM_REASONING:
            kwargs["reasoning_effort"] = config.LLM_REASONING  # less thinking = faster replies on calls
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
        now_s = time.monotonic()
        # Models that recently hit a rate limit sit out for a minute; then try the last good one first.
        fresh = [m for m in self.models if self._cooldown.get(m, 0) <= now_s] or list(self.models)
        order = ([self.model] if self.model in fresh else []) + [m for m in fresh if m != self.model]
        emitted = [False]
        if on_text:
            user_cb = on_text

            def on_text(chunk, _cb=user_cb):
                emitted[0] = True
                _cb(chunk)
        for i, model in enumerate(order):
            t = time.perf_counter()
            try:
                out = self._stream(model, kwargs, on_text) if on_text else self._once(model, kwargs)
            except FALLTHROUGH as e:
                if emitted[0]:
                    raise  # part of the reply was already spoken; don't say it twice with another model
                if isinstance(e, openai.RateLimitError):
                    self._cooldown[model] = time.monotonic() + 60
                if i == len(order) - 1:
                    raise
                log.warning("llm %s unavailable (%s), trying %s", model, type(e).__name__, order[i + 1])
                continue
            self.model = model
            log.info("llm %s %.0f ms", model, (time.perf_counter() - t) * 1000)
            break
        out["role"] = "assistant"
        out["content"] = out.get("content") or ""
        for i, call in enumerate(out.get("tool_calls") or []):
            call["id"] = call.get("id") or f"call_{int(time.time() * 1000)}_{i}"
        if not out.get("tool_calls"):
            out.pop("tool_calls", None)
        return out

    def _once(self, model: str, kwargs: dict) -> dict:
        resp = self.client.chat.completions.create(model=model, **kwargs)
        return resp.choices[0].message.model_dump(exclude_none=True)

    def _stream(self, model: str, kwargs: dict, on_text) -> dict:
        text, calls = "", []
        stream = self.client.chat.completions.create(model=model, stream=True, **kwargs)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text += delta.content
                on_text(delta.content)
            for tc in delta.tool_calls or []:
                # Gemini sends each call whole with index=None; OpenAI-style APIs send pieces by index.
                if tc.index is not None and tc.index < len(calls) and not tc.id:
                    call = calls[tc.index]
                else:
                    call = {"id": tc.id, "type": "function", "function": {"name": "", "arguments": ""}}
                    calls.append(call)
                if tc.function and tc.function.name:
                    call["function"]["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    call["function"]["arguments"] += tc.function.arguments
                call.update(tc.model_extra or {})  # e.g. Gemini's extra_content thought signature
        return {"content": text, "tool_calls": calls}

    def text(self, prompt: str, system: str | None = None) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        return (self.chat(msgs).get("content") or "").strip()


def parse_args(raw: str | dict | None) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {"__invalid__": raw}


if __name__ == "__main__":
    llm = LLM()
    print(f"provider={llm.provider} model={llm.model}")
    try:
        print("models:", ", ".join(m.id for m in llm.client.models.list()))
    except Exception as e:  # not every provider lists models
        print("could not list models:", e)
    print(llm.text("Reply with one short Hinglish sentence greeting a salon customer."))
