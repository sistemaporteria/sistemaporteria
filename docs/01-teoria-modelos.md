# Teoría: cómo funciona un ALPR

Documento de referencia académica. Explica qué hace cada modelo y herramienta del stack, por
qué existe y qué problema resuelve.

---

## 1. Un ALPR no es un modelo, es una cascada

Error conceptual frecuente: pensar que existe "un modelo que lee placas". No existe. Un ALPR
es una **cascada de modelos especializados**, cada uno resolviendo un problema distinto:

```
frame → [detección de objetos] → [detección de placa] → [OCR] → texto
          ¿dónde hay vehículos?   ¿dónde está la placa?  ¿qué dice?
```

¿Por qué en cascada y no un solo modelo extremo a extremo? Porque cada etapa **reduce el
espacio de búsqueda** para la siguiente. Buscar seis caracteres de 20 px en un frame de
1920×1080 (2 millones de píxeles) es un problema muy distinto —y mucho más difícil— que
leerlos en un recorte de 200×100 ya localizado y rectificado. La cascada convierte un
problema imposible en tres problemas fáciles.

Además cada etapa se puede reemplazar, medir y mejorar por separado. Si la precisión es mala,
se puede saber *cuál* etapa falla.

---

## 2. Etapa 1 — Detección de objetos (YOLO)

**YOLO** = *You Only Look Once*. Familia de detectores de objetos en una sola pasada.

**El problema que resuelve:** dada una imagen, devolver una lista de `(clase, bounding box,
confianza)`. Ej: `("car", [320,180,640,520], 0.94)`.

**Cómo funciona, en esencia:** los detectores anteriores (R-CNN) proponían regiones y luego
clasificaban cada una — lento, muchas pasadas. YOLO divide la imagen en una rejilla y hace
que **cada celda prediga directamente** las cajas y clases que le corresponden, en una sola
pasada de la red. De ahí "you only look once": una inferencia, no miles. Eso es lo que lo
hizo viable en tiempo real.

**Qué se usa aquí:** el detector de Frigate, preentrenado en **COCO** (80 clases, entre ellas
`car`, `bus`, `truck`, `motorcycle`). No se entrena nada.

**Post-procesado — NMS (Non-Maximum Suppression):** la red produce muchas cajas solapadas
para el mismo objeto. NMS se queda con la de mayor confianza y descarta las que se solapan
demasiado con ella. Detalle relevante: el modelo `yolo-v9-t-384-license-plate-end2end` de
FastALPR trae el NMS **dentro del grafo ONNX** (por eso "end2end"), lo que ahorra código y
tiempo en CPU.

**Nota de licencia:** las implementaciones de Ultralytics (YOLOv8/YOLO11) son **AGPL-3.0**,
que exige liberar el código de un servicio ofrecido por red. Para un sistema interno
universitario suele ser tolerable, pero conviene tenerlo consciente. Alternativas
Apache-2.0: RT-DETR, RF-DETR. Frigate usa modelos con licencias compatibles con su
distribución.

---

## 3. Etapa 2 — Detección de placa

Mismo tipo de modelo (YOLO), pero entrenado con **una sola clase**: `license_plate`. Se
ejecuta dentro del recorte del vehículo, no sobre el frame completo.

**Por qué acotar al recorte del vehículo:**
1. Menos área que analizar → más rápido.
2. Elimina falsos positivos estructuralmente: un cartel rectangular en la pared no está
   dentro de un carro, así que nunca se propone como placa.
3. Permite subir la resolución efectiva. En vez de encoger 1920×1080 a 384×384 (donde la
   placa mide 15 px y es ilegible), se recorta el vehículo y se procesa a resolución nativa.
   Esta idea —procesar recortes a resolución completa en lugar de la imagen entera reducida—
   es el patrón **SAHI** (*Slicing Aided Hyper Inference*) y es la técnica de mayor impacto
   para objetos pequeños.

Frigate implementa esto: por defecto necesita detectar primero un `car` o `motorcycle` antes
de correr el detector de placa.

---

## 4. Etapa 3 — OCR de placa

**El problema:** dado un recorte de placa, devolver la cadena de caracteres. No es
clasificación (no hay un número fijo de clases) sino **reconocimiento de secuencia**: la
salida es una secuencia de longitud variable.

Dos familias:

**a) OCR general — PaddleOCR** (lo que usa Frigate)
Pipeline de dos redes: una de *detección de texto* (dónde hay texto en la imagen) y otra de
*reconocimiento* (qué dice cada región). Entrenado con texto general de cualquier tipo.
Ventaja: robusto, multilenguaje, muy probado. Desventaja: no sabe nada de placas — no conoce
sus formatos, no aprovecha que siempre son 5–7 caracteres alfanuméricos en mayúscula.

**b) OCR especializado en placas — fast-plate-ocr**
Modelos pequeños entrenados solo con placas. El `cct-xs-v2-global-model` cubre 65+ países.
CCT = *Compact Convolutional Transformer*: convoluciones para extraer características locales
+ atención para modelar la relación entre caracteres. Como la longitud está acotada y el
alfabeto es pequeño, el modelo puede ser diminuto y aun así más preciso que un OCR general
**en su dominio**. Además es **reentrenable** con datos propios.

**CTC (Connectionist Temporal Classification):** el truco que permite entrenar estos modelos
sin saber dónde empieza y termina cada carácter. La red emite una predicción por columna de
píxeles y CTC colapsa las repeticiones y los "blancos" para producir la secuencia final. Es
lo que evita tener que segmentar cada carácter a mano.

**Decisión del proyecto:** se arranca con PaddleOCR (viene con Frigate, cero configuración).
Si la precisión medida en el set de validación no alcanza, se evalúa migrar a fast-plate-ocr
por su capacidad de fine-tuning. La medición decide, no la intuición.

---

## 5. Tracking multi-objeto — ByteTrack

**El problema:** la detección es *por frame* y no tiene memoria. El carro del frame 100 y el
del frame 101 son, para el detector, dos objetos sin relación. El tracking les asigna un
`track_id` estable.

**Por qué es indispensable aquí:** sin `track_id` no se puede
(a) agregar las 30 lecturas del mismo vehículo en una sola decisión, ni
(b) saber en qué **dirección** cruzó una línea, ni
(c) evitar registrar el mismo carro 30 veces.

**ByteTrack, la idea clave:** los trackers clásicos descartan las detecciones de baja
confianza porque suelen ser ruido. ByteTrack observó que las detecciones de baja confianza
frecuentemente son **objetos reales parcialmente ocluidos**. Entonces hace la asociación en
dos pasadas: primero empareja los tracks con las detecciones de alta confianza; después,
intenta emparejar los tracks huérfanos con las de **baja** confianza. Resultado: mucho menos
pérdida de identidad cuando un vehículo pasa detrás de otro o detrás de la caseta. Simple y
muy efectivo.

Frigate hace su propio tracking internamente y expone un `id` de objeto por MQTT, que cumple
la misma función.

---

## 6. Agregación temporal

Ver [02-placas-colombia.md §6](02-placas-colombia.md). Es el paso que más precisión aporta:
una lectura por frame al ~90% agregada sobre 30 frames del mismo `track_id` llega a ~98-99%
por votación ponderada por confianza.

---

## 7. Frigate — el NVR

**NVR** = *Network Video Recorder*. Frigate es un NVR open source con detección por IA,
diseñado para correr localmente.

**Qué resuelve (y que sería costoso reimplementar):**

- **Ingesta RTSP robusta**: reconexión automática, manejo de timestamps, buffers. Un stream
  RTSP real se cae, se desincroniza y cambia de bitrate constantemente; manejarlo bien es
  semanas de trabajo.
- **Detección de movimiento como filtro previo**: solo corre la IA cuando algo se mueve.
  Reduce el cómputo ~95%. Es lo que hace viable el sistema en un mini PC.
- **Grabación con retención** y recorte automático de eventos (evidencia).
- **LPR integrado** desde la versión 0.16: detector YOLOv9 de placas + PaddleOCR. Gratis, sin
  suscripción Frigate+.
- **Publicación MQTT** de cada evento.

**Requisitos:** ≥4 GB RAM y CPU con instrucciones AVX + AVX2.

**Opciones de configuración relevantes:**
- `min_area` (default 1000 px²) — área mínima de la placa para intentar leerla. Evita
  desperdiciar cómputo en placas ilegibles por lejanas.
- `known_plates` — mapea placas a etiquetas. **No se usa aquí**: la lista de vehículos vive
  en Postgres, no en un YAML. Duplicarla sería una fuente de inconsistencia.
- `type: "lpr"` — modo cámara dedicada a placas: salta la detección de objetos general y corre
  el pipeline de placa directamente sobre el movimiento. Más rápido, pero **se pierde la
  etiqueta `car`/`motorcycle`** que la verificación cruzada necesita. Por eso aquí se usa el
  modo normal.

**Salida MQTT:** `frigate/events` y `frigate/tracked_object_update`, con el texto en
`recognized_license_plate` (o en `sub_label` si la placa estaba en `known_plates`).

[Documentación oficial de LPR](https://docs.frigate.video/configuration/license_plate_recognition/)

---

## 8. MQTT y Mosquitto

**MQTT** es un protocolo de mensajería publicación/suscripción, diseñado para IoT: mínimo
overhead, pensado para redes poco fiables. **Mosquitto** es el broker (servidor) más común.

**Por qué usar un bus en vez de que Frigate llame directamente a la API:**

1. **Desacoplamiento**: si el agente se cae o se reinicia, Frigate sigue funcionando y
   grabando. Y viceversa.
2. **Múltiples consumidores**: mañana se puede añadir un display en la caseta, una alarma de
   placa en lista negra o un logger de depuración, todos escuchando el mismo tópico sin tocar
   Frigate.
3. **Es la interfaz que Frigate ya expone.** No hay que modificar Frigate.

---

## 9. ONNX y ONNX Runtime

**ONNX** (*Open Neural Network Exchange*) es un formato estándar para representar redes
neuronales, independiente del framework en que se entrenaron. **ONNX Runtime** es el motor
que las ejecuta.

**Por qué importa:** se entrena en PyTorch, se exporta a ONNX, y el **mismo archivo** corre en
CPU, GPU NVIDIA (CUDA), Intel (OpenVINO), Windows (DirectML) o ARM, sin tocar el código. Para
un proyecto que hoy corre en un PC Windows y mañana en un mini PC Intel en la portería, esta
portabilidad no es un lujo: es lo que evita reescribir el sistema al cambiar de hardware.

**OpenVINO** es el backend de Intel. En un mini PC N100 típicamente duplica o triplica el FPS
frente a CPU pura, sin cambiar el modelo.

---

## 10. Dónde queda el clustering

La idea original del proyecto mencionaba "un modelo de clustering". El ALPR en sí no usa
clustering — usa detección y reconocimiento de secuencia, que son supervisados. Pero el
clustering **sí tiene un lugar legítimo y valioso** en el sistema: el aprendizaje automático
de la **zona de interés (ROI)**.

```
Durante 2 semanas → registrar (cx, cy, w, h) de cada placa leída con confianza > 0.9
   ↓
DBSCAN sobre los centros (cx, cy)
   ↓ DBSCAN agrupa por densidad y no requiere saber cuántos grupos hay de antemano
   ↓ — ideal aquí, porque no se sabe si habrá 1, 2 o 3 trayectorias
   → cada cluster denso = un carril real por donde pasan los vehículos
   ↓
envolvente al percentil 95 de cada cluster + 15% de margen
   → polígono de ROI generado automáticamente
```

Beneficios: el rango de tamaños dentro del cluster da además **filtros de talla automáticos**
(descarta como falso positivo cualquier "placa" de 20 px o de 500 px). Y si alguien mueve o
golpea la cámara, los nuevos puntos dejan de caer en el cluster → **alerta automática de
recalibración**.

Es un aporte propio y defendible para el componente académico del trabajo.
