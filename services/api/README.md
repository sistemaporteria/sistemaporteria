# porteria_api

El **único escritor** de `access_events`.

```
edge_agent ──HTTP──→ POST /events ──→ revalida placa ──→ resuelve vehículo ──→ Supabase
                                       (plate_rules)      (tabla vehicles)    (secret key)
```

## Por qué es tan pequeña

El panel web **no pasa por aquí**: habla directo con Supabase usando la publishable key, Auth
y RLS. Este servicio existe por una sola razón: escribir eventos requiere la *secret key*, y
esa clave no puede salir de un servidor. Todo lo que se pueda resolver con RLS se resuelve con
RLS, no con endpoints.

De ahí que no haya rutas de lectura. Añadirlas sería duplicar lo que Postgres ya hace mejor.

## Endpoints

| Ruta | Auth | Qué hace |
|---|---|---|
| `GET /health` | — | Estado del servicio y si Supabase responde |
| `POST /events` | Bearer `API_INGEST_TOKEN` | Registra un paso de vehículo |

`POST /events` devuelve tres estados distintos, y **ninguno de los tres es un error**:

| `status` | HTTP | Significado | Qué hace el agente |
|---|---|---|---|
| `created` | 201 | Paso registrado | marca enviado |
| `already_recorded` | 200 | Reenvío tras corte de red (`23505` en `frigate_event_id`) | marca enviado |
| `duplicate` | 200 | Misma placa y cámara en <90 s (`23P01`) | marca enviado |

Los conflictos devuelven **200 y no 4xx** a propósito: un código de error haría que el outbox
reintentara para siempre algo que ya está resuelto. En cambio, un fallo de base de datos
devuelve **502**, para que el agente sí conserve el evento y reintente.

## Uso

```powershell
$env:PYTHONPATH="packages\plate_rules\src;services\api\src"
python -m uvicorn porteria_api.main:app --host 127.0.0.1 --port 8000
```

Configuración en `.env.local`: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `API_INGEST_TOKEN`.
Para generar el token: `python -c "from porteria_api import generate_ingest_token as g; print(g())"`.

## Decisiones

**La placa se revalida en el servidor, no se confía en el borde.** El agente ya normalizó,
pero quien decide qué entra a la base es el servidor. Una placa que el dominio rechaza se
guarda **solo como `raw_read`**, con `plate_read` en NULL: así nada inventado llega nunca a
asociarse con un vehículo. Verificado con la placa portuguesa `29UM92`.

**Placa desconocida no es un error.** Va a `review_status = 'pending'`, que es precisamente la
cola desde la que el guardia registra vehículos nuevos.

**El token de ingesta no es una credencial de usuario.** Es un secreto compartido entre una
máquina y el servidor. Las personas se autentican contra Supabase Auth desde el navegador y
nunca tocan este servicio.

**Las violaciones de restricción se traducen en `supabase.py`, no en la ruta.** Toda la
historia de idempotencia depende de distinguir `23505` de `23P01` de un fallo real, y ese
conocimiento vive junto al cliente que produce los errores.

## Pruebas

```powershell
$env:PYTHONPATH="packages\plate_rules\src;services\api\src"
python -m pytest services\api -q      # 23 tests, sin red
```

Los tests inyectan un `FakeSupabase`, así que no necesitan base de datos ni credenciales.
