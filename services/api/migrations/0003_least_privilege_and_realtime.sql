-- Dos cambios: acotar lo que ve un guardia, y habilitar Realtime en los eventos.
--
-- Ejecutar en el SQL Editor de Supabase.

-- ---------------------------------------------------------------------------
-- 1. Mínimo privilegio para el rol `guard`
-- ---------------------------------------------------------------------------
-- Las políticas de la migración 0001 daban `using (true)`: cualquier usuario autenticado
-- podía leer el histórico completo de entradas y salidas de todo el mundo. Para operar la
-- portería eso es mucho más de lo necesario.
--
-- Un guardia necesita exactamente tres cosas:
--   a) la cola de revisión, para resolver lecturas dudosas,
--   b) lo que pasó durante su turno, para saber quién está adentro,
--   c) consultar un vehículo puntual por placa, para atender a quien llega.
--
-- Nada de eso requiere ver los movimientos de un vehículo hace seis meses. Ese histórico es
-- material administrativo, y en el que más daño haría una fuga: permite reconstruir la
-- rutina diaria de una persona identificable.

drop policy if exists events_read on access_events;

create policy events_read_admin on access_events
  for select to authenticated
  using (current_role_is('admin'));

create policy events_read_guard on access_events
  for select to authenticated
  using (
    current_role_is('guard')
    and (
      -- la cola de trabajo
      review_status = 'pending'
      -- o la ventana operativa del turno
      or occurred_at > now() - interval '24 hours'
    )
  );

-- Los datos personales de los dueños quedan solo para administración. Un guardia ve la
-- placa y si el vehículo está registrado, que es lo que necesita para dejarlo pasar; el
-- documento y el teléfono del dueño no le hacen falta.
drop policy if exists owners_read on owners;

create policy owners_read_admin on owners
  for select to authenticated
  using (current_role_is('admin'));

-- El guardia sí necesita registrar dueños nuevos: es su tarea principal en la cola de
-- revisión. Puede crearlos, y leer el que acaba de crear, pero no listarlos todos.
create policy owners_insert_guard on owners
  for insert to authenticated
  with check (current_role_is('guard') or current_role_is('admin'));

-- Los vehículos no llevan datos personales por sí mismos, y el guardia necesita buscarlos
-- por placa constantemente. Se mantiene la lectura completa.

-- ---------------------------------------------------------------------------
-- 2. Realtime
-- ---------------------------------------------------------------------------
-- Permite que el tablero se actualice cuando entra un vehículo, sin recargar la página.
-- Realtime respeta RLS: cada suscriptor recibe solo las filas que sus políticas le
-- permitirían leer, así que un guardia no recibe eventos que no podría consultar.

alter publication supabase_realtime add table access_events;

-- REPLICA IDENTITY FULL hace que los UPDATE incluyan la fila anterior completa. Sin esto,
-- al resolver un evento en la cola de revisión el panel recibiría un payload incompleto y
-- no podría decidir si la fila sigue perteneciendo a la vista actual.
alter table access_events replica identity full;
