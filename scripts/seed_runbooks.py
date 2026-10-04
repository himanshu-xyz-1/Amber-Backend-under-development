#!/usr/bin/env python3
"""
Amber Runbook Seeder.
Reads production markdown runbooks from data/runbooks/ and seeds them
into PostgreSQL for hybrid keyword and vector RAG retrieval.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal, engine, Base
from backend.app.models.runbook import Runbook

RUNBOOKS_DIR = Path(__file__).parent.parent / "data" / "runbooks"


async def seed():
    print(f"Reading runbooks from: {RUNBOOKS_DIR}")
    if not RUNBOOKS_DIR.exists():
        print(f"Error: {RUNBOOKS_DIR} does not exist!")
        return

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    md_files = list(RUNBOOKS_DIR.glob("*.md"))
    print(f"Found {len(md_files)} markdown runbooks.")

    async with AsyncSessionLocal() as session:
        for f in md_files:
            content = f.read_text(encoding="utf-8")
            title = f.stem.replace("_", " ").title()
            category = "infrastructure"

            # Parse simple header for category if available
            for line in content.splitlines():
                if line.startswith("**Category:**"):
                    category = line.replace("**Category:**", "").strip()
                    break
                elif line.startswith("# Runbook:"):
                    title = line.replace("# Runbook:", "").strip()

            # Check if runbook already exists
            existing = await session.execute(select(Runbook).filter(Runbook.title == title))
            rb = existing.scalar_one_or_none()

            if not rb:
                rb = Runbook(
                    title=title,
                    content=content,
                    category=category,
                    is_active=True,
                    version=1
                )
                session.add(rb)
                print(f"  + Added: '{title}' [{category}]")
            else:
                rb.content = content
                rb.category = category
                print(f"  * Updated: '{title}' [{category}]")

        await session.commit()
    print("✓ All runbooks successfully seeded into PostgreSQL!")


if __name__ == "__main__":
    asyncio.run(seed())
