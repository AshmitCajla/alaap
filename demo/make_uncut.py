"""The full live call exactly as recorded: no pauses shortened, no captions. For transparency.
  cd demo && .venv/bin/python make_uncut.py"""
import subprocess, wave
import numpy as np
import assemble as A

track, keep, cuts, events, t0, caller = A.call_material()
m = A.META["call"]
dur = m["end"] - m["start"]
clip = A.render_scene("call", [[0.0, dur]], dur)
x = A.rms_norm(track[:int(dur * A.SR)], -19)
x = x / max(1.0, np.abs(x).max() / 0.95)
with wave.open(str(A.BUILD / "call_uncut.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(A.SR); w.writeframes((x * 32767).astype(np.int16).tobytes())
subprocess.run([A.FFMPEG, "-y", "-loglevel", "error", "-i", str(clip), "-i", str(A.BUILD / "call_uncut.wav"),
                "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-c:a", "aac",
                "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(A.HERE / "call-uncut.mp4")], check=True)
A.render_scene("call", keep, sum(e - s for s, e in keep))  # restore the edited clip in the cache
print("wrote call-uncut.mp4", round(dur, 1), "s")
