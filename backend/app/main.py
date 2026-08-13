"""Memory Inbox FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router, websocket_router
from app.config import get_settings
from app.database import engine, initialize_database
from app.telegram import telegram_bridge

settings = get_settings()
project_root = Path(__file__).resolve().parents[2]
frontend_dist = project_root / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await initialize_database()
    await telegram_bridge.initialize()
    telegram_bridge.start()
    yield
    await telegram_bridge.stop()
    await engine.dispose()


app = FastAPI(title="Memory Inbox API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(websocket_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/status")
async def status() -> dict[str, object]:
    """Safe runtime diagnostics; never returns the Telegram token."""
    return {"status": "healthy", "telegram": telegram_bridge.status()}


# Production uses one process: FastAPI serves the compiled PWA after all API
# and WebSocket routes. Vite remains available separately for frontend work.
if frontend_dist.is_dir():
    assets_dir = frontend_dist / "assets"
    icons_dir = frontend_dist / "icons"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")
    if icons_dir.is_dir():
        app.mount("/icons", StaticFiles(directory=icons_dir), name="frontend-icons")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def web_manifest() -> FileResponse:
        return FileResponse(frontend_dist / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/service-worker.js", include_in_schema=False)
    async def service_worker() -> FileResponse:
        return FileResponse(
            frontend_dist / "service-worker.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        candidate = (frontend_dist / path).resolve()
        if candidate.is_relative_to(frontend_dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")
