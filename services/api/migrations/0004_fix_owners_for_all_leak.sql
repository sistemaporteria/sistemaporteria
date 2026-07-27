-- Cierra la fuga que dejó la migración 0003 sobre `owners`.
--
-- La 0003 eliminó `owners_read` creyendo que con eso los datos personales quedaban solo para
-- administración. No funcionó: la política `owners_write` de la 0001 está declarada
-- `for all`, y en PostgreSQL **`FOR ALL` incluye `SELECT`**. Mientras exista una política
-- `for all` permisiva, quitar la de lectura no cambia nada.
--
-- Detectado por scripts/verify_rls.py, que entra como cada rol y compara lo que recibe. La
-- política existía y se veía correcta en pg_policies; solo la prueba empírica lo destapó.
--
-- Lección: en RLS, `for all` no es un atajo cómodo, es una política de lectura escondida.
-- A partir de aquí las políticas se declaran por operación.

drop policy if exists owners_write on owners;

create policy owners_update_admin on owners
  for update to authenticated
  using (current_role_is('admin'))
  with check (current_role_is('admin'));

create policy owners_delete_admin on owners
  for delete to authenticated
  using (current_role_is('admin'));

-- `owners_read_admin` y `owners_insert_guard` vienen de la 0003 y se conservan: el guardia
-- puede crear dueños —es su tarea en la cola de revisión— pero no listarlos.

-- ---------------------------------------------------------------------------
-- Buscar un dueño existente sin poder leer la tabla
-- ---------------------------------------------------------------------------
-- Al registrar un vehículo, el panel busca si el documento ya está registrado para reutilizar
-- la persona en vez de duplicarla. Sin lectura sobre `owners`, un guardia crearía un dueño
-- nuevo cada vez y la base terminaría con la misma persona repetida.
--
-- La solución no es devolverle la lectura, sino darle exactamente el dato que necesita: un
-- identificador, nunca el nombre ni el teléfono. SECURITY DEFINER ejecuta la función con los
-- privilegios de su dueño, así que puede consultar la tabla aunque quien la llama no pueda.

create or replace function find_owner_id_by_document(document text)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select id from owners where document_id = document and active limit 1;
$$;

revoke all on function find_owner_id_by_document(text) from public;
grant execute on function find_owner_id_by_document(text) to authenticated;

-- ---------------------------------------------------------------------------
-- Misma revisión sobre las demás tablas
-- ---------------------------------------------------------------------------
-- `vehicles_write` y `cameras_admin_write` también son `for all`, pero ahí la lectura amplia
-- es intencional: el guardia consulta vehículos por placa constantemente, y las cámaras no
-- contienen datos personales. Se dejan como están, ahora de forma consciente y no por
-- descuido.
