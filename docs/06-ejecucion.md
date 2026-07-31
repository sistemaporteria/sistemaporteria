# Cómo ejecutar el sistema

Tres procesos independientes. Para ver la demo completa hacen falta los tres, pero cada uno
arranca y se prueba por separado.

```
[1] Frigate (Docker)  ──MQTT──→  [2] edge_agent  ──HTTP──→  [3] API  ──→ Supabase ──→ [4] panel
```

---

## Paso 0 — Preparar el entorno (una sola vez)

```powershell
cd D:\Sistema\Carpetas\Programacion\ML\vehiculos_porteria

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

cd apps\web
npm install
cd ..\..
```

Verificar que todo está sano:

```powershell
$env:PYTHONPATH="packages\plate_rules\src;packages\plate_synth\src;services\edge_agent\src;services\api\src"
.\.venv\Scripts\python.exe -m pytest packages services -q      # 174 tests
```

`.env.local` debe existir en la raíz (ver `.env.example`) y en `apps/web/`.

---

## La ruta rápida: ver el sistema funcionando en 3 minutos

Sin Docker ni cámaras. Reproduce una sesión grabada de Frigate a través de todo el pipeline.

**Terminal 1 — API de ingesta**

```powershell
$env:PYTHONPATH="packages\plate_rules\src;services\api\src"
.\.venv\Scripts\python.exe -m uvicorn porteria_api.main:app --port 8000
```

**Terminal 2 — reproducir la sesión**

```powershell
$env:PYTHONPATH="packages\plate_rules\src;services\edge_agent\src"
.\.venv\Scripts\python.exe -m edge_agent --replay services\edge_agent\tests\fixtures\porteria_demo.jsonl --sync
```

Salida esperada — cada línea es un comportamiento distinto del dominio:

```
porteria_entrada in  placa=KEM018 confirmed             revision=False
porteria_entrada in  placa=HCR605 conflict              revision=True   <- moto vs carro
porteria_entrada in  placa=-      unrecognized_pattern  revision=True   <- placa extranjera
porteria_entrada in  placa=-      unrecognized_pattern  revision=True   <- paso ilegible
porteria_entrada in  placa=KEM018 confirmed             revision=False
porteria_salida  out placa=KEM018 confirmed             revision=False
sincronizados 6, fallidos 0
```

**Terminal 3 — panel web**

```powershell
cd apps\web
npm run dev
```

Abrir <http://localhost:3000> y entrar con `guardia@unal.edu.co` / `PorteriaDemo2026!`.

Y para ver los datos desde la base:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_events.py
```

---

## Probar la resiliencia (vale la pena verlo)

Con la API **apagada**, reproducir la sesión: los seis eventos quedan en cola y no se pierde
ninguno. Al encender la API y volver a sincronizar, se entregan todos.

```powershell
# con la API apagada
.\.venv\Scripts\python.exe -m edge_agent --replay ...\porteria_demo.jsonl --sync
#   -> sincronizados 0, fallidos 6
#   -> outbox: {'pendientes': 6, 'enviados': 0}

# encender la API y repetir
#   -> sincronizados 6, fallidos 0
#   -> outbox: {'pendientes': 0, 'enviados': 6}
```

Es el comportamiento que hace que el sistema sea mejor que la libreta de papel: un corte de
red no cuesta registros.

---

## La ruta completa: con Frigate y video real

Requiere Docker Desktop (WSL2), ≥4 GB de RAM libres y CPU con AVX/AVX2.

```powershell
# 1. Videos de prueba con placas legibles
.\.venv\Scripts\python.exe datasets\scripts\download_alpr_videos.py
Copy-Item datasets\raw\video\alpr_video1.mp4 infra\edge\media\entrada.mp4
Copy-Item datasets\raw\video\alpr_test.mp4   infra\edge\media\salida.mp4

# 2. Levantar Frigate + Mosquitto + simulador RTSP
docker compose -f infra\edge\docker-compose.yml up -d

# 3. Ver la interfaz de Frigate
#    https://localhost:8971  (pide crear contrasena en el primer arranque)

# 4. Ver los eventos MQTT en crudo
docker exec -it porteria-mosquitto mosquitto_sub -t 'frigate/#' -v

# 5. El agente, ahora contra el broker real
$env:PYTHONPATH="packages\plate_rules\src;services\edge_agent\src"
.\.venv\Scripts\python.exe -m edge_agent
```

> ✅ Camino **verificado en ejecución**: Frigate detecta, el LPR lee la placa y el evento
> llega hasta Supabase. Corregir cuatro defectos costó — ver la última sección del
> [CHANGELOG](CHANGELOG-IMPLEMENTACION.md).
>
> Dos cosas que conviene saber antes de mirar la salida:
>
> - El video de prueba **no es colombiano**. Las placas que lee (`CD864MY`, `DC·458-BC`) no
>   encajan en `LLLNNN`, así que el dominio las marca `unrecognized_pattern` y las manda a
>   revisión. Es la conducta correcta.
> - El LPR de Frigate **solo corre sobre `car` y `motorcycle`**. Los objetos etiquetados
>   `bus` nunca pasan por el OCR.
>
> Los parámetros marcados `CALIBRAR` (`min_area`, zonas, `fps`) siguen siendo puntos de
> partida razonados, no mediciones: eso requiere video de la portería.

---

## Herramientas de diagnóstico

```powershell
# Medir el OCR contra placas sinteticas colombianas
.\.venv\Scripts\python.exe scripts\eval_ocr.py --samples 40

# Correr el detector + OCR sobre un video y reportar ancho de placa en pixeles
.\.venv\Scripts\python.exe scripts\probe_video_alpr.py datasets\raw\video\alpr_video1.mp4 --every 8

# Ventana en vivo: lectura cruda del modelo vs veredicto del dominio, lado a lado
#   q/ESC salir, espacio pausar, s guardar el frame
.\.venv\Scripts\python.exe scripts\live_view.py datasets\raw\video\alpr_video1.mp4 --detector-label car
.\.venv\Scripts\python.exe scripts\live_view.py rtsp://localhost:8554/entrada --detector-label car

# Ver que hay en la base
.\.venv\Scripts\python.exe scripts\inspect_events.py
.\.venv\Scripts\python.exe scripts\inspect_events.py --purge-demo

# Comprobar que las politicas por rol hacen lo que dicen
.\.venv\Scripts\python.exe scripts\verify_rls.py

# Estado de la cola local del agente
.\.venv\Scripts\python.exe -m edge_agent --status

# Crear un usuario del panel
.\.venv\Scripts\python.exe scripts\seed_user.py correo@unal.edu.co --role guard --name "Nombre"
```

---

## Cuentas de prueba

| Correo | Contraseña | Rol |
|---|---|---|
| `guardia@unal.edu.co` | `PorteriaDemo2026!` | guard |
| `admin@unal.edu.co` | `PorteriaDemo2026!` | admin |

Son cuentas de demostración con contraseña conocida y compartida. **Borrarlas antes de
producción**, junto con los datos sembrados.
