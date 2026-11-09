"""Record the call-intro and live-call scenes, then save the page's audio + event log."""
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

from rec import FRAMES, HERE, Recorder

MAN = json.loads((HERE / "audio" / "manifest.json").read_text())
INTRO = sum(x["dur"] for x in MAN["scenes"]["call_intro"])


async def wait_reply(r, after, timeout=40):
    """Until Riya has answered something said after `after` (ms) and that audio has finished playing."""
    t = time.time()
    while time.time() - t < timeout:
        s = await r.page.evaluate("window.__demo.callState()")
        said = [e["t"] for e in s["events"] if e["event"] == "transcript" and e.get("role") == "alaap" and e["t"] > after]
        # done = Riya said something, its audio has started (text arrives just before audio) and fully played out
        if said and s["lastAt"] >= said[-1] - 50 and s["now"] > s["lastEnd"] + 1100 and s["now"] - s["lastAt"] > 2000:
            return True
        await asyncio.sleep(0.15)
    return False


async def main():
    r = await Recorder().start()
    p = r.page
    await p.goto("http://localhost:8000/c/glow-salon")
    await p.wait_for_selector(".alaap-callbtn")
    await p.add_script_tag(path=str(HERE / "assets" / "callpanel.js"))
    await p.evaluate("document.fonts.ready")
    await asyncio.sleep(1.5)
    call_btn = p.locator(".alaap-callbtn")

    async with r.scene("call_intro"):
        await r.until(INTRO * 0.55)
        await r.move(call_btn, 900)
        await r.highlight(call_btn, 2200)
        await r.until(INTRO + 0.6)

    async with r.scene("call"):
        await r.click(call_btn, ms=200)
        t0 = int(time.time() * 1000)
        ok = await wait_reply(r, t0)
        print("  greeting done", ok)
        for c in MAN["caller"]:
            await asyncio.sleep(0.5)
            b64 = base64.b64encode((HERE / "audio" / c["file"]).read_bytes()).decode()
            said = int(time.time() * 1000)
            dur = await p.evaluate("b => window.__callerSay(b)", b64)
            await asyncio.sleep(dur)
            ok = await wait_reply(r, said + int(dur * 1000))
            print(f"  line done {ok}: {c['text'][:40]}")
        # the call ends itself after the goodbye; let the screen settle
        await asyncio.sleep(2.5)

    dump = await p.evaluate("window.__demo.dump()")
    (FRAMES / "call_audio.json").write_text(json.dumps(dump))
    for e in dump["events"]:
        if e["event"] == "transcript":
            print(f"  {e['role']:8} {e['text']}")
    await r.stop()


if __name__ == "__main__":
    asyncio.run(main())
