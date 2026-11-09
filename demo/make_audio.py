"""Generate narration (one WAV per sentence) and caller lines with Gnani Timbre TTS. Run with the backend venv:
  cd demo && ../.venv/bin/python make_audio.py"""
import json, sys, wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from alaap import speech  # noqa: E402

RATE = 24000
HERE = Path(__file__).resolve().parent
OUT = HERE / "audio"
CALLER = [
    "Sat Sri Akal ji. Kal shaam saade chhe baje gents haircut ho jayega? Mera naam Rohit hai.",
    "Mera number hai nau aath ek do teen, chaar paanch chhe saat shunya.",
    "Haan ji, pakka kar do.",
    "Bas ji, bahut dhanyavaad.",
]


def save(path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
    return len(pcm) / 2 / RATE


def main():
    cfg = json.loads((HERE / "narration.json").read_text())
    gn = speech.provider()
    OUT.mkdir(exist_ok=True)
    manifest = {"scenes": {}, "caller": []}
    for sc in cfg["scenes"]:
        items = []
        for i, line in enumerate(sc["lines"]):
            p = OUT / f"nar_{sc['id']}_{i}.wav"
            if not p.exists():
                save(p, gn.synthesize(line, sample_rate=RATE, container="raw", voice=cfg["narrator_voice"]))
            with wave.open(str(p)) as w:
                items.append({"file": p.name, "text": line, "dur": w.getnframes() / RATE})
        manifest["scenes"][sc["id"]] = items
    for i, line in enumerate(CALLER):
        p = OUT / f"caller_{i}.wav"
        if not p.exists():
            save(p, gn.synthesize(line, sample_rate=RATE, container="raw", voice=cfg["caller_voice"]))
        with wave.open(str(p)) as w:
            manifest["caller"].append({"file": p.name, "text": line, "dur": w.getnframes() / RATE})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    for k, v in manifest["scenes"].items():
        print(f"{k:11} {sum(x['dur'] for x in v):5.1f}s")
    print("narration total", round(sum(x["dur"] for v in manifest["scenes"].values() for x in v), 1), "s")


main()
