import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings, get_whisper_model
from app.core.database import db_manager
from app.routers import transcribe, auth, projects

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transcription-system")

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load the Whisper model
    logger.info("Starting up... loading global Whisper model.")
    try:
        get_whisper_model()
    except Exception as e:
        logger.error(f"Whisper model failed to load: {e} — continuing without it.")

    # Connect to MongoDB (non-fatal — auth routes return 503 if DB is down)
    logger.info("Connecting to MongoDB...")
    try:
        await db_manager.connect()
        logger.info("✅ MongoDB connected successfully.")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        logger.warning("Server will start but database-dependent routes will return 503.")

    yield

    logger.info("Shutting down... cleanup.")
    await db_manager.disconnect()

app = FastAPI(
    title=settings.app_name,
    description="Production-grade AI Video Transcription Backend",
    version="1.0.0",
    lifespan=lifespan
)

# ── CORS Middleware (must be added FIRST so it wraps everything) ───────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Global HTTP Exception Handler — ensures CORS headers on all errors ─────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception on {request.method} {request.url}: {exc}")
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers=headers,
    )

# ── Request Logging Middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    logger.info(f"→ {request.method} {request.url}")
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"← {response.status_code} ({process_time:.4f}s)")
    return response

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(transcribe.router)
app.include_router(auth.router)
app.include_router(projects.router)

# ── Static Files ───────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Health Check (with DB ping) ────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    db_status = "disconnected"
    try:
        if db_manager.client:
            await db_manager.client.admin.command("ping")
            db_status = "connected"
    except Exception:
        db_status = "error"
    return {
        "status": "ok",
        "app": settings.app_name,
        "database": db_status,
    }
