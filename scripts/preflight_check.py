#!/usr/bin/env python3
"""
Amber Pre-Flight Verification & Environment Audit.
Validates database connectivity, redis queues, API keys, and environment variables
prior to starting or deploying Amber in production clusters.
"""

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.app.core.config import settings
from backend.app.core.database import engine
from sqlalchemy import text


async def check_all():
    print("=" * 60)
    print("🛡️  AMBER PRE-FLIGHT AUDIT & ENVIRONMENT CHECK")
    print("=" * 60)

    all_passed = True

    # 1. Check Python Version
    py_ver = sys.version.split()[0]
    print(f"[1] Python Runtime: {py_ver}", end=" ... ")
    if sys.version_info >= (3, 10):
        print("✓ PASS")
    else:
        print("❌ FAIL (Requires Python >= 3.10)")
        all_passed = False

    # 2. Check Database Connectivity
    print(f"[2] Database ({settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'local'}):", end=" ... ")
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1;"))
            val = res.scalar()
            if val == 1:
                print("✓ CONNECTED")
            else:
                print("❌ UNEXPECTED RESPONSE")
                all_passed = False
    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")
        all_passed = False

    # 3. Check Gemini API Key
    print(f"[3] Gemini GenAI Key:", end=" ... ")
    if settings.GEMINI_API_KEY:
        masked = settings.GEMINI_API_KEY[:4] + "..." + settings.GEMINI_API_KEY[-4:]
        print(f"✓ CONFIGURED ({masked})")
    else:
        print("⚠️  NOT SET (Agent will run in deterministic fallback mode)")

    # 4. Check Redis Configuration
    print(f"[4] Redis Stream Buffer:", end=" ... ")
    if settings.REDIS_URL:
        print(f"✓ CONFIGURED ({settings.REDIS_URL})")
    else:
        print("⚠️  DISABLED (Running in local direct-execution mode)")

    print("-" * 60)
    if all_passed:
        print("🎉 PRE-FLIGHT STATUS: ALL CRITICAL CHECKS PASSED. SYSTEM READY FOR INGESTION.")
    else:
        print("⚠️  PRE-FLIGHT STATUS: ONE OR MORE CHECKS FAILED. REVIEW CONFIGURATION.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(check_all())
