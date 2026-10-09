from backend.app.api.v1.approvals import router as approvals_router
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.contact import router as contact_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.incidents import router as incidents_router
from backend.app.api.v1.license import router as license_router
from backend.app.api.v1.settings import router as settings_router
from backend.app.api.v1.webhooks import router as webhooks_router

__all__ = [
    "approvals_router",
    "auth_router",
    "contact_router",
    "health_router",
    "incidents_router",
    "license_router",
    "settings_router",
    "webhooks_router",
]
