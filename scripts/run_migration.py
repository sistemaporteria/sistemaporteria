"""Apply a SQL migration to the Supabase project.

DDL cannot run with a client key (publishable or anon): those are constrained by RLS and the
exposed schema. It needs either a Personal Access Token, used against the Management API, or
the database password, used over a direct Postgres connection.

Credentials are read from the environment or .env.local, never passed on the command line,
so they do not end up in the shell history.

Usage:
  # 1. Personal Access Token (sbp_...) in SUPABASE_ACCESS_TOKEN
  python scripts/run_migration.py services/api/migrations/0001_initial_schema.sql

  # 2. dry run: print what would be sent
  python scripts/run_migration.py <file> --dry-run

  # 3. inspect the current schema instead of migrating
  python scripts/run_migration.py --list-tables
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env.local"
MANAGEMENT_API = "https://api.supabase.com/v1"

LIST_TABLES_SQL = """
select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;
"""


def load_env() -> dict[str, str]:
  """Read .env.local without adding a dependency on python-dotenv."""
  values: dict[str, str] = {}
  if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
      line = line.strip()
      if not line or line.startswith("#") or "=" not in line:
        continue
      key, _, value = line.partition("=")
      values[key.strip()] = value.strip()
  values.update({k: v for k, v in os.environ.items() if k.startswith("SUPABASE_")})
  return values


def run_query(project_ref: str, token: str, sql: str) -> tuple[int, str]:
  request = urllib.request.Request(
    f"{MANAGEMENT_API}/projects/{project_ref}/database/query",
    data=json.dumps({"query": sql}).encode("utf-8"),
    headers={
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
      # The Management API sits behind Cloudflare, which rejects urllib's default
      # User-Agent with a 403 "error code: 1010".
      "User-Agent": "porteria-migrator/1.0",
      "Accept": "application/json",
    },
    method="POST",
  )
  try:
    with urllib.request.urlopen(request, timeout=120) as response:
      return response.status, response.read().decode("utf-8")
  except urllib.error.HTTPError as error:
    return error.code, error.read().decode("utf-8")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("migration", type=Path, nargs="?")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--list-tables", action="store_true")
  args = parser.parse_args()

  env = load_env()
  project_ref = env.get("SUPABASE_PROJECT_REF")
  token = env.get("SUPABASE_ACCESS_TOKEN")

  if not project_ref:
    print("falta SUPABASE_PROJECT_REF en .env.local", file=sys.stderr)
    return 1

  if args.list_tables:
    sql = LIST_TABLES_SQL
  elif args.migration:
    if not args.migration.exists():
      print(f"no existe: {args.migration}", file=sys.stderr)
      return 1
    # utf-8-sig strips a BOM if present: Windows editors and PowerShell's Set-Content write
    # one by default, and Postgres rejects it as a syntax error on the first statement.
    sql = args.migration.read_text(encoding="utf-8-sig")
  else:
    parser.print_help()
    return 1

  if args.dry_run:
    print(f"proyecto : {project_ref}")
    print(f"token    : {'presente' if token else 'AUSENTE'}")
    print(f"sentencias: ~{sql.count(';')}")
    return 0

  if not token:
    print(
      "falta SUPABASE_ACCESS_TOKEN.\n"
      "Crear uno en https://supabase.com/dashboard/account/tokens y anadirlo a .env.local\n"
      "como SUPABASE_ACCESS_TOKEN=sbp_...  (se puede revocar apenas termine la migracion)",
      file=sys.stderr,
    )
    return 1

  status, body = run_query(project_ref, token, sql)
  print(f"HTTP {status}")
  try:
    print(json.dumps(json.loads(body), indent=2, ensure_ascii=False)[:4000])
  except json.JSONDecodeError:
    print(body[:4000])
  return 0 if status < 300 else 1


if __name__ == "__main__":
  raise SystemExit(main())
