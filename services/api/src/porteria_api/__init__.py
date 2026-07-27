"""Ingest API: the only writer of access_events."""

from .config import Settings, generate_ingest_token
from .main import create_app
from .schemas import AccessEventIn, AccessEventOut
from .supabase import InsertOutcome, SupabaseClient, SupabaseError

__all__ = [
  "AccessEventIn",
  "AccessEventOut",
  "InsertOutcome",
  "Settings",
  "SupabaseClient",
  "SupabaseError",
  "create_app",
  "generate_ingest_token",
]

__version__ = "0.1.0"
