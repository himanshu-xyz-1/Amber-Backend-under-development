from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.database import engine, Base
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.webhooks import router as webhook_router
from backend.app.api.v1.incidents import router as incident_router
from backend.app.api.v1.approvals import router as approval_router
from backend.app.api.v1.contact import router as contact_router
from backend.app.api.v1.license import router as license_router
from backend.app.api.v1.settings import router as settings_router
from backend.app.core.license import license_manager

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Amber API...")
    license_manager.print_startup_banner()
    
    # 1. Run database schema migrations
    try:
        import os
        import asyncio
        if os.path.exists("alembic.ini"):
            from alembic.config import Config
            from alembic import command
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
            await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
            logger.info("Database schema migrations successfully applied (Alembic head).")
        else:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.warning(f"Alembic auto-migration skipped or failed ({e}). Falling back to Base.metadata.create_all.")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    yield
    # Shutdown
    logger.info("Shutting down Amber API...")
    await engine.dispose()

app = FastAPI(
    title="Amber API",
    description="Autonomous Incident Remediation & SRE Engine",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(webhook_router, prefix=settings.API_V1_PREFIX)
app.include_router(incident_router, prefix=settings.API_V1_PREFIX)
app.include_router(approval_router, prefix=settings.API_V1_PREFIX)
app.include_router(contact_router, prefix=settings.API_V1_PREFIX)
app.include_router(license_router, prefix=settings.API_V1_PREFIX)
app.include_router(settings_router, prefix=settings.API_V1_PREFIX)

@app.get("/")
async def root():
    return {"app": "Amber", "status": "running", "docs": "/docs"}
