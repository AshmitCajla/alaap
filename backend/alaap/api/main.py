"""FastAPI app.  Run: uvicorn alaap.api.main:app --reload  (from backend/)"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .. import config, db, jobs
from . import owner, public, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).resolve().parent.parent / "static"


async def _job_loop():
    while True:
        await asyncio.to_thread(jobs.run_once)
        await asyncio.sleep(60)


log = logging.getLogger("alaap")


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = config.check()
    for p in problems:
        (log.error if p.startswith("FATAL") else log.warning)(p)
    if config.PRODUCTION and any(p.startswith("FATAL") for p in problems):
        raise SystemExit("Refusing to start in production with the problems above.")
    db.create_all()
    task = asyncio.create_task(_job_loop()) if config.RUN_JOBS else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Alaap", lifespan=lifespan)
# Owner endpoints use Bearer tokens (no cookies), so allowing other origins can't be used for CSRF;
# the widget must work on any shop's website.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if config.PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response
app.include_router(public.router)
app.include_router(webhooks.router)
app.include_router(owner.router)


@app.get("/widget.js")
def widget_js():
    return FileResponse(STATIC / "widget.js", media_type="application/javascript")


@app.get("/demo/{slug}", response_class=HTMLResponse)
def demo_page(slug: str):
    """A page that embeds the widget, for walk-in demos."""
    return (STATIC / "demo.html").read_text().replace("{{SLUG}}", slug)


@app.get("/c/{slug}", response_class=HTMLResponse)
def customer_page(slug: str):
    """The page a business shares with customers (QR poster, Instagram bio, Google profile)."""
    from html import escape

    from sqlalchemy import select

    from .. import models
    from ..engine import assistant_name
    from ..scheduling import hours_on
    from ..timeutil import now

    with db.session() as s:
        biz = s.scalar(select(models.Business).where(models.Business.slug == slug, models.Business.active.is_(True)))
        if not biz:
            return HTMLResponse("<h2>Not found</h2>", status_code=404)
        t = now(biz.timezone)
        hours = hours_on(s, biz, t.date())
        is_open = bool(hours and hours[0] <= t < hours[1])
        if is_open:
            open_text = f"Open now · till {hours[1]:%I:%M %p}".replace(" 0", " ")
        elif hours and t < hours[0]:
            open_text = f"Opens today at {hours[0]:%I:%M %p}".replace(" 0", " ")
        else:
            open_text = f"Closed now · {assistant_name(biz)} still answers"
        fields = {"NAME": biz.name, "KIND": biz.kind.replace("_", " ").title(), "CITY": biz.city or "",
                  "ADDRESS": biz.address or "", "SLUG": biz.slug, "ASSISTANT": assistant_name(biz),
                  "OPEN_CLASS": "yes" if is_open else "no", "OPEN_TEXT": open_text}
    html = (STATIC / "customer.html").read_text()
    for k, v in fields.items():
        html = html.replace("{{" + k + "}}", escape(str(v)))
    return html


@app.get("/", response_class=HTMLResponse)
def index():
    return (f'<p>Alaap API is running. Dashboard: <a href="{config.DASHBOARD_URL}">{config.DASHBOARD_URL}</a>. '
            f'Demos: <a href="/demo/glow-salon">salon</a>, <a href="/demo/sharma-kirana">kirana</a>, '
            f'<a href="/demo/vidya-coaching">coaching</a>.</p>')
