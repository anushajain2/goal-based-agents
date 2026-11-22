"""FastAPI application.

    uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import auth
from app.api import campaigns, connections, events, guardrails, mcp, org, overview, plan, requests
from app.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await events.broadcaster.start()
    yield
    await events.broadcaster.stop()


app = FastAPI(title="Autopilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (auth, org, campaigns, requests, guardrails, connections, events, overview, plan, mcp):
    app.include_router(module.router)


@app.get("/api/health")
async def health():
    return {"ok": True}
