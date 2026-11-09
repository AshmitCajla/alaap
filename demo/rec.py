"""Recording helpers: Chromium via Playwright, frames via the Chrome DevTools screencast (with timestamps),
a visible cursor, smooth zooms/highlights, and the page's audio log for the call."""

import asyncio
import base64
import json
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
W, H = 1920, 1080


class Recorder:
    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(
            channel="chromium", headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream",
                  "--force-color-profile=srgb", "--hide-scrollbars"])
        self.ctx = await self.browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                                  color_scheme="light", permissions=["microphone"])
        await self.ctx.add_init_script(path=str(HERE / "assets" / "overlay.js"))
        self.page = await self.ctx.new_page()
        self.cdp = await self.ctx.new_cdp_session(self.page)
        self.frames = None
        self.cdp.on("Page.screencastFrame", self._frame)
        self.meta = json.loads((HERE / "frames" / "meta.json").read_text()) if (HERE / "frames" / "meta.json").exists() else {}
        return self

    async def stop(self):
        await self.browser.close()
        await self.pw.stop()

    # ---------- frames ----------
    def _frame(self, p):
        if self.frames is not None:
            path = self.dir / f"{len(self.frames):05d}.jpg"
            path.write_bytes(base64.b64decode(p["data"]))
            self.frames.append([p["metadata"]["timestamp"], path.name])
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]}))

    @asynccontextmanager
    async def scene(self, name):
        self.dir = FRAMES / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.frames = []
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H})
        await self.nudge()
        self.t0 = time.time()
        try:
            yield self
        finally:
            await self.nudge()
            await asyncio.sleep(0.15)
            end = time.time()
            await self.cdp.send("Page.stopScreencast")
            self.meta[name] = {"start": self.t0, "end": end, "frames": self.frames}
            self.frames = None
            (FRAMES / "meta.json").write_text(json.dumps(self.meta))
            print(f"  scene {name}: {end - self.t0:.1f}s, {len(self.meta[name]['frames'])} frames")

    async def nudge(self):
        """The screencast only sends frames when something changes; a 1px invisible toggle forces one."""
        await self.page.evaluate("""() => { let n = document.getElementById('__nudge');
          if (!n) { n = document.createElement('div'); n.id='__nudge';
            n.style.cssText='position:fixed;left:0;top:0;width:1px;height:1px;z-index:2147483647;pointer-events:none';
            document.body.appendChild(n); }
          n.style.background = n.style.background === 'rgba(0, 0, 0, 0.01)' ? 'rgba(0, 0, 0, 0.02)' : 'rgba(0, 0, 0, 0.01)'; }""")

    # ---------- timing ----------
    async def until(self, t):
        """Wait until t seconds after the scene started."""
        left = self.t0 + t - time.time()
        if left > 0:
            await asyncio.sleep(left)

    # ---------- interaction ----------
    async def center(self, loc):
        await loc.scroll_into_view_if_needed()
        b = await loc.bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    async def move(self, loc, ms=750):
        x, y = await self.center(loc)
        await self.page.evaluate("([x,y,ms]) => window.__demo.move(x,y,ms)", [x, y, ms])
        await asyncio.sleep(ms / 1000 + 0.1)
        return x, y

    async def click(self, loc, ms=750, pause=0.25):
        x, y = await self.move(loc, ms)
        await self.page.evaluate("([x,y]) => window.__demo.ripple(x,y)", [x, y])
        await asyncio.sleep(0.12)
        await loc.click()
        await asyncio.sleep(pause)

    async def type(self, loc, text, delay=38):
        await self.click(loc, pause=0.1)
        await loc.press_sequentially(text, delay=delay)

    async def zoom(self, loc, scale=1.35, ms=900):
        x, y = await self.center(loc)
        await self.page.evaluate("([x,y,s,ms]) => window.__demo.zoom(x,y,s,ms)", [x, y, scale, ms])
        await asyncio.sleep(ms / 1000)

    async def unzoom(self, ms=800):
        await self.page.evaluate("ms => window.__demo.unzoom(ms)", ms)
        await asyncio.sleep(ms / 1000)

    async def highlight(self, loc, ms=2600):
        h = await loc.element_handle()
        await self.page.evaluate("([el,ms]) => window.__demo.highlight(el,ms)", [h, ms])

    async def scroll(self, y, ms=1200):
        await self.page.evaluate("""([y,ms]) => new Promise(r => { const s = scrollY, t0 = performance.now();
          const f = (t) => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2;
            scrollTo(0, s + (y - s) * e); k < 1 ? requestAnimationFrame(f) : r(); }; requestAnimationFrame(f); })""", [y, ms])
