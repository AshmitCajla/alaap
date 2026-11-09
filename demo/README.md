# Alaap — product demo video

**`alaap-demo.mp4`** · 2:56 · 1920×1080, 30 fps · H.264 + AAC · −17 LUFS · English narration with burned-in captions
(`captions.srt` is the same captions as a separate file for upload sites).

| File | What it is |
|---|---|
| `alaap-demo.mp4` | The final video |
| `call-uncut.mp4` | The live call exactly as recorded (84 s, no pauses shortened, no captions) |
| `SCRIPT.md` | Narration with timestamps, plus the call transcript and English translations |
| `captions.srt` / `captions.ass` | Captions (plain / styled as burned in) |
| `narration.json`, `audio/` | Narration text and the Gnani TTS audio (narrator Devansh, caller Avinash) |
| `cards/` | The four title cards (HTML) |
| `assets/overlay.js`, `assets/callpanel.js` | Recording helpers injected into the browser (cursor, zoom, call audio capture, live-events panel) |
| `frames/` | Raw screencast frames per scene, timing (`meta.json`) and the call's audio/event log (`call_audio.json`) |
| `build/` | Per-scene clips and the mixed soundtrack |

## How it was made

1. **Real app, real models.** Every app scene is the running product (API on demo data, production dashboard build) driven
   by Playwright in Chromium and captured with the DevTools screencast. Nothing on screen is a mockup except the four title
   cards.
2. **The live call.** The browser's microphone was replaced by a synthesized caller voice (Gnani Timbre, voice Avinash)
   played on cue. From there it's the live pipeline: the widget streams the audio to the server → Gnani Prisma streaming
   speech recognition → Gemini with the booking tools → Gnani Timbre streaming speech → back to the browser. The audio you
   hear is the exact audio the page played, captured buffer by buffer with timestamps. The booking (ref 5161) was really
   created and shows up in the dashboard scene.
3. **Narration** is Gnani Timbre (voice Devansh); every line was checked by transcribing it back with Gnani Prisma.
4. **Assembly** (`assemble.py`): frames → constant 30 fps clips, crossfades, captions (libass), loudness normalised.

## Honesty notes

- The caller's voice is synthesized; this is said in the narration and on screen.
- In the call, silences longer than 0.6 s were shortened. Every shortened pause over 1.2 s is marked on screen with its
  real length ("Edited · 2.6 s pause shortened"). In this take the caller waited 2.3–3.0 s for Riya's first sound and
  2.6–4.9 s for her answer (free-tier Gemini). `call-uncut.mp4` is the unedited call.
- The call is cut after Riya's "anything else?"; in the full recording she says goodbye and ends the call when the caller
  thanks her.
- The right-hand panel in the call scene is a recording overlay that displays the server's real state/transcript events.
- Dashboard history (other bookings, conversations) is generated demo data. WhatsApp isn't connected in this demo, so
  messages show as queued/"Not sent", as the narration says.

## Rebuild

```bash
./demo.sh                                   # from the repo root: fresh demo data, API :8000, dashboard :3000
# or: production dashboard (no dev badge): cd dashboard && npx next build && npx next start -p 3000
cd demo
python3 -m venv .venv && .venv/bin/pip install playwright imageio-ffmpeg numpy && .venv/bin/playwright install chromium
ln -sf "$(.venv/bin/python -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')" ffmpeg
../.venv/bin/python make_audio.py           # narration + caller audio (Gnani TTS; cached in audio/)
.venv/bin/python record_all.py              # resets demo data and records every scene (~6 min, uses Gnani + Gemini)
# update call_captions.json if the call went differently (one English line per transcript event)
.venv/bin/python assemble.py && .venv/bin/python make_uncut.py && .venv/bin/python make_docs.py
```
