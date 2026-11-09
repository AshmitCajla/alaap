import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
HERE = Path(__file__).resolve().parent
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chromium")
        pg = await b.new_page(viewport={"width": 1920, "height": 1080})
        for name in ["hook", "gnani", "tech", "close"]:
            await pg.goto((HERE / "cards" / f"{name}.html").as_uri())
            await pg.evaluate("document.fonts.ready")
            for i in range(4):
                await pg.evaluate(f"step({i})")
            await asyncio.sleep(1.2)
            await pg.screenshot(path=str(HERE / "frames" / f"card_{name}.png"))
        await b.close()
asyncio.run(main())
