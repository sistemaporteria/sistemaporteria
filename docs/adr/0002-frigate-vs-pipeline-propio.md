# ADR 0002 — Frigate como capa de visión, en lugar de un pipeline propio

- **Fecha:** 2026-07-25
- **Estado:** aceptada

## Contexto

Definida la Ruta B ([ADR 0001](0001-ruta-b-edge-nube.md)), falta decidir qué corre en el
borde: un pipeline propio (OpenCV + FastALPR + supervision) o un NVR con LPR integrado.

Restricción explícita del proyecto: es un trabajo académico, pero **no se quiere profundizar
en el funcionamiento interno de los modelos ni en el tuning de costo de cómputo**. El aporte
técnico debe concentrarse en otra parte.

## Opciones consideradas

### A. Pipeline propio (FastALPR + supervision + OpenCV)

- ✅ Control total sobre cada etapa: agregación temporal, ROI adaptativa, umbrales.
- ✅ FastALPR es MIT, ONNX, con OCR **reentrenable** (`fast-plate-ocr`).
- ✅ Mayor mérito académico si el trabajo se evaluara por la ingeniería de visión.
- ❌ Hay que implementar toda la ingeniería de video: reconexión RTSP, buffers, timestamps,
  grabación, retención, snapshots. Semanas de trabajo con muchos casos borde.
- ❌ Mucha superficie donde fallar en producción sin experiencia previa.

### B. Frigate como NVR con LPR integrado

- ✅ Resuelve ingesta RTSP robusta, detección de movimiento como prefiltro (~95% menos
  cómputo), grabación con retención, snapshots y eventos MQTT.
- ✅ LPR incluido desde 0.16 (YOLOv9 + PaddleOCR), gratis, sin Frigate+.
- ✅ Software probado en producción por miles de usuarios.
- ✅ Deja libre el tiempo para la capa de dominio, que es donde está el aporte propio.
- ❌ Menos control sobre la agregación temporal (Frigate hace la suya internamente).
- ❌ El OCR (PaddleOCR) **no es reentrenable** dentro de Frigate.
- ❌ Requiere 4 GB RAM y AVX/AVX2.

## Decisión

**Frigate.** Coincide con la restricción declarada del proyecto y libera el esfuerzo hacia
donde sí hay aporte original: `packages/plate_rules` (reglas de placas colombianas, inferencia
de tipo de vehículo, verificación cruzada) y la ROI autoaprendida por clustering.

Frigate se usa en **modo normal**, no en `type: "lpr"`. El modo dedicado es más rápido pero
salta la detección de objetos general, y con ella se perdería la etiqueta `car`/`motorcycle`
de la que depende toda la verificación cruzada. Es un intercambio consciente: se paga cómputo
a cambio de una señal independiente que detecta errores de OCR.

## Consecuencias

- El contrato de integración es **MQTT**, no una librería Python. `edge_agent` consume
  `frigate/events` y `frigate/tracked_object_update`.
- `known_plates` de Frigate **no se usa**: el registro de vehículos vive en Postgres.
  Duplicarlo en un YAML garantizaría inconsistencia.
- La agregación temporal se implementa igual en `plate_rules.aggregate`, aplicada sobre las
  lecturas que Frigate publica. No se desperdicia: sigue siendo el paso de mayor ganancia.
- **Puerta de salida documentada:** si la precisión medida de PaddleOCR sobre el set de
  validación no alcanza, se puede añadir un servicio de OCR propio con `fast-plate-ocr` que
  reprocese el recorte que Frigate ya guardó. Frigate no bloquea esa ruta.
