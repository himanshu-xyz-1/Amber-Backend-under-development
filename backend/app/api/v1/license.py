"""
Amber SRE Engine - License Management API Router.
Enables checking license status and dynamically activating Enterprise keys via Web UI or curl.
"""

import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.auth.security import AuthenticatedUser, require_api_key
from backend.app.core.config import settings
from backend.app.core.license import LicenseManager, license_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/license", tags=["License"])

DEFAULT_CONTACT_URL = "https://ambersre.xyz/#connect"


class LicenseActivateRequest(BaseModel):
    license_key: str


def _persist_license_to_env(key: str):
    """Safely updates or appends AMBER_LICENSE_KEY in .env file (skipped in test mode)."""
    if settings.ENVIRONMENT == "test":
        logger.debug("[TEST MODE] Skipping .env persistence of license key.")
        return

    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write(f"AMBER_LICENSE_KEY={key}\n")
        return

    with open(env_path) as f:
        content = f.read()

    if re.search(r"^AMBER_LICENSE_KEY=.*", content, re.MULTILINE):
        new_content = re.sub(r"^AMBER_LICENSE_KEY=.*", f"AMBER_LICENSE_KEY={key}", content, flags=re.MULTILINE)
    else:
        new_content = content.rstrip() + f"\n\n# Amber Commercial License Key\nAMBER_LICENSE_KEY={key}\n"

    with open(env_path, "w") as f:
        f.write(new_content)


@router.get("/status", status_code=status.HTTP_200_OK)
def get_license_status():
    """Returns current active commercial license details, capabilities, and purchase/contact link."""
    details = license_manager.get_license_details()
    contact_url = os.getenv("AMBER_CONTACT_URL", DEFAULT_CONTACT_URL)
    return {
        **details,
        "contact_url": contact_url,
        "get_key_url": contact_url
    }


@router.post("/activate", status_code=status.HTTP_200_OK)
def activate_license(
    req: LicenseActivateRequest,
    current_user: AuthenticatedUser = Depends(require_api_key)
):
    """
    Activates a newly purchased or issued Enterprise license key dynamically.
    Validates cryptographic signature, updates runtime state, and persists to .env.
    """
    token = req.license_key.strip()
    test_manager = LicenseManager(token=token)

    if not test_manager.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=test_manager.error_message or "Invalid or expired license key."
        )

    # Apply globally
    license_manager.reload(token)

    # Persist to disk
    try:
        _persist_license_to_env(token)
    except Exception as e:
        logger.warning(f"Could not persist AMBER_LICENSE_KEY to .env: {e}")

    logger.info(f"💎 Successfully activated Amber Enterprise license for '{test_manager.org}' ({test_manager.tier.upper()})")

    return {
        "success": True,
        "message": f"Amber Enterprise license successfully activated for '{test_manager.org}'!",
        "details": license_manager.get_license_details()
    }
