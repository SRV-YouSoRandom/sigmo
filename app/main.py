"""FastAPI application entry point."""

import logging

from fastapi import BackgroundTasks, FastAPI, Request
from prometheus_client import generate_latest
from starlette.responses import Response

from app.bot.handlers import process_update
from app.bot.notifier import close_client, register_bot_commands
from app.core.database import close_db, get_engine
from app.core.scheduler import scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sigmo Checklist Bot", version="1.0.0")


@app.on_event("startup")
async def startup() -> None:
    logger.info("Starting Sigmo bot")
    scheduler.start()
    logger.info("Scheduler started")
    await register_bot_commands()


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info("Shutting down Sigmo bot")
    scheduler.shutdown(wait=False)
    await close_client()
    await close_db()


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    data = await request.json()
    background_tasks.add_task(process_update, data)
    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    db_ok = False
    try:
        eng = get_engine()
        async with eng.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")