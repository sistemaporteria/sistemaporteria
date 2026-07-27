"""Edge agent: Frigate over MQTT -> domain rules -> local outbox -> ingest API."""

from .config import Config
from .models import AccessEvent, Direction, PlateReading, TrackedObject
from .outbox import Outbox
from .pipeline import Pipeline
from .transport import HttpSink, LoggingSink, Synchronizer

__all__ = [
  "AccessEvent",
  "Config",
  "Direction",
  "HttpSink",
  "LoggingSink",
  "Outbox",
  "Pipeline",
  "PlateReading",
  "Synchronizer",
  "TrackedObject",
]

__version__ = "0.1.0"
