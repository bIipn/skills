"""FastAPI app: REST + WebSocket API and static dashboard host.

Run:  uvicorn backend.main:app --reload --port 8000
Then open http://localhost:8000
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .engine import engine

app = FastAPI(title="Polymarket Arbitrage Bot", version="0.1.0")

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@app.on_event("startup")
async def _startup():
    print("=" * 70)
    print("Polymarket Arbitrage Bot")
    print(settings.banner())
    print("=" * 70)
    app.state.engine_task = asyncio.create_task(engine.run())


@app.on_event("shutdown")
async def _shutdown():
    engine.stop()
    task = getattr(app.state, "engine_task", None)
    if task:
        task.cancel()


@app.get("/api/state")
async def get_state():
    return JSONResponse(engine.snapshot())


@app.get("/api/backtest")
async def run_backtest_endpoint(ticks: int = 200, seed: int = 42):
    # Run the (CPU-bound, deterministic) backtest off the event loop.
    from .backtest import run_backtest
    report = await asyncio.to_thread(run_backtest, min(ticks, 2000), seed)
    return JSONResponse(report.to_dict())


@app.get("/api/config")
async def get_config():
    return JSONResponse({
        "data_mode": settings.data_mode,
        "execution_live": settings.live_execution_enabled,
        "min_profit_threshold": settings.min_profit_threshold,
        "max_book_depth_fraction": settings.max_book_depth_fraction,
        "kelly_fraction": settings.kelly_fraction,
        "scan_interval_s": settings.scan_interval_s,
    })


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(json.dumps(engine.snapshot()))
            await asyncio.sleep(settings.scan_interval_s)
    except WebSocketDisconnect:
        return
    except Exception:
        return


@app.get("/")
async def index():
    return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))


if os.path.isdir(_FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")
