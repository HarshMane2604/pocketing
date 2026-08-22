"""Pocketing FastAPI application."""

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import router, websocket_router
from app.config import get_settings
from app.database import engine, initialize_database
from app.telegram import telegram_bridge
from pocketing_logging.logger import setup_logging, get_backend_logger

settings = get_settings()
project_root = Path(__file__).resolve().parents[2]
frontend_dist = project_root / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    await initialize_database()
    await telegram_bridge.initialize()
    telegram_bridge.start()
    yield
    await telegram_bridge.stop()
    await engine.dispose()


app = FastAPI(title="Pocketing API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(websocket_router)


# ── API request/response logging middleware ────────────────────────────────────

# Paths that are too noisy or uninteresting for the log
_SKIP_PREFIXES = ("/ws", "/health", "/api/status", "/assets/", "/icons/", "/manifest", "/service-worker")


class APILoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip noisy endpoints
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        method = request.method
        query = str(request.query_params) if request.query_params else ""
        start = time.time()

        # Parse request body for write operations on /api/ routes
        # NOTE: We only read JSON bodies. Multipart form data CANNOT be read
        # here because consuming the stream would break the actual endpoint.
        req_summary = ""
        if path.startswith("/api/") and method in ("POST", "PATCH", "PUT"):
            content_type = request.headers.get("content-type", "")
            try:
                if "application/json" in content_type:
                    raw = await request.body()
                    req_summary = raw.decode("utf-8", errors="replace")[:500]
                elif "multipart/form-data" in content_type:
                    req_summary = "(multipart form data)"
            except Exception:
                req_summary = "(could not read body)"

        response: Response = await call_next(request)

        elapsed_ms = int((time.time() - start) * 1000)
        backend_log = get_backend_logger()

        # Build log line
        line = f"{method} {path}"
        if query:
            line += f"?{query}"
        line += f" → {response.status_code} ({elapsed_ms}ms)"

        backend_log.info(line)

        if req_summary:
            backend_log.info("  Request:  %s", req_summary)

        return response


app.add_middleware(APILoggingMiddleware)


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
