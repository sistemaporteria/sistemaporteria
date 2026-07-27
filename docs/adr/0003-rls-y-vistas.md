# ADR 0003 — RLS como única barrera, y el caso especial de las vistas

- **Fecha:** 2026-07-26
- **Estado:** aceptada

## Contexto

El repositorio es **público** y la clave `publishable` de Supabase también lo es por diseño:
viaja dentro del bundle JavaScript que se descarga cualquier visitante del panel web. No hay
forma de ocultarla.

La base contiene nombres, documentos de identidad, placas y horarios de entrada y salida de
personas — datos personales bajo la Ley 1581 de 2012.

Por lo tanto: **lo único que separa esos datos de internet es Row Level Security.** No es una
capa de defensa en profundidad, es *la* barrera.

## El incidente

Al verificar el esquema recién aplicado, las cinco tablas mostraban `relrowsecurity = true`
con sus políticas. Pero la vista `parking_sessions` aparecía con `false` y cero políticas.

En PostgreSQL una vista se evalúa por defecto con los privilegios de **su dueño**, no de quien
la consulta. Como la creó un rol privilegiado, leerla saltaba el RLS de `access_events` por
completo. Verificado alternando el ajuste sobre datos de prueba:

```
security_invoker = off  ->  HTTP 200 [{"plate":"ABC123",...},{"plate":"XYZ789",...}]
security_invoker = on   ->  HTTP 200 []
```

Es decir: las tablas estaban protegidas y la vista publicaba lo mismo sin restricción alguna.

## Decisión

1. **RLS activo en toda tabla del esquema `public`**, sin excepción, activado *antes* de
   crear cualquier política.
2. **Toda vista sobre una tabla con RLS declara `security_invoker = on`.** Sin esto la vista
   es la puerta trasera de la tabla.
3. **Los clientes nunca escriben eventos.** La creación de `access_events` es exclusiva de
   `services/api`, que guarda la clave de servicio del lado del servidor. Los guardias solo
   pueden *actualizar* la cola de revisión.
4. **La clave de servicio nunca sale del servidor** ni se pega en un chat ni se commitea.
5. **La verificación es empírica, no documental.** No basta leer `pg_class`: hay que intentar
   leer y escribir con la clave pública y comprobar que devuelve vacío o rechaza.

## Consecuencias

- Cada tabla o vista nueva obliga a repetir la verificación. `verify_schema.sql` la
  automatiza parcialmente, pero **no detecta el caso de la vista** — hay que probar con la
  clave pública.
- Conviene revisar también el *linter* de seguridad del panel de Supabase, que marca este
  mismo problema como `security_definer_view`.
- Pendiente al crecer el esquema: las políticas actuales dan lectura completa a cualquier
  usuario autenticado (`using (true)`). Para un guardia eso es más de lo necesario; cuando
  haya datos reales conviene restringir su acceso al histórico.
