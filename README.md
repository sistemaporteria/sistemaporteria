# Control de acceso vehicular por reconocimiento de placas

Sistema ALPR para la portería vehicular de la **Universidad Nacional de Colombia — Sede
Manizales**. Detecta el vehículo, lee la placa, determina si entra o sale, y registra el
evento con su dueño. Reemplaza el registro manual en libreta que se usa hoy.

**Estado: demo en desarrollo.** Sin cámaras instaladas; se trabaja con video de prueba.

---

## Documentación

| Documento | Contenido |
|---|---|
| [CLAUDE.md](CLAUDE.md) | **Empezar aquí.** Contexto completo, decisiones cerradas, estado actual |
| [docs/00-arquitectura.md](docs/00-arquitectura.md) | Ruta B, flujo de datos, volumetría, hosting, aspectos legales |
| [docs/01-teoria-modelos.md](docs/01-teoria-modelos.md) | Cómo funciona un ALPR: YOLO, OCR, CTC, tracking, ONNX, MQTT |
| [docs/02-placas-colombia.md](docs/02-placas-colombia.md) | Formatos, colores, tipo de vehículo, verificación cruzada |
| [docs/03-datasets.md](docs/03-datasets.md) | Datasets de vehículos, de placas y de OCR: cuál sirve para qué |
| [docs/CHANGELOG-IMPLEMENTACION.md](docs/CHANGELOG-IMPLEMENTACION.md) | Bitácora de todo lo construido |
| [docs/adr/](docs/adr/) | Decisiones arquitectónicas con sus alternativas descartadas |

---

## Arquitectura en una línea

```
cámaras → Frigate (detección + LPR) → MQTT → edge_agent (dominio) → API → Supabase → web
└──────────── en la portería, el video nunca sale ─────────────┘ └──── en la nube ────┘
```

---

## Estructura

```
packages/plate_rules/    Dominio: placas colombianas. Python puro, sin dependencias.
services/edge_agent/     MQTT → dominio → outbox SQLite → nube.          (pendiente)
services/api/            FastAPI: ingesta y REST.                        (pendiente)
apps/web/                Next.js: panel de guardias y admin.             (pendiente)
infra/edge/              Docker Compose: Frigate + Mosquitto + RTSP sim.
datasets/                Datos de prueba (contenido ignorado por git).
scripts/                 Calibración y evaluación.
```

---

## Puesta en marcha

### Dominio de placas

```powershell
$p = "packages\plate_rules"
python -m venv "$p\.venv"
& "$p\.venv\Scripts\python.exe" -m pip install pytest ruff
& "$p\.venv\Scripts\python.exe" -m pytest $p -q
```

### Stack del borde

Requiere Docker Desktop (WSL2), ≥4 GB RAM libres, CPU con AVX/AVX2, y dos videos en
`infra/edge/media/`. Ver [infra/edge/README.md](infra/edge/README.md).

```powershell
docker compose -f infra/edge/docker-compose.yml up -d
```

---

## Licencia y datos

Los datasets de `datasets/` **no se redistribuyen**: varios (RodoSol-ALPR, UFPR-ALPR) tienen
licencias académicas que lo prohíben expresamente. Solo se versionan los scripts que los
descargan y transforman.

El sistema procesa datos personales (placa + dueño) bajo la Ley 1581 de 2012. Ver las
consideraciones legales en [docs/00-arquitectura.md §7](docs/00-arquitectura.md).
