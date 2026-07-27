"""Create a panel user: an auth account plus its profile row.

Two steps are needed and both require the secret key. Supabase Auth owns `auth.users`, but
the role that RLS checks lives in `public.profiles`, so a user without a profile can log in
and then see nothing — which is the correct failure mode, but a confusing one to debug.

Usage:
  python scripts/seed_user.py guardia@unal.edu.co --role guard --name "Ana Gomez"
  python scripts/seed_user.py --list
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "plate_rules" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "api" / "src"))

import httpx

from porteria_api.config import Settings


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("email", nargs="?")
  parser.add_argument("--role", choices=["guard", "admin"], default="guard")
  parser.add_argument("--name", default=None)
  parser.add_argument("--password", default=None, help="si se omite, se genera una")
  parser.add_argument("--list", action="store_true")
  args = parser.parse_args()

  settings = Settings.from_env()
  if not settings.is_configured():
    print("falta SUPABASE_URL o SUPABASE_SECRET_KEY en .env.local", file=sys.stderr)
    return 1

  base = settings.supabase_url.rstrip("/")
  headers = {
    "apikey": settings.supabase_secret_key,
    "Authorization": f"Bearer {settings.supabase_secret_key}",
    "Content-Type": "application/json",
    "User-Agent": "porteria-seed/1.0",
  }

  with httpx.Client(headers=headers, timeout=30) as client:
    if args.list:
      profiles = client.get(
        f"{base}/rest/v1/profiles", params={"select": "id,full_name,role,active"}
      ).json()
      for profile in profiles:
        print(f"  {profile['role']:6} {profile['full_name']:24} activo={profile['active']}")
      print(f"  total: {len(profiles)}")
      return 0

    if not args.email:
      parser.print_help()
      return 1

    password = args.password or secrets.token_urlsafe(12)
    created = client.post(
      f"{base}/auth/v1/admin/users",
      json={"email": args.email, "password": password, "email_confirm": True},
    )
    if created.status_code >= 300:
      print(f"fallo creando usuario: {created.status_code} {created.text[:300]}", file=sys.stderr)
      return 1
    user_id = created.json()["id"]

    profile = client.post(
      f"{base}/rest/v1/profiles",
      headers={"Prefer": "return=representation"},
      json={
        "id": user_id,
        "full_name": args.name or args.email.split("@")[0],
        "role": args.role,
      },
    )
    if profile.status_code >= 300:
      print(f"fallo creando perfil: {profile.status_code} {profile.text[:300]}", file=sys.stderr)
      return 1

    print(f"usuario creado: {args.email}  rol={args.role}")
    if not args.password:
      print(f"contrasena generada: {password}")
      print("  (guardala ahora; no se vuelve a mostrar)")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
