import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.processor import process_alert_into_incident
from backend.app.auth.security import require_webhook_auth
from backend.app.core.database import get_db
from backend.app.models.alert import Alert, AlertSource
from backend.app.schemas.alert import WebhookAckResponse

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/{source}", response_model=WebhookAckResponse, status_code=202)
async def ingest_webhook(
    source: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _authorized: bool = Depends(require_webhook_auth),
) -> WebhookAckResponse:
    """
    High-throughput webhook ingestion gateway (500 alerts/sec capacity).
    Accepts PagerDuty, Datadog, Sentry, CloudWatch, Prometheus alerts.
    Responds in <30ms with 202 Accepted and queues autonomous LangGraph incident remediation.
    """
    payload = await request.json()

    # Map source string to AlertSource enum safely
    source_upper = source.upper()
    try:
        alert_source = AlertSource[source_upper]
    except KeyError:
        alert_source = AlertSource.GENERIC

    # Generate deterministic fingerprint: source + payload title/message/alertname
    title = payload.get("title", "")
    message = payload.get("message", "")
    alertname = payload.get("alertname", "")
    if not (title or message or alertname):
        alertname = str(payload)

    fingerprint_str = f"{alert_source.value}-{title}-{message}-{alertname}"
    fingerprint = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()

    alert = Alert(
        source=alert_source,
        source_alert_id=str(payload.get("id") or payload.get("alert_id") or ""),
        title=title or message or alertname or None,
        raw_payload=payload,
        fingerprint=fingerprint,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    # Trigger background autonomous incident pipeline
    background_tasks.add_task(
        process_alert_into_incident,
        alert_id=alert.id,
        source=alert_source.value,
        raw_payload=payload
    )

    return WebhookAckResponse(
        status="accepted",
        alert_id=alert.id,
        message=f"Alert ingested successfully from {alert_source.value}. Autonomous triage pipeline engaged."
    )
