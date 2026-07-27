# CLAUDE.md — Control de acceso vehicular por reconocimiento de placas

> Archivo de contexto permanente. Cualquier chat nuevo debe leer esto primero.
> Es un **índice + reglas + estado actual**; la teoría profunda vive en `docs/`.
> Mantenerlo corto: si una explicación pasa de ~15 líneas, va a `docs/` y aquí queda el enlace.

---

## 1. Qué es este proyecto

Sistema ALPR (Automatic License Plate Recognition) para la **portería vehicular de la
Universidad Nacional de Colombia — Sede Manizales**. Dos carriles físicos separados por un
bordillo: uno de entrada y uno de salida.

**Problema que resuelve:** hoy el registro es 100% manual — el guardia pasa una libreta al
conductor para que anote sus datos en cada ingreso. Volumen real: **1000–2000 vehículos/día,
lunes a sábado** en temporada alta.

**Qué debe hacer el sistema:**

1. Detectar el vehículo y leer su placa automáticamente en cada carril.
2. Determinar si es **entrada** o **salida** (por carril/cámara).
3. Buscar la placa en la base de datos. Si existe → registra el evento con su dueño.
   Si no existe → queda en cola para que el guardia registre dueño y vehículo.
4. Guardar fecha/hora de entrada y de salida, y emparejarlas en sesiones de parqueo.
5. Ofrecer un panel web para guardias (operación) y para administración (reportes).

**Naturaleza:** trabajo académico + herramienta operativa real. Se privilegia usar
componentes preentrenados y probados sobre entrenar modelos desde cero. El aporte técnico
propio está en la **capa de dominio** (reglas de placas colombianas, tipo de vehículo,
verificación cruzada, agregación temporal, ROI adaptativa), no en la arquitectura de redes.

**Estado actual: DEMO en el equipo del desarrollador.** No hay cámaras instaladas todavía.
Se trabaja con videos e imágenes de prueba. La demo debe **cubrir y soportar todas las fases**
del plan de producción, aunque no se despliegue en sitio aún.

---

## 2. Arquitectura — Ruta B (edge + nube)

Decisión tomada. Ver el porqué en [docs/adr/0001-ruta-b-edge-nube.md](docs/adr/0001-ruta-b-edge-nube.md).

```
┌──────────── EDGE (hoy: el PC del dev; mañana: mini PC en la portería) ─────────────┐
│                                                                                     │
│  Fuente de video ──→ [ Frigate ] ──MQTT──→ [ edge_agent ] ──HTTPS──┐                │
│  (video de prueba     • detección de         • normaliza placa      │                │
│   en loop, luego       objetos (car/moto)    • infiere tipo         │                │
│   RTSP real)         • LPR: YOLOv9 +        • verificación cruzada │                │
│                        PaddleOCR             • dirección in/out     │                │
│                      • grabación/snapshots   • deduplicación        │                │
│                      • MQTT out              • outbox SQLite        │                │
│                                                (sobrevive sin red)  │                │
└─────────────────────────────────────────────────────────────────────┼───────────────┘
                                                                      │ solo JSON + JPG (~30 KB)
                                        ┌─────────────────────────────▼──────────────┐
                                        │  services/api  (FastAPI)                   │
                                        └─────────────────────────────┬──────────────┘
                                                                      │
                                        ┌─────────────────────────────▼──────────────┐
                                        │  Supabase: Postgres + Auth + Storage + RT   │
                                        └─────────────────────────────┬──────────────┘
                                                                      │
                                        ┌─────────────────────────────▼──────────────┐
                                        │  apps/web  (Next.js) — guardias + admin     │
                                        └─────────────────────────────────────────────┘
```

**Regla de oro:** el **video nunca sale del borde**. Solo viajan eventos JSON y un recorte
JPG. Razones: ancho de banda (2 cámaras 1080p ≈ 1 TB/mes), latencia, costo y habeas data
(Ley 1581 de 2012 — placa + dueño = dato personal).

---

## 3. Stack y por qué cada pieza

| Capa | Herramienta | Rol | Teoría |
|---|---|---|---|
| Visión / NVR | **Frigate 0.16+** | Ingesta RTSP, detección de movimiento, detección de objetos, LPR integrado, grabación, eventos MQTT | [docs/01-teoria-modelos.md](docs/01-teoria-modelos.md) |
| Detector de placa | **YOLOv9** (interno de Frigate) | Localiza el rectángulo de la placa | idem |
| OCR de placa | **PaddleOCR** (interno de Frigate) | Convierte el recorte en texto | idem |
| Bus de eventos | **Mosquitto (MQTT)** | Desacopla Frigate del agente | idem |
| Dominio | **`packages/plate_rules`** (propio) | Normalización, tipo de vehículo, verificación cruzada | [docs/02-placas-colombia.md](docs/02-placas-colombia.md) |
| Agente edge | **`services/edge_agent`** (Python) | MQTT → dominio → outbox → nube | — |
| API | **FastAPI** | Ingesta de eventos + REST para el web | — |
| BD / BaaS | **Supabase** (Postgres, Auth, Storage, Realtime, RLS) | Persistencia y servicios | — |
| Web | **Next.js 15 + TypeScript + Tailwind + shadcn/ui** | Panel de guardias y admin | — |
| Contenedores | **Docker Compose** | Todo el edge reproducible | — |

**Por qué Frigate y no un pipeline propio:** decisión explícita del usuario — no quiere
entrar al detalle interno de los modelos ni al tuning de costo de cómputo. Frigate resuelve
~60% de la ingeniería de video (reconexión RTSP, buffers, timestamps, retención, snapshots)
y es software probado en producción. El trabajo propio se concentra en la capa de dominio.
Ver [docs/adr/0002-frigate-vs-pipeline-propio.md](docs/adr/0002-frigate-vs-pipeline-propio.md).

---

## 4. Decisiones de diseño ya tomadas (no re-litigar)

1. **Ruta B**, edge + nube. El video no sale del borde.
2. **Frigate** como capa de visión, no pipeline propio.
3. **La dirección (entrada/salida) se deduce de la cámara**, no del tracking. Cada carril
   tiene su cámara y cada cámara tiene una dirección fija configurada. Es la solución más
   robusta y aprovecha que los carriles ya están físicamente separados.
4. **El texto de la placa NO basta para determinar el tipo de vehículo.** `AAA123` es
   idéntico para particular y para público; solo el **color de fondo** los separa. Por eso
   la clasificación combina tres señales: patrón + color + etiqueta del detector.
5. **Arquitectura hexagonal en el dominio**: `plate_rules` es Python puro, sin dependencias
   ni I/O, 100% testeable. La visión por computador (color, geometría) vive en `edge_agent`
   y le pasa valores ya calculados. Nunca meter OpenCV/numpy dentro de `plate_rules`.
6. **Offline-first**: el agente escribe primero en un outbox SQLite local y luego sincroniza.
   Si se cae internet, no se pierde ningún ingreso.
7. **Siempre se guarda el evento crudo**, aunque la placa no esté registrada o sea ilegible.
   Esa cola es el insumo del registro de vehículos nuevos y del active learning.
8. **Toda vista sobre una tabla con RLS debe declarar `security_invoker = on`.** Por defecto
   una vista de PostgreSQL se evalúa con los privilegios de su dueño y **puentea el RLS de
   las tablas subyacentes**: se convierte en la puerta trasera de la tabla. Costó una fuga
   real, verificada, en `parking_sessions` — ver
   [ADR 0003](docs/adr/0003-rls-y-vistas.md).
9. **Las migraciones son de solo-añadir.** Una vez aplicada, una migración no se edita: se
   corrige con otra nueva. Así el historial de git reproduce el estado real de la base.

---

## 5. Reglas de trabajo para el asistente

### Documentación (obligatorio)
- **Cada implementación o cambio se documenta**, en dos lugares:
  1. Una nueva sección al final de [docs/CHANGELOG-IMPLEMENTACION.md](docs/CHANGELOG-IMPLEMENTACION.md)
     con qué se hizo, por qué y cómo probarlo.
  2. Si introduce una herramienta, modelo o concepto nuevo → **la teoría detrás** va al
     documento correspondiente en `docs/`. Este proyecto es académico: el "por qué funciona"
     importa tanto como el "que funcione".
- Las decisiones arquitectónicas con alternativas descartadas van como **ADR** numerado en
  `docs/adr/`. Formato: contexto → opciones → decisión → consecuencias.
- Actualizar la sección **§7 Estado actual** de este archivo cuando cambie.

### Código
- Código, nombres y comentarios **en inglés**. Documentación y textos de UI **en español**.
- Sin comentarios salvo que la lógica no sea obvia.
- Indentación de 2 espacios (Python, JS, CSS, YAML).
- CSS en `rem`; excepciones: bordes (1px), sombras y ajustes finos.
- Python: type hints obligatorios, `ruff` para lint y formato, `pytest` para tests.
- **Toda regla de dominio nueva necesita un test**. `plate_rules` no se toca sin test.
- Nada de números mágicos: los umbrales van a `config.py` / `.env` con su justificación.

### Honestidad técnica
- Los parámetros que dependen de la óptica real (relación de aspecto de la placa, umbrales
  de color HSV, área mínima en píxeles) están marcados **`# CALIBRAR`** en el código.
  No inventar valores y presentarlos como definitivos: se calibran con datos reales.
- Si una métrica no se ha medido, decirlo. No estimar precisión sin haberla evaluado.

### Git
- Commit después de cada cambio de código (repo local, sin remoto por ahora).
- Mensajes en inglés, imperativo: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.

---

## 6. Mapa del repositorio

```
vehiculos_porteria/
├── CLAUDE.md                     ← este archivo
├── README.md                     ← cómo levantar todo
├── docs/
│   ├── 00-arquitectura.md        Ruta B en detalle, flujo de datos, volumetría
│   ├── 01-teoria-modelos.md      Cómo funciona un ALPR: YOLO, OCR, tracking, MQTT
│   ├── 02-placas-colombia.md     Formatos, colores, tipo de vehículo, verificación cruzada
│   ├── 03-datasets.md            Todos los datasets, para qué sirve cada uno, cómo bajarlos
│   ├── 04-plan-fases.md          Las 6 fases y cómo la demo las cubre
│   ├── CHANGELOG-IMPLEMENTACION.md  ← bitácora de todo lo construido
│   └── adr/                      Decisiones arquitectónicas
├── infra/edge/                   Docker Compose: Frigate + Mosquitto (+ video de prueba)
├── packages/plate_rules/         Dominio puro: placas colombianas (sin dependencias)
├── services/edge_agent/          MQTT → dominio → outbox → nube
├── services/api/                 FastAPI (pendiente)
├── apps/web/                     Next.js (pendiente)
├── datasets/                     Datos de prueba (contenido ignorado por git)
└── scripts/                      Utilidades de calibración y evaluación
```

---

## 7. Estado actual

Actualizado: 2026-07-25

| Componente | Estado |
|---|---|
| Estructura del repo, git, docs base | ✅ hecho |
| `packages/plate_rules` (dominio de placas) | ✅ 70 tests |
| `packages/plate_synth` (placas sintéticas) | ✅ 21 tests |
| `scripts/eval_ocr.py` + medición del OCR | ✅ **medido**, ver [docs/05-evaluacion.md](docs/05-evaluacion.md) |
| `scripts/probe_video_alpr.py` (pipeline sobre video) | ✅ verificado sobre video real |
| Video de prueba: vehículos + **placas legibles** | ✅ descargado |
| `infra/edge` (Frigate + Mosquitto + RTSP sim) | ✅ escrito, ⚠️ sin verificar en ejecución |
| Esquema de BD en Supabase | ✅ **aplicado y verificado** (migraciones 0001 + 0002) |
| `services/edge_agent` | ✅ 60 tests, verificado con sesión grabada |
| `services/api` | ✅ 23 tests, circuito verificado contra la base real |
| `apps/web` | ✅ 5 rutas, RLS verificado desde el navegador |
| Detector de placas (modelo 2) — métrica IoU | ⬜ pendiente |
| Calibración con datos reales | ⬜ bloqueado: requiere video de la portería |

**Supabase** (proyecto `mhqyonldsvlyxebdmjse`). Esquema aplicado y verificado: RLS activo en
las cinco tablas, lectura y escritura anónimas bloqueadas, deduplicado y vista comprobados.

- La clave de cliente es la **publishable** (`sb_publishable_...`); las *legacy JWT keys* del
  proyecto están deshabilitadas y devuelven 401.
- La raíz `/rest/v1/` devuelve 401 **incluso con clave válida**: para comprobar conectividad
  hay que consultar una tabla, que responde `PGRST205` si no existe.
- Las migraciones se aplican con `scripts/run_migration.py`, que necesita un Personal Access
  Token en `SUPABASE_ACCESS_TOKEN`. **Es de alcance de cuenta: crear uno, usarlo y revocarlo.**
- La Management API está tras Cloudflare y rechaza el `User-Agent` por defecto de `urllib`
  con `403 error code: 1010`; el script manda uno explícito.

**Bloqueo activo:** sin video real de la portería, todo lo marcado `CALIBRAR` sigue sin medir.

**Siguiente paso:** calibración con video real de la portería (bloqueado), Realtime en el tablero, y exportación CSV para administración.

---

## 8. Entorno de desarrollo

- Windows 11, PowerShell. Docker 29.5.3, Python 3.12.10, git 2.53.
- Remoto: `https://github.com/sistemaporteria/sistemaporteria.git` (**público**), cuenta
  `Juanma0247` autenticada por `gh`.
- Un solo venv en la raíz (`.venv`) para scripts y evaluación; `packages/plate_rules/.venv`
  existe para correr el dominio aislado y comprobar que no arrastra dependencias.
- No hay cámaras: se alimenta Frigate con archivos de video servidos por RTSP en loop.
  Ver `infra/edge/README.md`.

### Seguridad — el repo es PÚBLICO

- Claves reales solo en `.env.local` (ignorado). `.env.example` va con valores vacíos.
- La **anon key es pública por diseño** (viaja en el bundle del navegador). Lo que protege
  los datos es **RLS**, no el secreto de la clave. Por eso el esquema activa RLS en todas las
  tablas y **nunca debe desactivarse**: la base contiene datos personales bajo la Ley 1581.
- La **service_role / secret key nunca sale del servidor** ni se pega en un chat. Salta RLS.
- Los datasets no se redistribuyen: RodoSol y UFPR tienen licencias que lo prohíben.
