# edge_agent

Traduce lo que ve Frigate a eventos de acceso del dominio, y garantiza que no se pierda
ninguno aunque se caiga internet.

```
frigate/events                ──┐
frigate/tracked_object_update ──┴─→ pipeline ─→ outbox SQLite ─→ sincronizador ─→ API
                                      │
                                      ├── agregación temporal   (plate_rules.aggregate)
                                      ├── normalización + máscara (plate_rules.normalize)
                                      ├── tipo de vehículo + color (plate_rules.classify)
                                      ├── verificación cruzada contra car/motorcycle
                                      ├── dirección según la cámara
                                      └── deduplicación por ventana de 90 s
```

## Uso

```powershell
# Reproducir una sesión grabada: sin broker, sin cámara, sin Frigate
python -m edge_agent --replay services\edge_agent\tests\fixtures\porteria_demo.jsonl

# Contra el broker real
python -m edge_agent

# Estado de la cola
python -m edge_agent --status
```

Configuración en `.env.local` (ver `.env.example`): `MQTT_HOST`, `CAMERA_DIRECTIONS`,
`API_BASE_URL`, `API_INGEST_TOKEN`, `OUTBOX_PATH`, `DEDUP_WINDOW_SECONDS`.

## Decisiones

**El outbox no es opcional.** El agente nunca llama a la API desde el hilo que procesa MQTT:
escribe primero en SQLite —operación que no puede fallar por red— y un worker aparte drena la
cola con reintentos y *backoff*. Sin esto, un corte de diez minutos en hora pico pierde en
silencio unos treinta ingresos. En una portería que hoy funciona con libreta de papel, perder
registros es peor que el sistema al que reemplaza.

**Se emite en el evento `end`, no en cada `update`.** Frigate refina la placa mientras el
vehículo se mueve; solo al final se tiene la mejor evidencia. Mientras tanto el agente
acumula cada mensaje `lpr` y al cerrar corre su propia votación ponderada por confianza. Esto
también protege de que Frigate cambie su estrategia interna de agregación.

**La dirección la da la cámara, no el movimiento.** Los dos carriles están físicamente
separados por un bordillo: la geometría ya respondió la pregunta. Analizar el vector del
track sería menos robusto y fallaría con vehículos que retroceden o maniobran sobre la línea.

**Un vehículo sin lectura de placa también genera evento.** Un paso ilegible es información:
descartarlo escondería una cámara que se está degradando. Va a la cola de revisión.

**La deduplicación está en dos capas** —ventana en memoria en el agente y restricción de
exclusión en Postgres— porque el agente se reinicia y pierde su estado, y la base no.

**El `frigate_event_id` viaja en cada evento.** MQTT entrega *al menos una vez*, así que el
mismo evento puede llegar dos veces; ese identificador hace la ingesta idempotente tanto en
el outbox como en la base.

## Pruebas

```powershell
$env:PYTHONPATH="packages\plate_rules\src;services\edge_agent\src"
python -m pytest services\edge_agent -q      # 60 tests
```

`tests/fixtures/porteria_demo.jsonl` es una sesión grabada con seis pasos de vehículo que
cubre el camino completo: agregación con un frame malo recuperado por la máscara, una moto
cuya lectura entra en conflicto con lo que ve la cámara, una placa extranjera rechazada, un
paso ilegible, y una entrada emparejada con su salida.

## Pendiente

- Estimación del color de la placa (`enable_color_estimation`). Requiere traer el snapshot de
  Frigate y volver a detectar la placa, porque MQTT no publica la caja de la placa. Los
  umbrales HSV además siguen sin calibrar.
- Subida del recorte a almacenamiento; hoy `image_url` viaja vacío.
