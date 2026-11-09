"""Turn the recorded frames + captured call audio + Gnani narration into the final MP4 with captions.

  cd demo && .venv/bin/python assemble.py

Writes build/scene_*.mp4, build/audio.wav, captions.ass and alaap-demo.mp4."""

import base64
import io
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FR = HERE / "frames"
BUILD = HERE / "build"
FFMPEG = str(HERE / "ffmpeg")
FPS, SR, XF = 30, 48000, 0.4
ORDER = ["hook", "solution", "call_intro", "call", "dashboard", "gnani", "owner", "setup", "tech", "close"]
NAR_START, GAP = 0.5, 0.3
MAX_SILENCE = 0.6
META = json.loads((FR / "meta.json").read_text())
MAN = json.loads((HERE / "audio" / "manifest.json").read_text())
TRANSLATE = json.loads((HERE / "call_captions.json").read_text())


def read_wav(path):
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768, w.getframerate()


def resample(x, rate):
    if rate == SR:
        return x
    n = int(len(x) * SR / rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def rms_norm(x, target_db=-20.0):
    voiced = x[np.abs(x) > 0.01]
    if not len(voiced):
        return x
    rms = np.sqrt(np.mean(voiced ** 2))
    return x * (10 ** (target_db / 20) / rms)


def nar_starts(scene):
    t, out = NAR_START, []
    for it in MAN["scenes"][scene]:
        out.append(t)
        t += it["dur"] + GAP
    return out, t - GAP


# ---------- the call: captured audio, silence compression ----------

def call_material():
    d = json.loads((FR / "call_audio.json").read_text())
    m = META["call"]
    t0, dur = m["start"], m["end"] - m["start"]
    track = np.zeros(int((dur + 2) * SR), np.float32)
    busy, voice = [], {"app": [], "caller": []}
    for a in d["audio"]:
        if "b64" not in a:
            continue
        pcm = np.frombuffer(base64.b64decode(a["b64"]), np.int16).astype(np.float32) / 32768
        x = resample(pcm, a["rate"]) * (0.9 if a["tag"] == "caller" else 1.0)
        s = a["t"] / 1000 - t0
        i = int(s * SR)
        track[i:i + len(x)] += x[:max(0, len(track) - i)]
        busy.append([s, s + len(x) / SR])
        voice[a["tag"]].append([s, s + len(x) / SR])
    busy.sort()
    merged = []
    for s, e in busy:
        if merged and s <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    keep, cuts, cur = [], [], 0.0
    for i, (s, e) in enumerate(merged):
        if i == 0:
            keep.append([0.0, e])
        else:
            g = s - merged[i - 1][1]
            if g > MAX_SILENCE:
                half = MAX_SILENCE / 2
                keep[-1][1] = merged[i - 1][1] + half
                keep.append([s - half, e])
                cuts.append((merged[i - 1][1] + half, g))
            else:
                keep[-1][1] = e
    # Stop after Riya's "anything else?" (the goodbye exchange is cut for length), and skip most of "Connecting…".
    last_caller = max(s for s, _ in voice["caller"])
    end_at = max(e for s, e in merged if e < last_caller) + 1.0
    keep = [[max(s, merged[0][0] - 1.0) if i == 0 else s, min(e, end_at)] for i, (s, e) in enumerate(keep) if s < end_at]
    cuts = [(a, g) for a, g in cuts if a < end_at]
    return track, keep, cuts, d["events"], t0, voice["caller"]


def remap(keep):
    """Source time -> output time for kept spans."""
    spans, out = [], 0.0
    for s, e in keep:
        spans.append((s, e, out))
        out += e - s
    def f(t):
        for s, e, o in spans:
            if s <= t <= e:
                return o + t - s
        prev = [o + (e - s) for s, e, o in spans if e < t]
        return prev[-1] if prev else 0.0
    return f, out


# ---------- per-scene video from timestamped frames ----------

def render_scene(name, keep, length):
    m = META[name]
    t0, frames = m["start"], m["frames"]
    ts = [f[0] - t0 for f in frames]
    files = [str(FR / name / f[1]) for f in frames]
    lines, out_t, k = [], 0.0, 0
    total = int(round(length * FPS))
    spans, acc = [], 0.0
    for s, e in keep:
        spans.append((s, e, acc)); acc += e - s
    for n in range(total):
        t_out = n / FPS
        for s, e, o in spans:
            if t_out < o + (e - s) + 1e-9:
                src = s + (t_out - o)
                break
        else:
            src = spans[-1][1]
        while k + 1 < len(ts) and ts[k + 1] <= src:
            k += 1
        if k > 0 and ts[k] > src:
            k -= 1
        lines.append(f"file '{files[k]}'\nduration {1 / FPS:.6f}")
    lines.append(f"file '{files[k]}'")
    lst = BUILD / f"{name}.txt"
    lst.write_text("\n".join(lines))
    out = BUILD / f"scene_{name}.mp4"
    stamp = BUILD / f"scene_{name}.key"
    key = json.dumps([keep, length, len(frames), t0])
    if out.exists() and stamp.exists() and stamp.read_text() == key:
        return out
    stamp.write_text(key)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"fps={FPS},scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "16", "-r", str(FPS), str(out)], check=True)
    return out


# ---------- captions ----------

def ass_time(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def chunks(text, limit=84):
    """Split at clause boundaries (, ; : .) first, then pack clauses into caption-sized pieces."""
    import re
    clauses = [c.strip() for c in re.split(r"(?<=[,;:.])\s+", text) if c.strip()]
    out, cur = [], ""
    for c in clauses:
        if cur and len(cur) + len(c) + 1 > limit:
            out.append(cur); cur = c
        else:
            cur = f"{cur} {c}".strip()
        while len(cur) > limit:  # a single long clause: break at a space
            cut = cur.rfind(" ", 0, limit)
            out.append(cur[:cut]); cur = cur[cut + 1:]
    out.append(cur)
    return out


def main():
    BUILD.mkdir(exist_ok=True)
    track, keep_call, cuts, events, call_t0, caller_iv = call_material()
    f_call, call_len = remap(keep_call)

    lengths, keeps = {}, {}
    for name in ORDER:
        m = META[name]
        rec = m["end"] - m["start"]
        if name == "call":
            keeps[name], lengths[name] = keep_call, call_len
        else:
            if MAN["scenes"].get(name) and name in ("hook", "gnani", "tech", "close", "call_intro", "solution", "dashboard"):
                _, end = nar_starts(name)
                rec = min(rec, end + (1.3 if name == "close" else 0.5))
            keeps[name], lengths[name] = [[0.0, rec]], rec
    starts, g = {}, 0.0
    for name in ORDER:
        starts[name] = g
        g += lengths[name] - XF
    total = g + XF
    print(f"total {total:.1f}s: " + ", ".join(f"{n} {lengths[n]:.1f}" for n in ORDER))

    # ----- audio -----
    mix = np.zeros(int((total + 1) * SR), np.float32)
    def place(x, t, gain=1.0):
        i = int(t * SR)
        mix[i:i + len(x)] += x[:max(0, len(mix) - i)] * gain
    for name in ORDER:
        if name == "call":
            parts = [track[int(s * SR):int(e * SR)] for s, e in keep_call]
            call = np.concatenate(parts)
            fade = int(0.012 * SR)  # tiny fades at the cut points against clicks
            pos = 0
            for p in parts[:-1]:
                pos += len(p)
                call[pos - fade:pos] *= np.linspace(1, 0, fade)
                call[pos:pos + fade] *= np.linspace(0, 1, min(fade, len(call) - pos))
            place(rms_norm(call, -19), starts[name])
            continue
        s, _ = nar_starts(name) if MAN["scenes"].get(name) else ([], 0)
        for t, it in zip(s, MAN["scenes"].get(name, [])):
            x, rate = read_wav(HERE / "audio" / it["file"])
            place(rms_norm(resample(x, rate), -18), starts[name] + t)
    peak = np.max(np.abs(mix)) or 1
    mix = mix / max(1.0, peak / 0.95)
    with wave.open(str(BUILD / "audio.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix[:int(total * SR)], -1, 1) * 32767).astype(np.int16).tobytes())

    # ----- captions -----
    ev = []
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Nar,Avenir Next,42,&H00FFFFFF,&H00FFFFFF,&H82111A18,&H82111A18,1,0,0,0,100,100,0,0,3,14,0,2,200,200,56,1
Style: Call,Avenir Next,40,&H00FFFFFF,&H00FFFFFF,&H82111A18,&H82111A18,1,0,0,0,100,100,0,0,4,14,0,2,160,160,44,1
Style: Badge,Avenir Next,28,&H00FFFFFF,&H00FFFFFF,&H00317A0D,&H00317A0D,1,0,0,0,100,100,0,0,3,10,0,9,60,60,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    for name in ORDER:
        if name == "call" or not MAN["scenes"].get(name):
            continue
        s, _ = nar_starts(name)
        for t, it in zip(s, MAN["scenes"][name]):
            parts = chunks(it["text"])
            total_chars = sum(len(p) for p in parts)
            at = starts[name] + t
            for p in parts:
                d = it["dur"] * len(p) / total_chars
                ev.append(f"Dialogue: 0,{ass_time(at)},{ass_time(at + d)},Nar,,0,0,0,,{p}")
                at += d
    # call lines: the server's transcript events, with an English translation
    call_caps = []
    tr = [e for e in events if e["event"] == "transcript"]
    assert len(tr) == len(TRANSLATE), f"{len(tr)} transcript events, {len(TRANSLATE)} translations"
    for i, (e, en) in enumerate(zip(tr, TRANSLATE)):
        src = e["t"] / 1000 - call_t0
        if src > keep_call[-1][1]:
            continue
        nxt = tr[i + 1]["t"] / 1000 - call_t0 if i + 1 < len(tr) else src + 4
        if e["role"] == "customer":  # show it while the caller was speaking: from the start of their audio
            src = max(s for s, _ in caller_iv if s < src)
        a, b = f_call(src), min(f_call(nxt), f_call(src) + 7)
        who = "{\\c&HC8E65A&}Riya:{\\c&HFFFFFF&} " if e["role"] == "alaap" else "{\\c&H5CC8F0&}Caller:{\\c&HFFFFFF&} "
        call_caps.append([starts['call'] + a, starts['call'] + b, f"{who}{en['en']}"])
    call_caps.sort()
    for i, (a, b, text) in enumerate(call_caps):
        if i + 1 < len(call_caps):
            b = min(b, call_caps[i + 1][0])
        ev.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b - 0.04)},Call,,0,0,0,,{text}")
    for at, g in cuts:
        if g < 1.2:
            continue
        o = starts["call"] + f_call(at)
        ev.append(f"Dialogue: 1,{ass_time(o)},{ass_time(o + 1.6)},Badge,,0,0,0,,Edited · {g:.1f} s pause shortened")
    (HERE / "captions.ass").write_text(head + "\n".join(ev) + "\n")

    # ----- video -----
    clips = [render_scene(n, keeps[n], lengths[n]) for n in ORDER]
    inputs, fc, prev, off = [], [], "0:v", 0.0
    for c in clips:
        inputs += ["-i", str(c)]
    for i in range(1, len(clips)):
        off += lengths[ORDER[i - 1]] - XF
        out = f"v{i}"
        fc.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[{out}]")
        prev = out
    fc.append(f"[{prev}]ass={HERE / 'captions.ass'},fade=t=in:st=0:d=0.6,fade=t=out:st={total - 0.9:.2f}:d=0.9,"
              f"scale=in_range=pc:out_range=tv,format=yuv420p[vout]")
    fc.append(f"[{len(clips)}:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample={SR},afade=t=out:st={total - 0.9:.2f}:d=0.9[aout]")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *inputs, "-i", str(BUILD / "audio.wav"),
                    "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS),
                    "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart", "-shortest",
                    str(HERE / "alaap-demo.mp4")], check=True)
    print("wrote", HERE / "alaap-demo.mp4")


if __name__ == "__main__":
    main()
