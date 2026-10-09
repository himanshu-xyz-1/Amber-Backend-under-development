"""
Amber Core Database Module.
Provides Async SQLAlchemy Engine, Session Factory, Declarative Base, and FastAPI session dependency.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from backend.app.core.config import settings

# 1. Engine configuration
# SQLite requires check_same_thread=False; PostgreSQL handles connections via asyncpg natively
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    connect_args=connect_args,
)

# 2. Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 3. Declarative Base for ORM models
Base = declarative_base()


# 4. FastAPI Dependency for Database Sessions
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session per request.
    Automatically commits on success, rolls back on error, and ensures clean closure.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
