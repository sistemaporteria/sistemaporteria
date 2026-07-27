"""Verify the role policies empirically, using the two seeded accounts.

Reading pg_policies proves the policies exist; it does not prove they do what was intended.
This signs in as each role and compares what they actually receive.

Usage:
  python scripts/verify_rls.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "plate_rules" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "api" / "src"))

from porteria_api.config import Settings

ACCOUNTS = {
  "guard": ("guardia@unal.edu.co", "PorteriaDemo2026!"),
  "admin": ("admin@unal.edu.co", "PorteriaDemo2026!"),
}
PASS, FAIL = "OK  ", "FALLA"


def main() -> int:
  settings = Settings.from_env()
  if not settings.is_configured():
    print("falta configuracion en .env.local", file=sys.stderr)
    return 1

  base = settings.supabase_url.rstrip("/")
  publishable = _read_env("SUPABASE_PUBLISHABLE_KEY")
  if not publishable:
    print("falta SUPABASE_PUBLISHABLE_KEY en .env.local", file=sys.stderr)
    return 1

  def call(path: str, token: str, method: str = "GET", body: dict | None = None):
    request = urllib.request.Request(
      f"{base}{path}",
      data=json.dumps(body).encode() if body else None,
      headers={
        "apikey": publishable,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "porteria-verify/1.0",
      },
      method=method,
    )
    try:
      with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
      return error.code, error.read().decode()

  def sign_in(email: str, password: str) -> str | None:
    status, body = call(
      "/auth/v1/token?grant_type=password",
      publishable,
      "POST",
      {"email": email, "password": password},
    )
    return json.loads(body)["access_token"] if status == 200 else None

  tokens = {}
  for role, (email, password) in ACCOUNTS.items():
    token = sign_in(email, password)
    if not token:
      print(f"{FAIL} no se pudo entrar como {role} ({email})", file=sys.stderr)
      return 1
    tokens[role] = token

  def count(role: str, table: str, query: str = "select=*") -> int | str:
    status, body = call(f"/rest/v1/{table}?{query}", tokens[role])
    if status != 200:
      return f"HTTP {status}"
    return len(json.loads(body))

  failures = 0

  def check(label: str, actual, expected, explain: str = "") -> None:
    nonlocal failures
    ok = expected(actual) if callable(expected) else actual == expected
    if not ok:
      failures += 1
    suffix = f"  ({explain})" if explain else ""
    print(f"  {PASS if ok else FAIL} {label}: {actual}{suffix}")

  # Montaje: sin datos que discriminen, todas las comprobaciones pasarian por razones
  # triviales. Se crean las condiciones que la politica debe distinguir y se deshacen al
  # final.
  print("=== montaje ===")
  call(
    "/rest/v1/owners",
    tokens["admin"],
    "POST",
    {"full_name": "VERIFY dueno", "kind": "visitor", "document_id": "VERIFY-OWNER"},
  )
  status, body = call(
    "/rest/v1/access_events?select=id,occurred_at&order=occurred_at.asc&limit=1",
    tokens["admin"],
  )
  rows = json.loads(body) if status == 200 else []
  target_id = rows[0]["id"] if rows else None
  if target_id:
    call(
      f"/rest/v1/access_events?id=eq.{target_id}",
      tokens["admin"],
      "PATCH",
      {"review_status": "confirmed"},
    )
    print(f"  un evento antiguo marcado como resuelto: {target_id[:8]}")
  print("  un dueño creado")

  print("\n=== conteos por rol ===")
  admin_events = count("admin", "access_events")
  guard_events = count("guard", "access_events")
  print(f"  admin ve {admin_events} eventos, guard ve {guard_events}")
  check(
    "guard ve MENOS eventos que admin",
    guard_events,
    lambda n: isinstance(admin_events, int) and isinstance(n, int) and n < admin_events,
    f"admin={admin_events}",
  )

  print("\n=== dueños: datos personales solo para admin ===")
  check("admin lista owners", count("admin", "owners"), lambda n: n >= 1)
  check("guard NO lista owners", count("guard", "owners"), 0, "RLS devuelve vacio")

  print("\n=== histórico antiguo y ya resuelto ===")
  check(
    "admin ve el resuelto",
    count("admin", "access_events", "select=id&review_status=neq.pending"),
    lambda n: n >= 1,
  )
  check(
    "guard NO ve el resuelto de mas de 24 h",
    count("guard", "access_events", "select=id&review_status=neq.pending"),
    0,
  )

  print("\n=== cola de revisión: ambos la ven ===")
  check(
    "guard ve pendientes",
    count("guard", "access_events", "select=id&review_status=eq.pending"),
    lambda n: n >= 1,
  )

  print("\n=== guardia puede crear dueños (su tarea en la cola) ===")
  status, _ = call(
    "/rest/v1/owners",
    tokens["guard"],
    "POST",
    {"full_name": "VERIFY RLS", "kind": "visitor", "document_id": "VERIFY-RLS"},
  )
  check("guard inserta owner", status, 201)

  print("\n=== limpieza ===")
  call("/rest/v1/owners?document_id=like.VERIFY*", tokens["admin"], "DELETE")
  if target_id:
    call(
      f"/rest/v1/access_events?id=eq.{target_id}",
      tokens["admin"],
      "PATCH",
      {"review_status": "pending"},
    )
  print("  montaje deshecho")

  print(f"\n{'todo correcto' if failures == 0 else f'{failures} comprobaciones fallaron'}")
  return 1 if failures else 0


def _read_env(key: str) -> str:
  env_file = REPO_ROOT / ".env.local"
  if not env_file.exists():
    return ""
  for line in env_file.read_text(encoding="utf-8-sig").splitlines():
    if line.strip().startswith(f"{key}="):
      return line.split("=", 1)[1].strip()
  return ""


if __name__ == "__main__":
  raise SystemExit(main())
