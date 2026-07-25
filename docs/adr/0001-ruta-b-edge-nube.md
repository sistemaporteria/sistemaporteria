# ADR 0001 — Arquitectura Ruta B: procesamiento en el borde, datos en la nube

- **Fecha:** 2026-07-25
- **Estado:** aceptada

## Contexto

Hay que decidir dónde se ejecutan los modelos de visión: en la nube, en el borde (portería),
o un híbrido. El volumen esperado es de 1000–2000 vehículos/día con dos cámaras 1080p, en una
universidad pública colombiana con presupuesto cero para infraestructura.

## Opciones consideradas

### A. Todo en la nube (streaming del video a un servidor con GPU)

- ✅ Cero hardware en sitio, actualización centralizada, escalable a más porterías.
- ❌ **Ancho de banda prohibitivo**: 2 cámaras 1080p 24/7 ≈ 2–4 Mbps sostenidos ≈ **1 TB/mes
  de subida**. Ninguna conexión institucional lo tolera sin conflicto.
- ❌ Costo de GPU en la nube, sin free tier viable para carga continua.
- ❌ Latencia alta; inviable si algún día se conecta a una talanquera.
- ❌ **El video sale del campus** → problema de habeas data (Ley 1581 de 2012).

### B. Edge + nube (procesar en sitio, sincronizar solo eventos)

- ✅ Egreso de ~30 KB por evento ≈ **3 GB/mes** en vez de 1 TB.
- ✅ El video nunca sale del campus.
- ✅ Funciona sin internet (con outbox local) — crítico en una portería.
- ✅ Cabe holgado en free tiers.
- ❌ Requiere un mini PC en sitio (~USD 150–200) y mantenimiento físico.

### C. Todo local (también el servidor web, expuesto con Cloudflare Tunnel)

- ✅ Máxima privacidad, costo cloud cero.
- ❌ Respaldos, disponibilidad y actualizaciones quedan bajo responsabilidad propia.
- ❌ Un corte de luz en la portería tumba también la consulta administrativa.

## Decisión

**Ruta B.** El principio rector es: *el video nunca sale del borde; solo viajan eventos.*

El diseño mantiene la puerta abierta a degradar hacia C si la red del campus resulta poco
fiable: basta con levantar la API y el web localmente, ya que se comunican por HTTP.

## Consecuencias

- Se necesita un `edge_agent` propio que traduzca eventos de Frigate a eventos de dominio.
- Se necesita un **outbox local** (SQLite) para no perder registros sin conexión.
- El almacenamiento de imágenes se convierte en el recurso crítico, no el cómputo ni la
  base de datos. Obliga a una política de retención explícita
  (ver [00-arquitectura.md §5](../00-arquitectura.md)).
- Se depende de hardware físico en un espacio compartido: hace falta UPS y protección.
