import logging
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.rag import router as rag_router
from app.api.sharing import router as sharing_router
from app.core.config import settings
from app.core.database import engine
from app.core.init_db import init_db
from app.services.vector_store import get_qdrant

serve_api_docs = settings.docs_enabled and not settings.public_demo_mode
app = FastAPI(
    title="Secure Enterprise RAG",
    description="Private document search and question answering with JWT RBAC",
    version="1.1.0",
    docs_url="/docs" if serve_api_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if serve_api_docs else None,
)
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
frontend_assets = frontend_dist / "assets"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(rag_router, prefix=settings.api_prefix)
app.include_router(sharing_router, prefix=settings.api_prefix)


_signup_requests: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def request_timing_middleware(request, call_next):
    if settings.public_demo_mode and request.method == "POST" and request.url.path == f"{settings.api_prefix}/auth/register":
        # Cloudflare sets this header on proxied requests; the API remains bound to localhost.
        client_ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        attempts = _signup_requests[client_ip]
        while attempts and attempts[0] <= now - 3600:
            attempts.popleft()
        if len(attempts) >= 8:
            return JSONResponse(status_code=429, content={"detail": "Too many accounts created from this network recently. Try again later."})
        attempts.append(now)

    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        logging.getLogger("app.requests").exception(
            "request_failed request_id=%s method=%s duration_ms=%.1f",
            request_id, request.method, duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - started) * 1000
    route = request.scope.get("route")
    route_template = getattr(route, "path", "unmatched")
    response.headers["X-Request-ID"] = request_id
    logging.getLogger("app.requests").info(
        "request_complete request_id=%s method=%s route=%s status=%s duration_ms=%.1f",
        request_id, request.method, route_template, response.status_code, duration_ms,
    )
    return response

@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def root():
    index_file = frontend_dist / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {"message": "Secure Enterprise RAG API is running. Build the frontend to serve the website here."}


@app.get("/health")
def health_check():
    # Liveness probe: confirms that the API process is responding.
    return {"status": "healthy"}


@app.get("/health/ready")
def readiness_check():
    """Check the local services required to answer questions and index documents."""
    checks = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["postgres"] = "healthy"
    except Exception:
        checks["postgres"] = "unavailable"

    try:
        get_qdrant().get_collections()
        checks["qdrant"] = "healthy"
    except Exception:
        checks["qdrant"] = "unavailable"

    try:
        response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=3.0)
        response.raise_for_status()
        installed = {item.get("name", "") for item in response.json().get("models", [])}
        model_available = any(name == settings.ollama_model or name.startswith(f"{settings.ollama_model}:") for name in installed)
        checks["ollama"] = "healthy" if model_available else "model_missing"
    except Exception:
        checks["ollama"] = "unavailable"

    healthy = all(value == "healthy" for value in checks.values())
    body = {"status": "healthy" if healthy else "degraded", "checks": checks}
    return body if healthy else JSONResponse(status_code=503, content=body)


if frontend_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_assets), name="frontend-assets")


@app.get("/database/health")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"database": "connected", "status": "healthy"}
    except Exception:
        return {"database": "disconnected", "status": "unhealthy"}
