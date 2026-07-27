"""Ingest API: the only writer of access_events.

Scope is deliberately narrow. The web panel talks to Supabase directly, using the publishable
key with Auth and RLS, so this service exposes no read endpoints. It exists for one reason:
writing events requires the secret key, which must never leave a server.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from plate_rules import normalize

from .config import Settings
from .schemas import AccessEventIn, AccessEventOut, HealthOut
from .supabase import SupabaseClient, SupabaseError

logger = logging.getLogger("porteria_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
  settings: Settings = app.state.settings
  # An injected client (tests) is never replaced. Building it here rather than in create_app
  # keeps the network connection out of import time.
  if not app.state.supabase_injected and settings.is_configured():
    app.state.supabase = SupabaseClient(
      settings.rest_url, settings.supabase_secret_key, settings.request_timeout
    )
  elif not settings.is_configured():
    logger.warning("Supabase sin configurar: la API arranca en modo degradado")
  yield
  if app.state.supabase and not app.state.supabase_injected:
    app.state.supabase.close()


def create_app(settings: Settings | None = None, supabase: Any = None) -> FastAPI:
  """Build the app. Both dependencies are injectable so tests need no network.

  State is populated here and not only in the lifespan, because a TestClient used without its
  context manager never runs the lifespan, and the routes would find no client.
  """
  app = FastAPI(title="Porteria — API de ingesta", version="0.1.0", lifespan=lifespan)
  app.state.settings = settings or Settings.from_env()
  app.state.supabase = supabase
  app.state.supabase_injected = supabase is not None
  _register_routes(app)
  return app


def _require_token(
  request: Request, authorization: Annotated[str | None, Header()] = None
) -> None:
  """Shared-secret auth for the edge agent.

  Not a user credential: one machine, one token. Users authenticate against Supabase Auth
  from the browser instead, and never reach this service.
  """
  expected = request.app.state.settings.ingest_token
  if not expected:
    raise HTTPException(
      status.HTTP_503_SERVICE_UNAVAILABLE, "API_INGEST_TOKEN no configurado en el servidor"
    )
  if authorization != f"Bearer {expected}":
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token de ingesta invalido")


def _register_routes(app: FastAPI) -> None:
  @app.get("/health", response_model=HealthOut)
  def health() -> HealthOut:
    settings: Settings = app.state.settings
    client = app.state.supabase
    if not settings.is_configured() or client is None:
      return HealthOut(
        status="degraded", database=False, configured=False, detail="Supabase sin configurar"
      )
    reachable = client.ping()
    return HealthOut(
      status="ok" if reachable else "degraded",
      database=reachable,
      configured=True,
      detail=None if reachable else "Supabase no responde",
    )

  @app.post(
    "/events",
    response_model=AccessEventOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_token)],
  )
  def ingest(event: AccessEventIn, request: Request, response: Response) -> AccessEventOut:
    client = request.app.state.supabase
    if client is None:
      raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase sin configurar")

    plate = _revalidate_plate(event)
    vehicle = None
    if plate:
      try:
        vehicle = client.find_vehicle_by_plate(plate)
      except SupabaseError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    payload = _to_row(event, plate, vehicle)

    try:
      outcome = client.insert_access_event(payload)
    except SupabaseError as error:
      # 502 rather than 500: the agent must keep the event queued and retry.
      raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    if not outcome.created:
      # 200, not 201 and not an error: the passage is accounted for and the agent must stop
      # retrying. A 4xx/5xx here would make the outbox retry a conflict forever.
      response.status_code = status.HTTP_200_OK
      return AccessEventOut(
        status=outcome.reason or "duplicate",
        plate_read=plate,
        detail="el paso ya estaba registrado",
      )

    row = outcome.row or {}
    return AccessEventOut(
      status="created",
      event_id=row.get("id"),
      plate_read=plate,
      vehicle_id=vehicle["id"] if vehicle else None,
      vehicle_known=vehicle is not None,
      needs_review=bool(payload["review_status"] == "pending"),
    )


def _revalidate_plate(event: AccessEventIn) -> str | None:
  """Re-run the domain rules server-side instead of trusting the edge.

  The agent already normalized, but the server is the one that owns what enters the database.
  A plate the domain rejects is stored as a raw read only, so nothing invented ever becomes a
  vehicle record.
  """
  if not event.plate_read:
    return None
  result = normalize(event.plate_read)
  return result.text if result.is_valid else None


def _to_row(event: AccessEventIn, plate: str | None, vehicle: dict[str, Any] | None) -> dict:
  needs_review = event.needs_review or plate is None or vehicle is None
  return {
    "occurred_at": event.occurred_at.isoformat(),
    "camera_id": event.camera_id,
    "direction": event.direction,
    "raw_read": event.raw_read or event.plate_read,
    "plate_read": plate,
    "vehicle_id": vehicle["id"] if vehicle else None,
    "ocr_confidence": event.ocr_confidence,
    "verdict": event.verdict,
    "detected_class": event.detected_class,
    "plate_class": event.plate_class,
    "frames_agreed": event.frames_agreed,
    "frames_total": event.frames_total,
    "frigate_event_id": event.frigate_event_id,
    "track_id": event.track_id,
    "image_url": event.image_url,
    # An unknown plate is not an error: it is the queue that feeds vehicle registration.
    "review_status": "pending" if needs_review else "auto",
  }


app = create_app()
