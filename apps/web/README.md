# apps/web

Panel para guardias y administración. Next.js 16, React 19, TypeScript, Tailwind.

## Por qué no pasa por `services/api`

Habla **directo con Supabase** usando la publishable key, Auth y RLS. La API de ingesta existe
solo porque escribir eventos necesita la *secret key*; leer y editar desde el navegador no la
necesita, porque RLS ya decide qué puede ver y hacer cada usuario.

Un endpoint intermedio que replicara esas reglas sería una segunda implementación de la misma
política de acceso, y dos implementaciones divergen.

```
navegador ──publishable key + JWT del usuario──→ Supabase (RLS decide)
```

## Pantallas

| Ruta | Para qué |
|---|---|
| `/login` | Autenticación contra Supabase Auth |
| `/` | Tablero: entradas y salidas de hoy, vehículos adentro, últimos pasos |
| `/revision` | **La pantalla principal del guardia.** Cola de lecturas sin resolver |
| `/historial` | Eventos filtrables y sesiones de parqueo |
| `/vehiculos` | Registro de vehículos y dueños |

## Puesta en marcha

```powershell
cd apps\web
npm install
# .env.local con NEXT_PUBLIC_SUPABASE_URL y NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
npm run dev
```

Usuarios de prueba (creados con `scripts/seed_user.py`):

| Correo | Rol |
|---|---|
| `guardia@unal.edu.co` | guard |
| `admin@unal.edu.co` | admin |

## Decisiones

**La cola de revisión es la pantalla que justifica el proyecto.** Ahí llega todo lo que el
sistema no pudo resolver solo: placas desconocidas, conflictos entre el patrón de la placa y
lo que vio la cámara, y pasos ilegibles. Cada corrección del guardia es además el insumo del
reentrenamiento del modelo, así que la pantalla no es solo operación, es recolección de datos.

**Los conflictos se explican en palabras, no en códigos.** Cuando el veredicto es `conflict`,
la tarjeta dice *"la placa sugiere una moto pero la cámara vio un carro"* y añade que eso casi
siempre significa un error de OCR. Un guardia no debería tener que aprender el vocabulario
interno del sistema para hacer su trabajo.

**Todas las horas se muestran en `America/Bogota`,** nunca en la zona del navegador. Un
reporte que cambia de horas según el equipo desde el que se consulta es inservible.

**El `proxy.ts` que protege las rutas es comodidad, no seguridad.** Quien lo saltara llegaría
a una página que consulta la base como usuario anónimo y no recibe nada. La barrera real es
RLS, verificada de forma empírica: con solo la publishable key, `cameras` devuelve 0 filas;
autenticado como guardia, devuelve las 2 que existen.

**`getUser()` y no `getSession()`** en el proxy: revalida el token contra Supabase en vez de
confiar en lo que afirme la cookie.

## Qué ve cada rol

Definido por RLS en la migración `0003`, no por la interfaz. Ocultar un botón que la base
rechazaría de todos modos es cortesía, no seguridad: cuando las dos discrepan, manda la base.

| | guard | admin |
|---|---|---|
| Cola de revisión | ✅ | ✅ |
| Eventos de las últimas 24 h | ✅ | ✅ |
| Histórico completo | ❌ | ✅ |
| Datos personales de dueños | ❌ (solo puede crearlos) | ✅ |
| Vehículos por placa | ✅ | ✅ |
| Exportar CSV | ❌ | ✅ |

Un guardia necesita resolver lecturas dudosas, saber quién está adentro y consultar un
vehículo puntual. Nada de eso exige ver los movimientos de una persona hace seis meses — y ese
histórico es justamente donde una fuga haría más daño, porque permite reconstruir la rutina
diaria de alguien identificable.

## Realtime

El tablero y la cola de revisión se actualizan solos cuando cambia `access_events`, con un
indicador de estado de la conexión. Se hace recargando los componentes de servidor y no
parcheando estado local: la vista muestra agregados y una vista de la base, y recalcularlos en
el navegador sería una segunda implementación de lógica que Postgres ya posee. Con unos pocos
eventos por minuto, el costo de recargar es irrelevante.

Realtime respeta RLS, así que un guardia solo recibe notificaciones de filas que sus políticas
le permitirían leer.

## Pendiente

- Fotografía del recorte de placa en la cola de revisión: el agente todavía no sube imágenes.
- Filtro por rango de fechas en el histórico.
