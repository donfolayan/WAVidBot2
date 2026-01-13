"""Main application entry point."""

import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .config.settings import Settings, get_settings
from .api.routes import router
from .services.cloud import CloudinaryService
from .services.database import DatabaseService
from .utils.logging import setup_logging, get_logger

# Load environment variables
load_dotenv()

# Get settings
settings = get_settings()

# Setup logging
setup_logging(log_level=settings.log_level, dev_mode=settings.dev_mode)
logger = get_logger(__name__)


async def cleanup_old_files() -> None:
    """Cleanup old files periodically."""
    logger.info("Starting cleanup task")
    cloud_service = CloudinaryService(settings)

    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            logger.info("Running periodic cleanup")
            cloud_service.cleanup_cloudinary_files()
        except Exception as e:
            logger.error("Error in cleanup task", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    # Startup
    logger.info(
        "Server starting up",
        app_name=settings.app_name,
        version="0.1.0",
        dev_mode=settings.dev_mode,
        base_url=settings.base_url,
        waha_url=settings.waha_base_url
    )

    # Initialize database
    try:
        db_service = DatabaseService(settings)
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise

    # Create downloads directory
    os.makedirs("downloads", exist_ok=True)
    logger.info("Downloads directory ready")

    # Start cleanup task
    cleanup_task = asyncio.create_task(cleanup_old_files())

    yield

    # Shutdown
    logger.info("Server shutting down")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


# Configure docs URLs based on development mode
docs_url = "/docs" if settings.dev_mode else None
redoc_url = "/redoc" if settings.dev_mode else None
openapi_url = "/openapi.json" if settings.dev_mode else None

# Create FastAPI app
app = FastAPI(
    title="WABotII - WhatsApp Video Downloader",
    description="""
    A FastAPI application that downloads videos from YouTube and Facebook via WhatsApp,
    using WAHA (WhatsApp HTTP API) for reliable WhatsApp connectivity.

    ## Features
    - Download videos from YouTube and Facebook
    - Send videos directly via WhatsApp (files < 16MB)
    - Upload to Cloudinary for shareable links
    - Automatic cleanup of old files
    - Download tracking and statistics

    ## Getting Started
    1. Start WAHA service: `docker-compose up waha`
    2. Scan QR code from WAHA admin panel
    3. Send WhatsApp message with video URL

    ## Endpoints
    - `GET /webhook` - WhatsApp webhook verification
    - `POST /webhook` - Receive WhatsApp messages
    - `GET /health` - Detailed health status
    - `GET /stats` - Download statistics
    - `GET /privacy` - Privacy Policy
    - `GET /terms` - Terms and Conditions
    - `POST /test-download` - Test download (DEV_MODE only)

    ## Security
    - All sensitive data via environment variables
    - API docs disabled in production (DEV_MODE=false)
    - CORS configured for webhook endpoints
    - Security headers added to all responses
    """,
    version="0.1.0",
    contact={
        "name": "WABotII",
        "url": "https://github.com/donfolayan/WABotII",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # WAHA webhooks can come from anywhere
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Mount downloads directory
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

# Include routes
app.include_router(router)

logger.info("FastAPI application created")
