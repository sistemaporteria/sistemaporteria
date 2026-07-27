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

---

## 2026-07-25 — Datos de prueba para los tres modelos, y medición real del OCR

**Qué se hizo**

1. `datasets/scripts/download_video_assets.py` — descarga `vehicles.mp4` (4K, 22 s) y
   `vehicles-2.mp4` (1080p, 43 s) del catálogo de supervision.
2. `packages/plate_synth` — generador de placas colombianas sintéticas:
   - `render.py`: dibuja placas válidas del catálogo (particular amarilla, público blanca,
     oficial verde, moto amarilla) con colores y formatos correctos.
   - `degrade.py`: ocho degradaciones controladas — ancho, motion blur, desenfoque, yaw,
     pitch, iluminación, ruido, compresión JPEG.
   - `dataset.py`: escribe sets etiquetados con manifiesto JSON.
3. `scripts/eval_ocr.py` — harness de evaluación con barridos y baseline.
4. `ruff.toml` en la raíz, para que los scripts fuera de paquetes también usen 2 espacios.

**Por qué: el hallazgo que forzó esta estrategia**

Se descargó el video público esperando probar el pipeline completo. **Ambos videos son tomas
desde un puente sobre autopista: las placas miden ~10 px.** Sirven para el detector de
vehículos y para nada más.

No es mala suerte, es la norma — el video de tráfico público se graba para *contar*
vehículos, no para *leer* placas. De ahí la separación en tres niveles: video real para el
modelo 1, sintético para el modelo 3, y composición pendiente para el modelo 2.

**Tres bugs encontrados y corregidos durante la construcción**

1. *La fuente se dimensionaba solo por altura* → el texto desbordaba el ancho de la placa.
   Corregido con `_fit_font`, que ajusta a ambas dimensiones.
2. *El warp de perspectiva trasladaba la placa en vez de escorzarla.* Una placa rotada no se
   mueve de sitio: su borde lejano se acorta. Reemplazado por un modelo pinhole con división
   perspectiva real. Importaba: de ese barrido sale la especificación angular de la cámara, y
   el modelo ingenuo la habría hecho falsamente estricta.
3. *La banda "COLOMBIA" era demasiado alta en el formato moto* (34% del alto) → el OCR leía
   dentro de ella y añadía caracteres fantasma (`DOF38U` → `DOF38UG`). Reducida al 20%. El
   baseline subió de ~85% a 97,5%.

**Resultados medidos** — `cct-xs-v2-global-model`, n=40, baseline 97,5%

| Factor | Efecto | Veredicto |
|---|---|---|
| Motion blur | k=13: **−45%**, k=17: **−95%** | 🔴 el único con acantilado real |
| Ancho de placa | 40 px: −32,5%; ≥60 px: plano | 🟡 acantilado bajo 60 px |
| Yaw / pitch | plano hasta 50° | 🟢 mucho más tolerante de lo asumido |
| Desenfoque, ruido, JPEG | sin efecto medible | 🟢 |

**Consecuencia directa: se corrigió la especificación de cámara.** Se había documentado
"≥100 px" y "<30°" por regla general. La medición dice **≥80 px** y **<50°**, y que el
obturador rápido importa más que todo lo demás junto. Ver [05-evaluacion.md](05-evaluacion.md)
y [02-placas-colombia.md §7](02-placas-colombia.md).

**Un resultado negativo que también se reporta:** la columna `+ dominio` salió idéntica al OCR
crudo. La coerción por máscara no aporta exactitud con este modelo, porque cuando falla
sustituye un carácter por otro del mismo tipo y la cadena sigue cumpliendo la máscara. El
valor de `plate_rules` es **precisión** (rechazar basura, detectar conflictos), no
**cobertura**. A motion blur k=17 rechazó 20/40 lecturas inválidas que de otro modo habrían
entrado a la base de datos.

**Cómo se prueba**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install supervision opencv-python-headless pillow numpy "fast-plate-ocr[onnx]" pytest ruff
.\.venv\Scripts\python.exe datasets\scripts\download_video_assets.py
.\.venv\Scripts\python.exe scripts\eval_ocr.py --samples 40
.\.venv\Scripts\python.exe -m pytest packages -q      # 83 tests
```

**Limitaciones declaradas:** placas sintéticas (más limpias que la realidad), artefacto
tipográfico con la letra `I`, y se midió `fast-plate-ocr` y no el PaddleOCR que usa Frigate.
Las cinco limitaciones completas están en [05-evaluacion.md §3](05-evaluacion.md).

---

## 2026-07-25 — Repositorio remoto y esquema de base de datos

**Qué se hizo**

- Remoto `https://github.com/sistemaporteria/sistemaporteria.git` conectado y `main` publicado.
- `services/api/migrations/0001_initial_schema.sql` — esquema completo: `profiles`, `owners`,
  `vehicles`, `cameras`, `access_events`, vista `parking_sessions`, RLS en todas las tablas y
  función de retención de imágenes.
- `.env.example` (versionado, sin valores) y `.env.local` (ignorado, con la anon key).

**Decisiones de diseño del esquema**

- **`parking_sessions` es una VISTA, no una tabla.** Empareja cada entrada con la siguiente
  salida de la misma placa usando `lead()`. Así, cuando un guardia corrige una placa mal
  leída, todas las sesiones se recalculan solas en vez de quedar filas huérfanas apuntando a
  un vehículo inexistente.
- **`corrected_plate` junto a `plate_read`.** Nunca se sobrescribe la lectura automática: se
  necesita para auditar el sistema y para alimentar el reentrenamiento.
- **Índice único de deduplicación** por `(cámara, placa, minuto)` y otro por
  `frigate_event_id`, que hace la ingesta idempotente cuando el agente reenvía tras un corte
  de red.
- **La imagen se guarda como URL, no como blob**, para poder migrar de Supabase Storage a
  Cloudflare R2 sin tocar datos (ver el problema de 3,1 GB/mes en
  [00-arquitectura.md §5](00-arquitectura.md)).

**Seguridad: por qué RLS no es opcional aquí**

El repositorio es **público** y la anon key es **pública por diseño** (viaja en el bundle del
navegador). Lo único que impide que cualquiera lea y escriba la base de datos es **RLS**. Y la
base contiene datos personales bajo la Ley 1581 de 2012. Por eso el esquema activa RLS en las
cinco tablas antes de crear cualquier política, y los guardias solo pueden *actualizar* la
cola de revisión — la creación de eventos es exclusiva de `services/api`, que usa la clave de
servicio del lado del servidor.

**Estado: bloqueado.** La anon key entregada devuelve **HTTP 401** contra
`/rest/v1/`. Lo más probable es que las *legacy JWT keys* estén deshabilitadas y el proyecto
use las nuevas `sb_publishable_...`. El esquema no se ha aplicado.

---

## 2026-07-25 — Video con placas legibles, y un falso positivo del dominio encontrado con él

**Qué se hizo**

1. `datasets/scripts/download_alpr_videos.py` — descarga tres videos de
   [BarthPaleologue/ALPR](https://github.com/BarthPaleologue/ALPR) (MIT) que **sí tienen
   placas legibles**: un plano cercano con la placa `29-UM-92` nítida, y dashcam en París bajo
   lluvia con varios vehículos y motos.
2. `scripts/probe_video_alpr.py` — corre el pipeline completo (detector YOLOv9 + OCR) sobre un
   video y reporta cobertura, **ancho de placa en píxeles** y las lecturas obtenidas. El ancho
   es el número que decide si un video sirve, porque el acantilado del OCR está en 60 px.
3. Corrección en `plate_rules`: patrones `strict`.

**Verificación sobre video real** (`alpr_video1.mp4`, 60 frames):

```
con placa     : 35 (58%)
ancho de placa: min 28 / mediana 82 / max 200 px
lecturas      : 29UM92, 5527MA, 22ZC39, 20OH47 ...
```

Detección y OCR **funcionan sobre material real**, no solo sintético. La mediana de 82 px
cae en el rango que la medición sintética había declarado suficiente.

**El bug que esto destapó**

Entre las lecturas portuguesas, dos fueron aceptadas como **placas colombianas válidas**:

```
0961RF  -> coercion 1->I  -> 096IRF  aceptada como motocarro
66TE67  -> coercion T->7, E->3 -> 667367  aceptada como placa de policía
```

Ambas inventadas. La causa: el riesgo de falso positivo de un patrón crece con **cuántas
cadenas pueden ser dobladas hacia él**. `NNNNNN` es el peor caso posible — casi toda letra
tiene un dígito parecido, así que cualquier lectura de seis caracteres colapsa en él.
`NNNLLL` sufre lo mismo en su tramo numérico.

**Corrección:** se añadió `strict: bool` a `PlatePattern`. Un patrón estricto se reconoce
solo si el texto **ya lo cumple exactamente**; nunca se dobla nada hacia él. Se marcaron así
`NNNNNN` (policía) y `NNNLLL` (motocarro). Resultado:

| Lectura | Antes | Ahora |
|---|---|---|
| `0961RF`, `66TE67`, `29UM92`, `5527MA`, `22ZC39` | 2 aceptadas ❌ | **todas rechazadas** ✅ |
| `123ABC`, `123456` (colombianas legítimas) | aceptadas | **siguen aceptadas** ✅ |
| `A8C1Z3` → `ABC123` (2 errores de OCR) | corregida | **sigue corrigiendo** ✅ |

Los barridos del OCR sintético dieron **idénticos** tras el cambio: la restricción solo afecta
a placas extranjeras. Cubierto por 8 tests de regresión nuevos.

**Por qué importa más de lo que parece:** en la portería no habrá placas portuguesas, pero sí
habrá lecturas corruptas por movimiento, suciedad y ángulo, que producen exactamente el mismo
efecto — cadenas basura dobladas hasta parecer placas válidas. Un vehículo fantasma en la base
de datos es peor que una lectura fallida, porque nadie lo detecta. Es el mismo principio detrás
de `MAX_CORRECTIONS`, aplicado ahora a nivel de patrón.

**Lección de método:** el bug era invisible con datos sintéticos, porque el generador solo
produce placas colombianas válidas. Apareció al primer contacto con datos reales de otra
distribución. Los datos sintéticos miden sensibilidad; **no encuentran errores de dominio**.

**Cómo se prueba**

```powershell
.\.venv\Scripts\python.exe datasets\scripts\download_alpr_videos.py
.\.venv\Scripts\python.exe scripts\probe_video_alpr.py datasets\raw\video\alpr_video1.mp4 --every 8
.\.venv\Scripts\python.exe -m pytest packages -q      # 91 tests
```

---

## 2026-07-26 — Migración aplicada a Supabase, y una fuga de RLS encontrada al verificarla

**Qué se hizo**

- `scripts/run_migration.py` — aplica migraciones vía Management API con un Personal Access
  Token. Las credenciales se leen de `.env.local`, nunca de `argv`, para que no queden en el
  historial del shell.
- Migración `0001` aplicada al proyecto `mhqyonldsvlyxebdmjse`.
- Migración `0002` — corrige una fuga de RLS descubierta al verificar.
- `verify_schema.sql` — consulta de solo lectura que reporta tablas, RLS, políticas e índices.

**Tres errores corregidos antes de que la migración pasara**

1. **`to_tsvector('spanish', full_name)` en un índice GIN.** La variante
   `to_tsvector(text, text)` es STABLE, no IMMUTABLE, porque la configuración podría
   resolverse distinto según la sesión. Corregido con el cast explícito
   `'spanish'::regconfig`, que sí es IMMUTABLE.

2. **`date_trunc('minute', occurred_at)` en el índice de deduplicación.** Mismo problema:
   `date_trunc(text, timestamptz)` depende del TimeZone de la sesión. Pero al replantearlo
   apareció un defecto de diseño peor: **agrupar por minuto es incorrecto**. Dos lecturas
   separadas por 2 segundos que caen a ambos lados de un cambio de minuto quedan en cubetas
   distintas y ambas pasan el filtro. Reemplazado por una **restricción de exclusión** con
   `btree_gist` que mide la distancia real entre eventos.

3. **`timestamptz ± interval` tampoco es IMMUTABLE**, porque el resultado depende de las
   reglas de horario de verano. Se resuelve convirtiendo primero a `timestamp` plano con
   `at time zone 'UTC'` —conversión inmutable con zona literal— y haciendo la aritmética
   sobre el resultado.

4. Fallo de robustez del runner: PowerShell escribe UTF-8 **con BOM**, y Postgres rechaza el
   BOM como error de sintaxis. El script ahora lee con `utf-8-sig`.

**La fuga de RLS**

`verify_schema.sql` mostró las cinco tablas con `relrowsecurity = true`... y la vista
`parking_sessions` con `false` y cero políticas.

En PostgreSQL una vista se evalúa por defecto con los privilegios de su **dueño**, no de quien
consulta. Como la creó un rol privilegiado, **leerla saltaba por completo el RLS de
`access_events`**. Comprobado empíricamente alternando el ajuste (la base solo tenía datos de
prueba):

```
security_invoker = off  -> lectura anonima: HTTP 200 [{"plate":"ABC123","entered_at":...},
                                                      {"plate":"XYZ789","entered_at":...}]
security_invoker = on   -> lectura anonima: HTTP 200 []
```

Con la clave publishable —que es pública por diseño y este repositorio es público— cualquiera
podía obtener el histórico completo de entradas y salidas consultando la vista en lugar de la
tabla. Corregido en `0002`.

**Regla que queda:** toda vista sobre una tabla con RLS debe declarar `security_invoker`, o la
vista se convierte en la puerta trasera de la tabla. Añadida a las reglas de trabajo.

**Verificación final ejecutada**

| Prueba | Resultado |
|---|---|
| RLS en las 5 tablas | ✅ activo, con políticas (3 en `access_events`, 2 en el resto) |
| Lectura anónima de las 5 tablas + la vista | ✅ `[]` con datos presentes en la base |
| Escritura anónima en `owners` | ✅ rechazada, `42501 new row violates row-level security policy` |
| Control de conectividad | ✅ `404 PGRST205` en tabla inexistente — el endpoint responde |
| Vista `parking_sessions` | ✅ `ABC123` 08:00→17:30 duración 9h30m; `XYZ789` sesión abierta |
| Deduplicado a +40 s | ✅ rechazado, `23P01 conflicting key value violates exclusion constraint` |
| Paso legítimo a +120 s | ✅ aceptado |
| Limpieza | ✅ 0 eventos, 0 vehículos, 0 dueños; quedan las 2 cámaras sembradas |

**Cómo se prueba**

```powershell
.\.venv\Scripts\python.exe scripts\run_migration.py --list-tables
.\.venv\Scripts\python.exe scripts\run_migration.py services\api\migrations\verify_schema.sql
```

---

## 2026-07-26 — `services/edge_agent`: de MQTT a eventos de acceso

**Qué se hizo**

| Módulo | Responsabilidad |
|---|---|
| `frigate.py` | Parsea `frigate/events` y `frigate/tracked_object_update` |
| `models.py` | `TrackedObject` (estado en vuelo) y `AccessEvent` (lo que se persiste) |
| `pipeline.py` | Acumula lecturas por objeto, agrega, clasifica, verifica y deduplica |
| `outbox.py` | Cola SQLite transaccional |
| `transport.py` | Interfaz `Sink` + implementación HTTP + sincronizador con reintentos |
| `main.py` | Bucle MQTT, modo `--replay` y `--status` |
| `config.py` | Umbrales con su justificación; mapa cámara → dirección |

**El formato MQTT se consultó, no se supuso.** Los campos vienen de la
[documentación de Frigate](https://docs.frigate.video/integrations/mqtt/): `frigate/events`
trae `type: new|update|end` con `before`/`after`, y dentro de `after` están
`recognized_license_plate`, `recognized_license_plate_score` y —clave para la verificación
cruzada— `label` con `car` o `motorcycle`. `frigate/tracked_object_update` con `type: "lpr"`
publica cada refinamiento individual de la placa.

**Decisiones**

- **Se emite en `end`, no en cada `update`.** Frigate refina la placa mientras el vehículo se
  mueve. Mientras tanto el agente acumula los mensajes `lpr` y al cerrar corre su propia
  votación ponderada. Frigate ya hace una agregación interna, pero no expone las lecturas
  individuales en el evento final; recolectarlas mantiene el control del criterio y protege
  de que Frigate cambie su estrategia.
- **Un vehículo sin lectura también genera evento**, marcado para revisión. Un paso ilegible
  es información: descartarlo escondería una cámara degradándose.
- **Deduplicación en dos capas**: ventana en memoria en el agente, restricción de exclusión
  en Postgres. El agente se reinicia y pierde su estado; la base no.
- **`frigate_event_id` viaja en cada evento.** MQTT entrega *al menos una vez*, así que el
  mismo evento puede llegar dos veces; ese id hace la ingesta idempotente en ambas capas.
- **Un mensaje mal formado nunca tumba el agente.** El parser devuelve `None` en vez de
  lanzar, y el handler MQTT atrapa todo: un broker puede entregar cualquier cosa, y no puede
  costar el resto del turno.

**Verificación de extremo a extremo**

`tests/fixtures/porteria_demo.jsonl` es una sesión grabada de 21 mensajes con seis pasos de
vehículo. Ejecutada con `--replay`:

```
porteria_entrada in  placa=KEM018 conf=1.00 veredicto=confirmed            revision=False
porteria_entrada in  placa=HCR605 conf=0.60 veredicto=conflict             revision=True
porteria_entrada in  placa=-      conf=0.50 veredicto=unrecognized_pattern revision=True
porteria_entrada in  placa=-      conf=0.00 veredicto=unrecognized_pattern revision=True
porteria_entrada in  placa=KEM018 conf=0.95 veredicto=confirmed            revision=False
porteria_salida  out placa=KEM018 conf=0.97 veredicto=confirmed            revision=False
outbox: {'pendientes': 6, 'enviados': 0, 'total': 6}
```

Cada línea es un comportamiento distinto: agregación limpia, **moto cuya lectura entra en
conflicto con lo que ve la cámara**, placa extranjera rechazada en vez de inventada, paso
ilegible registrado igual, y una entrada emparejada con su salida por la cámara de salida. El
`person` del final se ignoró correctamente.

**Un test falló y el código tenía razón.** Esperaba `frames_agreed == 3` sobre las lecturas
`KEM018, KEM0I8, KEM018, KEM018`, asumiendo que la lectura mala sería *superada en votos*.
Salió 4: contra la máscara `LLLNNN`, la `I` en casilla numérica se coerce a `1`, así que
`KEM0I8` **se repara** a `KEM018` y las cuatro concuerdan. Corregí la expectativa del test,
no el código. Es la coerción por máscara funcionando dentro del pipeline completo, no solo en
los tests unitarios de `plate_rules`.

**Cómo se prueba**

```powershell
$env:PYTHONPATH="packages\plate_rules\src;services\edge_agent\src"
python -m edge_agent --replay services\edge_agent\tests\fixtures\porteria_demo.jsonl
python -m pytest packages services -q      # 151 tests
```

**Pendiente:** el `Sink` por defecto solo escribe al log porque `services/api` todavía no
existe. La estimación de color sigue desactivada: requiere traer el snapshot de Frigate y
volver a detectar la placa (MQTT no publica su caja), y los umbrales HSV no están calibrados.

---

## 2026-07-26 — `services/api` y el circuito cerrado hasta la base de datos

**Qué se hizo**

FastAPI con dos rutas: `GET /health` y `POST /events`. Más `scripts/inspect_events.py` para
leer de vuelta lo que quedó en la base.

**Alcance deliberadamente mínimo: no hay rutas de lectura.** El panel web hablará directo con
Supabase usando la publishable key, Auth y RLS. Este servicio existe por una sola razón:
escribir eventos requiere la *secret key*, y esa clave no puede salir de un servidor. Añadir
endpoints de lectura sería duplicar lo que Postgres ya resuelve mejor con RLS.

**Decisiones**

- **La placa se revalida en el servidor.** El agente ya normalizó, pero quien decide qué entra
  a la base es el servidor. Una placa que el dominio rechaza se guarda **solo como `raw_read`**
  con `plate_read` en NULL, así nada inventado llega a asociarse con un vehículo.
- **Los conflictos devuelven 200, no 4xx.** `already_recorded` (`23505` sobre
  `frigate_event_id`, reenvío tras corte) y `duplicate` (`23P01`, mismo paso en <90 s) no son
  errores: el paso ya está contabilizado. Un código de error haría que el outbox reintentara
  para siempre algo ya resuelto. En cambio un fallo real de base de datos devuelve **502**,
  para que el agente sí conserve el evento.
- **Las violaciones de restricción se traducen en `supabase.py`**, junto al cliente que las
  produce, no en la ruta.
- **El token de ingesta no es credencial de usuario**, es un secreto compartido entre una
  máquina y el servidor. Las personas se autentican contra Supabase Auth y nunca tocan este
  servicio.

**Dos fallos propios encontrados y corregidos**

1. El estado inyectado se perdía: `TestClient` usado sin su gestor de contexto **no ejecuta el
   `lifespan`**, así que las rutas no encontraban cliente. Se pobla el estado en `create_app`
   y el `lifespan` solo construye el cliente real si no hay uno inyectado.
2. La ruta devolvía 201 también en los conflictos, porque `status_code` es fijo por ruta. Se
   inyecta `Response` para bajarlo a 200 en ese caso.

**Verificación de extremo a extremo contra la base real**

La primera corrida falló entera —el servidor se había caído— y eso resultó ser la mejor
demostración posible del outbox:

```
sincronizados 0, fallidos 6
outbox: {'pendientes': 6, 'enviados': 0, 'total': 6}
last_error: [WinError 10061] conexion rechazada
```

Seis eventos encolados, **ninguno perdido**. Al levantar el API y reintentar los mismos
registros:

```
(los 6 se detectan como "duplicado, ya en cola")   <- idempotencia del outbox
sincronizados 6, fallidos 0
outbox: {'pendientes': 0, 'enviados': 6, 'total': 6}
```

Y leído de vuelta desde Postgres:

```
2026-07-25T17:21:44  porteria_entrada  in  placa=KEM018 crudo=KEM018 confirmed            pending
2026-07-25T17:23:23  porteria_entrada  in  placa=HCR605 crudo=HCR605 conflict             pending
2026-07-25T17:25:03  porteria_entrada  in  placa=-      crudo=29UM92 unrecognized_pattern pending
2026-07-25T17:26:42  porteria_entrada  in  placa=-      crudo=-      unrecognized_pattern pending
2026-07-25T17:27:12  porteria_entrada  in  placa=KEM018 crudo=KEM018 confirmed            pending
2026-07-26T01:40:02  porteria_salida   out placa=KEM018 crudo=KEM018 confirmed            pending

parking_sessions:
  KEM018  entro=2026-07-25T17:27:12  cerrada (08:12:50)
```

La placa portuguesa quedó **solo en `raw_read`**, con `plate_read` en NULL: la revalidación
del servidor hizo su trabajo. Y la vista emparejó sola la entrada con su salida.

Todo en `review_status = pending` porque la tabla `vehicles` está vacía: sin vehículos
registrados, toda placa es desconocida y va a la cola de revisión. Es el comportamiento
correcto, y es justo la cola desde la que el guardia dará de alta los vehículos.

Los datos de demo se borraron después (`--purge-demo`); la base quedó en 0 eventos.

**Cómo se prueba**

```powershell
# 1. levantar el API
$env:PYTHONPATH="packages\plate_rules\src;services\api\src"
python -m uvicorn porteria_api.main:app --port 8000

# 2. circuito completo desde una sesion grabada
$env:PYTHONPATH="packages\plate_rules\src;services\edge_agent\src"
python -m edge_agent --replay services\edge_agent\tests\fixtures\porteria_demo.jsonl --sync

# 3. leer de vuelta
python scripts\inspect_events.py

python -m pytest packages services -q      # 174 tests
```

---

## 2026-07-27 — `apps/web`: el panel, y RLS verificado desde fuera

**Qué se hizo**

Next.js 16 + React 19 + TypeScript + Tailwind. Cinco rutas: `/login`, tablero, `/revision`,
`/historial`, `/vehiculos`. Más `scripts/seed_user.py`, que crea una cuenta de Auth **y** su
fila en `profiles`.

**El panel no pasa por `services/api`.** Habla directo con Supabase usando la publishable key,
Auth y RLS. La API existe solo porque *escribir eventos* necesita la secret key; leer y editar
desde el navegador no la necesita, porque RLS ya decide qué ve y qué puede hacer cada usuario.
Un endpoint intermedio que replicara esas reglas sería una segunda implementación de la misma
política de acceso, y dos implementaciones divergen.

**Decisiones de interfaz**

- **La cola de revisión es la pantalla que justifica el proyecto.** Recibe todo lo que el
  sistema no resolvió solo, y cada corrección del guardia es además el insumo del
  reentrenamiento. No es solo operación: es recolección de datos.
- **Los conflictos se explican en palabras.** La tarjeta dice *"la placa sugiere una moto pero
  la cámara vio un carro; casi siempre significa que el OCR leyó mal un carácter"*. Un guardia
  no debería aprender el vocabulario interno del sistema para hacer su trabajo.
- **Todo se muestra en `America/Bogota`**, nunca en la zona del navegador. Un reporte que
  cambia de horas según el equipo desde el que se consulta es inservible.
- **`getUser()` y no `getSession()`** en el proxy: revalida el token contra Supabase en vez de
  confiar en lo que afirme la cookie.
- **Una cuenta sin `profiles` muestra un mensaje explícito.** RLS la dejaría ver cero filas,
  que es correcto pero se ve idéntico a una app vacía. Un modo de fallo silencioso y confuso
  es peor que un error claro.

**Migración de `middleware` a `proxy`.** Next 16 deprecó la convención `middleware`; se migró
para no arrancar un proyecto nuevo sobre una API obsoleta.

**RLS verificado empíricamente, no por documentación**

La prueba tiene un discriminador real: `cameras` contiene 2 filas sembradas por la migración.

```
--- ANONIMO (solo publishable key) ---
  access_events      HTTP 200  []
  vehicles           HTTP 200  []
  cameras            HTTP 200  []          <- existen 2 filas, ve 0
  parking_sessions   HTTP 200  []

--- AUTENTICADO como guardia ---
  cameras            HTTP 200  filas=2     <- ahora si
  profiles           HTTP 200  [{"full_name":"Guardia de prueba","role":"guard"}]
  POST owners        HTTP 201                escritura permitida
```

Y la puerta de rutas:

```
/            HTTP 307  -> /login?redirect=%2F
/revision    HTTP 307  -> /login?redirect=%2Frevision
/login       HTTP 200
```

Esa redirección es **comodidad, no seguridad**: quien la saltara llegaría a una página que
consulta como anónimo y no recibe nada.

**Datos de demo sembrados.** Se dejaron los 6 eventos de la sesión grabada en la base para que
el panel tenga contenido al abrirlo. Se borran con:

```powershell
python scripts\inspect_events.py --purge-demo
```

**Cómo se prueba**

```powershell
cd apps\web; npm install; npm run dev
# entrar con guardia@unal.edu.co
```

**Pendiente:** Realtime en el tablero, exportación CSV, y restringir el histórico completo a
`admin` — hoy las políticas dan lectura total a cualquier autenticado, más de lo que un
guardia necesita.
