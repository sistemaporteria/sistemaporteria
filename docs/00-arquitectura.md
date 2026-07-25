# Arquitectura — Ruta B (edge + nube)

## 1. Principio rector

**El video nunca sale del borde. Solo viajan eventos.**

Todo lo demás se deriva de ahí.

---

## 2. Flujo de datos completo

```
┌─── EDGE ── hoy: PC del dev · mañana: mini PC en la portería ──────────────────┐
│                                                                                │
│  ① Fuente de video                                                             │
│     demo: archivo .mp4 en loop  (ffmpeg -re -stream_loop -1)                    │
│     prod: 2 cámaras IP RTSP (carril entrada, carril salida)                     │
│                    │                                                            │
│                    ▼                                                            │
│  ② Frigate                                                                      │
│     detección de movimiento (filtro barato, descarta ~95% de frames)            │
│       → detección de objetos: car | motorcycle | bus | truck                    │
│         → detección de placa (YOLOv9) dentro del recorte del vehículo           │
│           → OCR (PaddleOCR) → texto crudo + confianza                           │
│     además: graba video, guarda snapshot del evento                             │
│                    │ MQTT                                                       │
│                    ▼                                                            │
│  ③ Mosquitto (broker)   tópicos: frigate/events, frigate/tracked_object_update  │
│                    │                                                            │
│                    ▼                                                            │
│  ④ edge_agent  (código propio)                                                  │
│     a. normaliza el texto      → plate_rules.normalize                          │
│     b. corrige con máscara     → plate_rules.normalize (coerción posicional)    │
│     c. infiere tipo            → plate_rules.classify (patrón + color)          │
│     d. verificación cruzada    → contra la etiqueta car/motorcycle de Frigate   │
│     e. dirección               → según qué cámara disparó el evento             │
│     f. deduplicación           → ventana de 90 s por (placa, cámara)            │
│     g. escribe en outbox SQLite local                                           │
│                    │ HTTPS, JSON + JPG (~30 KB)                                 │
└────────────────────┼───────────────────────────────────────────────────────────┘
                     ▼
  ⑤ services/api (FastAPI)     valida, resuelve vehículo/dueño, persiste
                     │
                     ▼
  ⑥ Supabase   Postgres · Auth · Storage (recortes) · Realtime · RLS
                     │
                     ▼
  ⑦ apps/web (Next.js)   panel de guardias · registro · reportes · cola de revisión
```

---

## 3. Por qué el outbox local (offline-first)

El agente **nunca** llama a la API directamente desde el hilo que procesa eventos. Escribe
primero en un SQLite local y un worker aparte sincroniza.

```
evento → INSERT en outbox (sent=0)  ← esto nunca falla
            │
worker  →  SELECT WHERE sent=0 → POST a la API → UPDATE sent=1
            └─ si falla: reintento con backoff exponencial, el registro sigue ahí
```

Sin esto, un corte de internet de 10 minutos en hora pico significa **perder ~30 ingresos**
sin forma de recuperarlos. En una portería que hoy funciona con libreta de papel, perder
registros es peor que el sistema actual — y destruiría la confianza en el sistema.

Este patrón se llama **transactional outbox** y es estándar en sistemas distribuidos.

---

## 4. Cómo se determina entrada vs salida

**Decisión: por cámara, no por tracking.**

Los dos carriles están físicamente separados por un bordillo y tienen flechas de sentido
opuesto. Cada carril lleva su propia cámara y cada cámara tiene una dirección fija en la
configuración:

```yaml
cameras:
  porteria_entrada:  { direction: in  }
  porteria_salida:   { direction: out }
```

**Por qué no usar la dirección del movimiento (LineZone / vector del track):** funciona, pero
depende de que el tracking sea estable y falla con vehículos que retroceden, se detienen sobre
la línea o maniobran. La geometría física ya resolvió el problema; usarla es más robusto y
más simple.

**Consecuencia:** el emparejamiento entrada→salida se hace **por placa**, en la base de datos,
no en el borde. El agente solo reporta "la placa X fue vista por la cámara Y en el instante T".

---

## 5. Volumetría — el cálculo que condiciona el diseño

Con **2.000 vehículos/día** (pico), lunes a sábado:

```
2.000 vehículos × 2 eventos (entrada + salida) = 4.000 eventos/día
                                                ≈ 104.000 eventos/mes (26 días)
```

| Recurso | Por unidad | Al mes | Free tier | Veredicto |
|---|---|---|---|---|
| Filas en Postgres | ~300 B/evento | ~31 MB/mes | Supabase 500 MB | **~14 meses**. Suficiente para la demo y el primer año. |
| Imágenes (recorte JPG) | ~30 KB | **~3,1 GB/mes** | Supabase Storage 1 GB | ❌ **Se desborda en 10 días.** |
| Egreso del borde | ~30 KB/evento | ~3,1 GB/mes | — | Trivial. |

### El problema del almacenamiento de imágenes y su solución

3,1 GB/mes no cabe en ningún free tier de forma sostenida. Tres medidas, en orden:

1. **Política de retención**: las imágenes se borran a los **30 días**; las filas se conservan
   indefinidamente. Un reporte administrativo de hace 6 meses necesita la placa y la hora, no
   la foto. Esto acota el uso a ~3,1 GB estables en lugar de crecimiento lineal.
2. **Guardar solo el recorte de la placa** (~8 KB) en vez del frame completo, salvo cuando el
   evento va a la cola de revisión (ahí sí se guarda el contexto). Reduce a ~0,8 GB/mes.
3. **Cloudflare R2** (10 GB gratis, **sin costo de egreso**) en lugar de Supabase Storage
   cuando el volumen lo justifique.

> Con (1) + (2): **~0,8 GB estables** → cabe en Supabase Storage free. El diseño debe soportar
> cambiar de backend de almacenamiento sin tocar la lógica: la API guarda una **URL**, no un
> blob.

### Concurrencia

4.000 eventos/día repartidos en ~14 h de operación = **~0,08 eventos/segundo** de promedio.
Incluso con un pico 20× (cambio de clase, entrada masiva) son ~2 req/s. Cualquier free tier
lo aguanta sobrado. **La escritura no es el cuello de botella; el almacenamiento sí.**

---

## 6. Hosting previsto (producción)

| Componente | Opción | Notas |
|---|---|---|
| API | **Oracle Cloud Always Free** (4 vCPU ARM + 24 GB RAM, permanente) | El mejor free tier para algo 24/7. Alternativa: Fly.io. **No Render free**: duerme a los 15 min. |
| BD + Auth + Storage | **Supabase** free | Ver límites arriba |
| Web | **Vercel** Hobby | Deploy con git push |
| Túnel al edge | **Cloudflare Tunnel** | Expone el mini PC sin IP pública ni abrir puertos en el firewall del campus |
| Monitoreo | **UptimeRobot** / Healthchecks.io | Crítico: un ALPR caído nadie lo nota hasta que piden un reporte |

Para la **demo** todo corre local salvo Supabase, que ya es en línea.

---

## 7. Consideraciones legales (Ley 1581 de 2012 — habeas data)

Placa + nombre del dueño = **dato personal**. Requisitos mínimos antes de producción:

- Aviso de privacidad visible en la portería.
- Política de retención documentada y **efectivamente implementada** (no basta escribirla).
- Control de acceso por rol: un guardia no necesita ver el histórico completo de un vehículo.
- Registro de la base de datos ante la SIC si aplica → **consultar con jurídica de la UNAL**.
- El video no sale del campus (ya garantizado por la arquitectura).

No es un detalle burocrático: es un requisito de la institución y conviene resolverlo antes
del despliegue, no después.
