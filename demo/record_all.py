"""Record every scene of the demo from the running app (API :8000 on demo data, dashboard :3000).

  cd demo && .venv/bin/python record_all.py [scene ...]

Scenes are timed to the narration in audio/manifest.json. Frames go to frames/<scene>/, timing to frames/meta.json,
the call's audio/events to frames/call_audio.json and voice-preview audio to frames/media_<scene>.json."""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time

from rec import FRAMES, HERE, Recorder
from scene_call import wait_reply

MAN = json.loads((HERE / "audio" / "manifest.json").read_text())
NAR_START, GAP, TAIL = 0.5, 0.3, 0.8
ROOT = HERE.parent
DB = f"sqlite:///{ROOT / 'backend' / 'data' / 'demo.db'}"


def starts(scene):
    t, out = NAR_START, []
    for it in MAN["scenes"][scene]:
        out.append(t)
        t += it["dur"] + GAP
    return out, t - GAP


def card(name):
    return (HERE / "cards" / f"{name}.html").as_uri()


async def card_scene(r, name):
    s, end = starts(name)
    await r.page.goto(card(name))
    await r.page.evaluate("document.fonts.ready")
    await asyncio.sleep(0.6)
    async with r.scene(name):
        for i, t in enumerate(s):
            await r.until(t)
            await r.page.evaluate(f"step({i})")
        await r.until(end + TAIL + (1.2 if name == "close" else 0))


async def api_login(r, origin, path, body, key):
    await r.page.goto(origin + "/welcome" if "ops" not in key else origin + "/ops/login")
    tok = await r.page.evaluate("""async ([path, body]) => (await (await fetch('http://localhost:8000' + path,
        {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})).json()).token""",
                                [path, body])
    await r.page.evaluate("([k, t]) => localStorage.setItem(k, t)", [key, tok])
    return tok


async def scene_solution(r):
    s, end = starts("solution")
    p = r.page
    await p.goto("http://localhost:3000/welcome")
    await p.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)
    async with r.scene("solution"):
        await r.until(s[0] + 0.3)
        await r.highlight(p.locator("h1").first, 2400)
        await r.until(s[1] + 0.2)
        await r.highlight(p.locator("p.lead").first, 4200)
        await r.until(s[2] - 0.6)
        y = await p.evaluate("document.querySelector('.lp-feat').getBoundingClientRect().top + scrollY - 190")
        await r.scroll(y, 1300)
        await r.highlight(p.locator(".lp-feat .card").nth(2), 2600)
        await r.until(end + TAIL)


async def scene_call(r):
    p = r.page
    await p.goto("http://localhost:8000/c/glow-salon")
    await p.wait_for_selector(".alaap-callbtn")
    await p.add_script_tag(path=str(HERE / "assets" / "callpanel.js"))
    await p.evaluate("document.fonts.ready")
    await asyncio.sleep(1.5)
    btn = p.locator(".alaap-callbtn")
    s, end = starts("call_intro")
    async with r.scene("call_intro"):
        await r.until(end * 0.45)
        await r.move(btn, 900)
        await r.highlight(btn, 2200)
        await r.until(end + 0.4)
    async with r.scene("call"):
        await r.click(btn, ms=200)
        await p.evaluate("window.__demo.move(1500, 1150, 900)")  # cursor out of the way
        t0 = int(time.time() * 1000)
        print("  greeting", await wait_reply(r, t0))
        for c in MAN["caller"]:
            await asyncio.sleep(0.5)
            b64 = base64.b64encode((HERE / "audio" / c["file"]).read_bytes()).decode()
            said = int(time.time() * 1000)
            dur = await p.evaluate("b => window.__callerSay(b)", b64)
            await asyncio.sleep(dur)
            print("  line", await wait_reply(r, said + int(dur * 1000)), c["text"][:30])
        await asyncio.sleep(2.5)
    dump = await p.evaluate("window.__demo.dump()")
    (FRAMES / "call_audio.json").write_text(json.dumps(dump))
    for e in dump["events"]:
        if e["event"] == "transcript":
            print(f"    {e['role']:8} {e['text']}")


async def owner_login(r):
    await api_login(r, "http://localhost:3000", "/api/auth/login", {"email": "owner@glow.demo", "password": "demo1234"},
                    "alaap_token")


async def scene_dashboard(r):
    p = r.page
    await owner_login(r)
    await p.goto("http://localhost:3000/appointments")
    row = p.locator(".list-row", has_text="Rohit").first
    await row.wait_for()
    await asyncio.sleep(1.2)
    s, end = starts("dashboard")
    async with r.scene("dashboard"):
        await r.until(s[0] + 0.2)
        await r.highlight(row, 4200)
        await r.zoom(row, 1.3, 1000)
        await r.until(s[1] - 0.9)
        await r.unzoom(700)
        await r.click(p.locator("a.nav", has_text="Messages sent"), ms=700)
        conf = p.locator(".list-row", has_text="Booking confirmed").first
        await conf.wait_for()
        await asyncio.sleep(0.5)
        await r.highlight(conf, 3200)
        rem = p.locator(".list-row", has_text="Reminder").first
        await asyncio.sleep(1.6)
        await r.highlight(rem, 3000)
        await r.until(end + TAIL)


async def scene_voices(r):
    p = r.page
    await owner_login(r)
    await p.goto("http://localhost:3000/settings")
    tab = p.locator("button", has_text="Voice & assistant")
    await tab.wait_for()
    await asyncio.sleep(0.8)
    s, end = starts("voices")
    voice = p.locator(".grid .card", has_text="Kalpana").locator("button")
    async with r.scene("voices"):
        await r.until(0.3)
        await r.click(tab, ms=600)
        await asyncio.sleep(0.6)
        await r.highlight(p.locator(".grid").last, 2600)
        await r.until(end - 1.2)  # the preview takes ~1 s to synthesize, so it plays as the narration ends
        n = await p.evaluate("window.__demo.media.length")
        await r.click(voice, ms=500)
        while await p.evaluate("window.__demo.media.length") == n:
            await asyncio.sleep(0.1)
        src = await p.evaluate("window.__demo.media[window.__demo.media.length - 1].src")
        dur = (len(base64.b64decode(src.split(",", 1)[1])) - 44) / 2 / 24000
        await asyncio.sleep(dur + 0.8)
    (FRAMES / "media_voices.json").write_text(json.dumps(await p.evaluate("window.__demo.media")))


async def scene_owner(r):
    p = r.page
    await owner_login(r)
    await p.goto("http://localhost:3000/assistant")
    box = p.locator("input[aria-label=Message]")
    await box.wait_for()
    await p.wait_for_function("document.querySelectorAll('.msg.alaap').length >= 1 && !document.querySelector('.msg.alaap').textContent.includes('typing')")
    await asyncio.sleep(1.0)
    s, end = starts("owner")
    async with r.scene("owner"):
        await r.until(0.6)
        await r.type(box, "Facial ka rate 900 kar do", delay=45)
        await asyncio.sleep(0.3)
        await box.press("Enter")
        await p.wait_for_function("""() => { const m = [...document.querySelectorAll('.msg.alaap')];
            return m.length >= 2 && !m[m.length-1].textContent.includes('typing'); }""", timeout=40000)
        reply = p.locator(".msg.alaap").last
        await r.highlight(reply, 3200)
        t_reply = time.time() - r.t0
        await r.until(max(end + TAIL, t_reply + 3.0))


async def scene_setup(r):
    p = r.page
    await api_login(r, "http://localhost:3000", "/api/ops/auth/login", {"email": "team@alaap.dev", "password": "demo1234"},
                    "alaap_ops_token")
    shop = await p.evaluate("""async () => (await (await fetch('http://localhost:8000/api/ops/shops', {method: 'POST',
        headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('alaap_ops_token')},
        body: JSON.stringify({name: 'Kaur Beauty Parlour', kind: 'salon', city: 'Patiala', owner_name: 'Simran Kaur',
                              owner_phone: '98140' + String(Date.now()).slice(-5)})})).json())""")
    await p.goto(f"http://localhost:3000/ops/shops/{shop['id']}")
    area = p.locator("textarea").first
    await area.wait_for()
    await asyncio.sleep(1.0)
    s, end = starts("setup")
    async with r.scene("setup"):
        await r.until(0.5)
        await r.type(area, "Threading 40, Upper lip 20, Waxing full arms 250, Fruit facial 600, Gold facial 1200, "
                           "Haircut 300. 10am-8pm, Tuesday closed.", delay=14)
        await r.click(p.locator("button", has_text="Read it"), ms=500)
        await p.get_by_text("Check what Alaap read").wait_for(timeout=60000)
        table = p.locator(".card", has_text="Check what Alaap read").locator("table").first
        await table.wait_for()
        await asyncio.sleep(0.4)
        await r.highlight(table, 3500)
        await r.zoom(table, 1.18, 900)
        t_read = time.time() - r.t0
        await r.until(max(end + TAIL, t_read + 3.2))
        await r.unzoom(500)


async def main(only):
    if not only or "call" in only:
        subprocess.run([str(ROOT / ".venv" / "bin" / "python"), "-m", "alaap.admin", "demo-reset"], cwd=ROOT / "backend",
                       env={**os.environ, "DATABASE_URL": DB}, check=True, capture_output=True)
        print("demo data reset")
    r = await Recorder().start()
    plan = [("hook", lambda: card_scene(r, "hook")), ("solution", lambda: scene_solution(r)),
            ("call", lambda: scene_call(r)), ("dashboard", lambda: scene_dashboard(r)),
            ("gnani", lambda: card_scene(r, "gnani")), ("voices", lambda: scene_voices(r)),
            ("owner", lambda: scene_owner(r)), ("setup", lambda: scene_setup(r)),
            ("tech", lambda: card_scene(r, "tech")), ("close", lambda: card_scene(r, "close"))]
    for name, fn in plan:
        if only and name not in only:
            continue
        print("recording", name)
        await fn()
    await r.stop()


asyncio.run(main(set(sys.argv[1:])))
