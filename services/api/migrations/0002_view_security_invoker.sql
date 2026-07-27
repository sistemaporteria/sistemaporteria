-- Cierra un puente de RLS en la vista `parking_sessions`.
--
-- El problema: una vista de PostgreSQL se ejecuta por defecto con los privilegios de su
-- DUEÑO, no de quien consulta. Como la vista la creó un rol privilegiado, leerla saltaba por
-- completo el RLS de `access_events`: cualquiera con la clave publishable podía obtener el
-- histórico entero de entradas y salidas —placas, horas, vehículos— simplemente consultando
-- la vista en lugar de la tabla.
--
-- Detectado al verificar el esquema recién aplicado: las cinco tablas tenían `relrowsecurity
-- = true`, pero la vista aparecía con `false` y cero políticas.
--
-- `security_invoker` (PostgreSQL 15+) hace que la vista se evalúe con los permisos y las
-- políticas RLS de quien la consulta, que es lo que se esperaba desde el principio.
--
-- Regla general para este proyecto: TODA vista sobre una tabla con RLS debe declarar
-- security_invoker, o la vista se convierte en la puerta trasera de la tabla.

alter view parking_sessions set (security_invoker = on);
