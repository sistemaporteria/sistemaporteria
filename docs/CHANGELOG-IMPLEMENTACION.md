# Bitácora de implementación

Una sección por cambio: **qué se hizo**, **por qué**, **cómo se prueba**. Lo más reciente al
final. La teoría profunda no va aquí — va al documento de `docs/` que corresponda, y aquí
queda el enlace.

---

## 2026-07-25 — Estructura del proyecto y documentación base

**Qué se hizo**

- Repositorio inicializado en `main`, con `.gitignore` (excluye datasets, video, modelos,
  secretos y estado de runtime) y `.editorconfig` (2 espacios, UTF-8, LF).
- Estructura monorepo: `packages/` (dominio), `services/` (procesos), `apps/` (frontend),
  `infra/` (despliegue), `docs/`, `datasets/`, `scripts/`.
- `CLAUDE.md` como contexto permanente: qué es el proyecto, arquitectura, stack, decisiones
  cerradas, reglas de trabajo y estado actual.
- Documentación base en `docs/`: arquitectura, teoría de modelos, placas colombianas,
  datasets, y dos ADR.

**Por qué**

Separar dominio de infraestructura desde el primer día. `plate_rules` no debe saber que
existe Frigate, ni MQTT, ni Postgres — así se puede probar en 0,3 s sin levantar nada, y se
puede reutilizar en el backend para revalidar del lado del servidor.

`CLAUDE.md` se mantiene como índice y no como enciclopedia: se carga en cada contexto, así
que la profundidad vive en `docs/` y allí solo quedan los enlaces.

**Cómo se prueba**

```powershell
git -C . log --oneline
```

---

## 2026-07-25 — `packages/plate_rules`: dominio de placas colombianas

**Qué se hizo**

Paquete Python puro, cero dependencias, cuatro módulos:

| Módulo | Responsabilidad |
|---|---|
| `types.py` | Vocabulario del dominio: `VehicleClass`, `ServiceType`, `PlateColor`, `PlateCategory`, `CrossCheckVerdict` + dataclasses de resultado |
| `patterns.py` | Catálogo de 8 patrones de placa colombiana con sus máscaras `L`/`N`, y los mapas categoría → clase / servicio / color |
| `normalize.py` | Limpieza de OCR + coerción posicional guiada por máscara, con límite de correcciones |
| `classify.py` | Combina patrón + color + etiqueta del detector; emite veredicto de verificación cruzada |
| `aggregate.py` | Votación ponderada por confianza sobre todas las lecturas de un track |

**Por qué**

Tres decisiones de diseño que vale la pena registrar:

1. **El texto de la placa no determina el tipo de vehículo.** Seis categorías comparten la
   máscara `LLLNNN` (particular, público, oficial, antiguo, diplomático, consular). Solo el
   **color de fondo** las separa. Por eso `categories_for()` devuelve un *conjunto* de
   candidatos y no una respuesta, y `narrow_by_color()` lo reduce después.
   Además los prefijos `O`/`D`/`C` **no son exclusivos**: un particular corriente puede tener
   placa `DAB123`. Cualquier regla basada solo en el prefijo produce falsos positivos.

2. **La verificación cruzada es un detector de errores de OCR gratuito.** Si el patrón dice
   "moto" y la cámara ve un carro, casi siempre significa que el OCR falló. Caso real y
   frecuente: la moto `ABC12D` leída como `ABC120` (`D`→`0`). Sin este chequeo, entraría en
   silencio a la base de datos como un vehículo que no existe. Con él, va a la cola de
   revisión. Está cubierto por el test `test_ocr_error_surfaces_as_a_conflict`.

3. **`MAX_CORRECTIONS = 2`.** El corrector de OCR podría "arreglar" cualquier cadena hasta
   convertirla en una placa válida. Inventar una placa plausible pero falsa es mucho peor que
   no leer nada, porque es un error silencioso. Con más de dos coerciones el resultado se
   marca inválido y va a revisión. Cada corrección además descuenta confianza.

Un cuarto punto, de arquitectura: **numpy y OpenCV no entran a este paquete**. La estimación
de color vive en `edge_agent` y le pasa un `PlateColor` ya calculado. El dominio se mantiene
puro y testeable sin dependencias.

Teoría completa en [02-placas-colombia.md](02-placas-colombia.md).

**Cómo se prueba**

```powershell
$p = "packages\plate_rules"
python -m venv "$p\.venv"
& "$p\.venv\Scripts\python.exe" -m pip install pytest ruff
& "$p\.venv\Scripts\python.exe" -m pytest $p -q
& "$p\.venv\Scripts\ruff.exe" check $p
```

**Resultado: 62 tests pasando, ruff sin hallazgos.** Cobertura por área: 24 de normalización
(incluye los casos de confusión `O/0`, `I/1`, `Z/2`, `B/8`), 25 de clasificación y
verificación cruzada, 13 de agregación temporal.

**Pendiente / calibrar**

- La señal geométrica (relación de aspecto de la placa) está descrita en la documentación
  pero **no implementada**: depende de la óptica real y no hay datos para fijar umbrales.
- Placas antiguas, diplomáticas y consulares se clasifican como `PUBLIC_CAR` porque la franja
  azul vertical no se detecta. Simplificación consciente y documentada.

---

## 2026-07-25 — `infra/edge`: Frigate + Mosquitto + simulador RTSP

**Qué se hizo**

`docker-compose.yml` con tres servicios:

- **mosquitto** (1883) — broker MQTT, bus de eventos entre Frigate y el agente.
- **rtsp-sim** (8554) — MediaMTX + ffmpeg reproduciendo `media/entrada.mp4` y
  `media/salida.mp4` en loop (`-re -stream_loop -1`) como si fueran cámaras RTSP reales.
- **frigate** (8971 UI, 5000 API) — detección de objetos, LPR, grabación, eventos MQTT.

`frigate/config.yml` con dos cámaras (`porteria_entrada`, `porteria_salida`), LPR activado,
detección restringida a `car`/`motorcycle`/`bus`/`truck`, y zonas de carril placeholder.

**Por qué**

- **El simulador RTSP no es un atajo, es parte del diseño.** Permite que la demo use
  exactamente el mismo camino de datos que producción: RTSP → Frigate → MQTT. Cuando lleguen
  las cámaras, se borra un servicio y se cambian dos URLs. Nada más. Si en cambio se
  alimentara Frigate con archivos directamente, el paso a producción cambiaría el camino de
  ingesta y habría que revalidarlo todo.
- **Modo normal, no `type: "lpr"`.** El modo dedicado es más rápido pero salta la detección de
  objetos general, y con ella se perdería la etiqueta `car`/`motorcycle` de la que depende la
  verificación cruzada. Ver [ADR 0002](adr/0002-frigate-vs-pipeline-propio.md).
- **`known_plates` no se usa.** El registro de vehículos vive en Postgres; duplicarlo en un
  YAML garantizaría inconsistencia.
- **`recognition_threshold` permisivo (0.60).** Frigate filtra poco a propósito: quien tiene
  las reglas de dominio para juzgar una lectura es `plate_rules`, aguas abajo. Filtrar
  temprano descartaría lecturas que la coerción por máscara habría recuperado.

**Cómo se prueba**

Requiere dos videos en `infra/edge/media/`. Ver [infra/edge/README.md](../infra/edge/README.md).

```powershell
docker compose -f infra/edge/docker-compose.yml up -d
docker exec -it porteria-mosquitto mosquitto_sub -t 'frigate/#' -v
```

**Estado: escrito, no verificado en ejecución** — faltan los videos de prueba. Los parámetros
marcados `CALIBRAR` (`min_area`, zonas, `fps`, umbral de movimiento) son puntos de partida
razonados, no mediciones.
