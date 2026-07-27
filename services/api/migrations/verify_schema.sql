-- Verificación del esquema aplicado. Solo lee: no modifica nada.
-- Uso: python scripts/run_migration.py services/api/migrations/verify_schema.sql

select
  c.relname                                            as objeto,
  case c.relkind when 'r' then 'tabla' when 'v' then 'vista' end as tipo,
  c.relrowsecurity                                     as rls_activo,
  (select count(*) from pg_policies p
    where p.schemaname = 'public' and p.tablename = c.relname) as politicas,
  (select count(*) from pg_index i where i.indrelid = c.oid)    as indices
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'v')
order by c.relkind desc, c.relname;
