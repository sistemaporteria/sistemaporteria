# Edge stack — Frigate + Mosquitto

Todo lo que corre en el borde. Hoy en el PC de desarrollo, mañana en un mini PC en la
portería. El único cambio al pasar a producción es reemplazar las URLs RTSP simuladas por las
de las cámaras reales.

## Qué levanta

| Servicio | Puerto | Rol |
|---|---|---|
| `mosquitto` | 1883 | Broker MQTT. Desacopla Frigate del `edge_agent`. |
| `rtsp-sim` | 8554 | **Solo demo.** Sirve videos en loop como si fueran cámaras RTSP. Se elimina en producción. |
| `frigate` | 8971 (UI), 5000 (API) | Ingesta, detección de objetos, LPR, grabación, eventos MQTT. |

## Requisitos

- Docker Desktop con backend WSL2 (Windows).
- **≥4 GB de RAM libres** y CPU con AVX + AVX2 — requisito duro del LPR de Frigate.
- Videos de prueba en `./media/` (ver abajo).

## Puesta en marcha

1. Coloca dos videos en `infra/edge/media/`:

   ```
   media/entrada.mp4    vehículos entrando
   media/salida.mp4     vehículos saliendo
   ```

   Para la primera prueba sirve el **mismo archivo copiado dos veces**. Lo importante es
   validar el flujo, no el contenido.

   Fuentes posibles: video grabado con celular en la portería (lo ideal), o clips de
   UA-DETRAC / RodoSol — ver [docs/03-datasets.md](../../docs/03-datasets.md).

2. Levanta el stack:

   ```powershell
   docker compose -f infra/edge/docker-compose.yml up -d
   ```

3. Abre `https://localhost:8971`. Frigate pide crear una contraseña en el primer arranque.

4. Verifica que llegan eventos MQTT:

   ```powershell
   docker exec -it porteria-mosquitto mosquitto_sub -t 'frigate/#' -v
   ```

## Cómo se decide entrada vs salida

**Por cámara, no por tracking.** Los carriles están físicamente separados, así que el nombre
de la cámara determina la dirección. El mapa vive en la configuración del `edge_agent`, no
aquí:

```
porteria_entrada  →  direction = in
porteria_salida   →  direction = out
```

Razón en [docs/00-arquitectura.md §4](../../docs/00-arquitectura.md).

## Parámetros que hay que calibrar

Marcados `CALIBRAR` en `frigate/config.yml`. **No son mediciones**, son puntos de partida:

| Parámetro | Valor actual | Cómo calibrarlo |
|---|---|---|
| `lpr.min_area` | 1500 px² | Medir el área real de la placa en un frame de la portería. Si es muy alto se pierden vehículos lejanos; si es muy bajo se gasta CPU en placas ilegibles. |
| `zones.carril` | placeholder | Redibujar sobre un frame real desde la UI (Settings → Masks & Zones). |
| `detect.fps` | 5 | Subir si los vehículos entran rápido y se pierden tracks; bajar si la CPU se satura. |
| `motion.threshold` | 30 | Bajar si no se detecta movimiento; subir si la lluvia o las ramas disparan detecciones. |

## Producción: qué cambia

1. Eliminar el servicio `rtsp-sim` y su volumen `./media`.
2. Poner las URLs RTSP reales en `cameras.*.ffmpeg.inputs[].path`.
3. Cambiar el detector de `cpu` a `openvino` (mini PC Intel):

   ```yaml
   detectors:
     ov:
       type: openvino
       device: GPU
   ```

4. Poner autenticación en Mosquitto (`allow_anonymous false` + archivo de contraseñas).
5. No exponer el puerto 5000 fuera de localhost: la API interna de Frigate no tiene auth.
