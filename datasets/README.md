# Datasets

El contenido de `raw/` y `processed/` **no se versiona**: son gigabytes y varias licencias
prohíben la redistribución (RodoSol-ALPR y UFPR-ALPR explícitamente). Solo se versionan los
scripts que los obtienen y transforman.

Catálogo completo y para qué sirve cada uno: [../docs/03-datasets.md](../docs/03-datasets.md).
Cómo se prueba cada modelo: [../docs/05-evaluacion.md](../docs/05-evaluacion.md).

## Estructura

```
raw/          descargas sin tocar
  video/      vehicles.mp4, vehicles-2.mp4
processed/    conversiones, recortes, sets sintéticos
scripts/      descarga y conversión (versionados)
```

## Obtener los datos

```powershell
# Video de tráfico real -> prueba el detector de vehículos (modelo 1)
.\.venv\Scripts\python.exe datasets\scripts\download_video_assets.py

# Placas sintéticas colombianas -> prueba el OCR (modelo 3)
.\.venv\Scripts\python.exe scripts\eval_ocr.py --samples 40
```

## Trámite pendiente

**RodoSol-ALPR** (20.000 imgs de cámaras estáticas en peajes — casi el mismo escenario que la
portería) y **UFPR-ALPR** (4.500 imgs con cajas por carácter) se piden por correo a
`rblsantos@inf.ufpr.br` desde una cuenta institucional, adjuntando el acuerdo de licencia
firmado. Tardan 1–5 días hábiles. Solicitarlos no bloquea nada mientras tanto.
