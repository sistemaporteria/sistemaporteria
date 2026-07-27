-- Portería vehicular UNAL Manizales — esquema inicial
-- Ejecutar en el SQL Editor de Supabase (una anon key no puede ejecutar DDL).
--
-- Principios de diseño (ver docs/00-arquitectura.md):
--   1. El evento crudo SIEMPRE se guarda, aunque la placa no esté registrada o sea ilegible.
--   2. Las sesiones de parqueo son una VISTA, no una tabla: una corrección de placa recalcula
--      todo automáticamente en vez de dejar filas huérfanas.
--   3. Se guarda la URL de la imagen, no el blob, para poder cambiar de backend de
--      almacenamiento sin migrar datos.
--   4. RLS activo en TODAS las tablas. Ver la nota de seguridad al final.

create extension if not exists "pgcrypto";
-- Necesaria para la restricción de exclusión del deduplicado: permite combinar operadores
-- de igualdad (btree) con solapamiento de rangos (gist) en un mismo índice.
create extension if not exists "btree_gist";

-- ---------------------------------------------------------------------------
-- Perfiles y roles
-- ---------------------------------------------------------------------------

create type app_role as enum ('guard', 'admin');

create table profiles (
  id          uuid primary key references auth.users on delete cascade,
  full_name   text not null,
  role        app_role not null default 'guard',
  active      boolean not null default true,
  created_at  timestamptz not null default now()
);

create or replace function current_role_is(target app_role)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from profiles
    where id = auth.uid() and role = target and active
  );
$$;

-- ---------------------------------------------------------------------------
-- Dueños y vehículos
-- ---------------------------------------------------------------------------

create type owner_kind as enum ('student', 'professor', 'staff', 'contractor', 'visitor');

create table owners (
  id           uuid primary key default gen_random_uuid(),
  full_name    text not null,
  document_id  text unique,
  kind         owner_kind not null default 'visitor',
  phone        text,
  email        text,
  active       boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- El cast a regconfig es obligatorio: to_tsvector(text, text) es STABLE porque la
-- configuración podría resolverse distinto según la sesión, y Postgres rechaza expresiones
-- no IMMUTABLE en un índice. to_tsvector(regconfig, text) sí es IMMUTABLE.
create index owners_full_name_idx
  on owners using gin (to_tsvector('spanish'::regconfig, full_name));

-- Espejo de plate_rules.PlateCategory / VehicleClass. La fuente de verdad es el paquete
-- Python; aquí se guarda lo que el dominio decidió, no se reimplementa la lógica.
create type vehicle_class as enum ('car', 'motorcycle', 'trailer', 'unknown');

create table vehicles (
  id             uuid primary key default gen_random_uuid(),
  plate          text not null unique check (plate ~ '^[A-Z0-9]{5,9}$'),
  class          vehicle_class not null default 'unknown',
  category       text,
  service_type   text,
  brand          text,
  model          text,
  color          text,
  owner_id       uuid references owners on delete set null,
  active         boolean not null default true,
  notes          text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index vehicles_owner_idx on vehicles (owner_id);

-- ---------------------------------------------------------------------------
-- Cámaras
-- ---------------------------------------------------------------------------

create type gate_direction as enum ('in', 'out');

create table cameras (
  id            text primary key,             -- coincide con el nombre en Frigate
  label         text not null,
  direction     gate_direction not null,
  roi_polygon   jsonb,
  active        boolean not null default true,
  last_seen_at  timestamptz,
  created_at    timestamptz not null default now()
);

insert into cameras (id, label, direction) values
  ('porteria_entrada', 'Portería — carril de entrada', 'in'),
  ('porteria_salida',  'Portería — carril de salida',  'out');

-- ---------------------------------------------------------------------------
-- Eventos de acceso
-- ---------------------------------------------------------------------------

create type review_status as enum ('auto', 'pending', 'confirmed', 'corrected', 'discarded');

-- Espejo de plate_rules.CrossCheckVerdict.
create type cross_check_verdict as enum (
  'confirmed', 'conflict', 'unverified', 'unrecognized_pattern'
);

create table access_events (
  id                  uuid primary key default gen_random_uuid(),
  occurred_at         timestamptz not null,
  camera_id           text not null references cameras,
  direction           gate_direction not null,

  -- Lo que se leyó, crudo y normalizado. Ambos se conservan para auditoría.
  raw_read            text,
  plate_read          text,
  corrected_plate     text,
  vehicle_id          uuid references vehicles on delete set null,

  -- Salida de plate_rules
  ocr_confidence      real check (ocr_confidence between 0 and 1),
  verdict             cross_check_verdict not null default 'unverified',
  detected_class      vehicle_class,
  plate_class         vehicle_class,
  frames_agreed       integer,
  frames_total        integer,

  -- Trazabilidad y evidencia
  frigate_event_id    text,
  track_id            text,
  image_url           text,
  image_expires_at    timestamptz,

  review_status       review_status not null default 'auto',
  reviewed_by         uuid references profiles on delete set null,
  reviewed_at         timestamptz,
  created_at          timestamptz not null default now()
);

-- La placa efectiva: la corrección humana gana sobre la lectura automática.
create or replace function effective_plate(e access_events)
returns text
language sql
immutable
as $$
  select coalesce(e.corrected_plate, e.plate_read);
$$;

create index access_events_occurred_idx on access_events (occurred_at desc);
create index access_events_plate_idx on access_events (plate_read, occurred_at desc);
create index access_events_vehicle_idx on access_events (vehicle_id, occurred_at desc);
create index access_events_review_idx on access_events (review_status)
  where review_status = 'pending';

-- Deduplicación: un vehículo que retrocede o se detiene ante la talanquera genera varios
-- tracks, y cada track produce un evento. Se rechaza la misma placa en la misma cámara
-- dentro de una ventana de 90 s.
--
-- Se usa una restricción de EXCLUSIÓN y no un índice único sobre date_trunc por dos razones:
--   1. date_trunc(text, timestamptz) es STABLE, no IMMUTABLE (depende del TimeZone de la
--      sesión), así que Postgres no la admite en un índice.
--   2. Aun si se pudiera, agrupar por minuto es incorrecto: dos lecturas separadas por 2
--      segundos que caen a ambos lados de un cambio de minuto quedarían en cubetas distintas
--      y ambas pasarían. La exclusión por solapamiento de rangos mide la distancia real.
--
-- El `at time zone 'UTC'` tampoco es cosmético: `timestamptz ± interval` es STABLE, porque el
-- resultado depende de las reglas de horario de verano vigentes. Convertir primero a
-- `timestamp` plano —conversión que sí es IMMUTABLE con una zona literal— hace que la
-- aritmética posterior sea inmutable y la expresión sea indexable.
alter table access_events add constraint access_events_dedup
  exclude using gist (
    camera_id with =,
    plate_read with =,
    tsrange(
      (occurred_at at time zone 'UTC') - interval '45 seconds',
      (occurred_at at time zone 'UTC') + interval '45 seconds'
    ) with &&
  )
  where (plate_read is not null);

-- El agente del borde reenvía tras un corte de red; el id de Frigate hace la ingesta
-- idempotente.
create unique index access_events_frigate_idx on access_events (frigate_event_id)
  where frigate_event_id is not null;

-- ---------------------------------------------------------------------------
-- Sesiones de parqueo — vista, no tabla
-- ---------------------------------------------------------------------------

create or replace view parking_sessions as
with ordered as (
  select
    id,
    coalesce(corrected_plate, plate_read) as plate,
    vehicle_id,
    direction,
    occurred_at,
    lead(occurred_at) over w as next_at,
    lead(direction)   over w as next_direction,
    lead(id)          over w as next_id
  from access_events
  where coalesce(corrected_plate, plate_read) is not null
    and review_status <> 'discarded'
  window w as (
    partition by coalesce(corrected_plate, plate_read)
    order by occurred_at
  )
)
select
  id                          as entry_event_id,
  next_id                     as exit_event_id,
  plate,
  vehicle_id,
  occurred_at                 as entered_at,
  case when next_direction = 'out' then next_at end as exited_at,
  case when next_direction = 'out' then next_at - occurred_at end as duration,
  next_direction is distinct from 'out' as is_open
from ordered
where direction = 'in';

-- ---------------------------------------------------------------------------
-- updated_at automático
-- ---------------------------------------------------------------------------

create or replace function touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger owners_touch before update on owners
  for each row execute function touch_updated_at();
create trigger vehicles_touch before update on vehicles
  for each row execute function touch_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- OBLIGATORIO. La anon key es pública por diseño (viaja en el bundle del navegador) y este
-- repositorio es público. Sin RLS, cualquiera con esa clave podría leer y escribir la base
-- de datos completa — que contiene datos personales bajo la Ley 1581 de 2012.
--
-- El agente del borde NO usa la anon key: escribe contra services/api, que guarda la clave
-- de servicio del lado del servidor.

alter table profiles       enable row level security;
alter table owners         enable row level security;
alter table vehicles       enable row level security;
alter table cameras        enable row level security;
alter table access_events  enable row level security;

-- Todo usuario autenticado ve su propio perfil; los administradores ven todos.
create policy profiles_self_read on profiles
  for select to authenticated
  using (id = auth.uid() or current_role_is('admin'));

create policy profiles_admin_write on profiles
  for all to authenticated
  using (current_role_is('admin')) with check (current_role_is('admin'));

-- Guardias y administradores operan sobre dueños, vehículos y eventos.
create policy owners_read on owners
  for select to authenticated using (true);
create policy owners_write on owners
  for all to authenticated
  using (current_role_is('guard') or current_role_is('admin'))
  with check (current_role_is('guard') or current_role_is('admin'));

create policy vehicles_read on vehicles
  for select to authenticated using (true);
create policy vehicles_write on vehicles
  for all to authenticated
  using (current_role_is('guard') or current_role_is('admin'))
  with check (current_role_is('guard') or current_role_is('admin'));

create policy cameras_read on cameras
  for select to authenticated using (true);
create policy cameras_admin_write on cameras
  for all to authenticated
  using (current_role_is('admin')) with check (current_role_is('admin'));

create policy events_read on access_events
  for select to authenticated using (true);
-- Los guardias solo pueden resolver la cola de revisión, no inventar eventos: la creación de
-- eventos es exclusiva del agente del borde vía services/api (clave de servicio, sin RLS).
create policy events_review on access_events
  for update to authenticated
  using (current_role_is('guard') or current_role_is('admin'))
  with check (current_role_is('guard') or current_role_is('admin'));
create policy events_admin_delete on access_events
  for delete to authenticated using (current_role_is('admin'));

-- ---------------------------------------------------------------------------
-- Retención de imágenes (docs/00-arquitectura.md §5)
-- ---------------------------------------------------------------------------
-- ~3,1 GB/mes de recortes no caben en ningún free tier de forma sostenida. Las filas se
-- conservan indefinidamente; las imágenes caducan. Programar con pg_cron o desde la API.

create or replace function expire_images(retention interval default '30 days')
returns integer
language sql
security definer
set search_path = public
as $$
  with expired as (
    update access_events
    set image_url = null, image_expires_at = null
    where image_url is not null
      and occurred_at < now() - retention
      and review_status <> 'pending'
    returning 1
  )
  select count(*)::integer from expired;
$$;
