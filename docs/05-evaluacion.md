# Evaluación: cómo se prueba cada modelo

El sistema tiene tres modelos convolucionales encadenados. **Cada uno necesita datos y
métricas distintas.** Este documento explica cómo se prueba cada uno y reporta las
mediciones ya realizadas.

| # | Modelo | Qué hace | Cómo se prueba | Estado |
|---|---|---|---|---|
| 1 | Detector de vehículos (YOLO/COCO) | localiza carros y motos | video de tráfico real | ✅ datos listos |
| 2 | Detector de placas (YOLOv9) | localiza la placa dentro del vehículo | composición sintética / datos Roboflow | ⬜ pendiente |
| 3 | OCR (CCT / PaddleOCR) | lee los caracteres | **placas sintéticas colombianas** | ✅ **medido** |

---

## 1. El problema: no hay video de portería

Se descargaron los dos únicos videos de tráfico libres, versionados y sin necesidad de
cuenta ([supervision assets](https://supervision.roboflow.com/latest/assets/)):

```powershell
python datasets/scripts/download_video_assets.py
# -> datasets/raw/video/vehicles.mp4    3840x2160, 25 fps, 22 s
# -> datasets/raw/video/vehicles-2.mp4  1920x1080, 30 fps, 43 s
```

**Hallazgo empírico:** ambos son tomas desde un puente sobre autopista. Los vehículos se ven
bien —sirven para el modelo 1— pero **las placas miden ~10 px de ancho**: inservibles para
los modelos 2 y 3.

Esto no es mala suerte, es la norma: el video de tráfico público está grabado para contar
vehículos, no para leer placas. Y confirma de entrada el requisito óptico: sin una cámara
apuntada al punto correcto, no hay ALPR posible por bueno que sea el modelo.

De ahí la estrategia de tres niveles.

---

## 2. Modelo 1 — Detector de vehículos

**Datos:** `vehicles.mp4` y `vehicles-2.mp4` (ya descargados). Vehículos reales, tráfico real,
iluminación real. Para medir con etiquetas: UA-DETRAC (cámara fija, con clima anotado) o
BDD100K (única que separa bien motos). Ver [03-datasets.md](03-datasets.md).

**Métrica:** mAP@0.5 por clase, y sobre todo la matriz de confusión **carro vs moto** — de
ella depende la verificación cruzada.

---

## 3. Modelo 3 — OCR: medición realizada

### Instrumento: `packages/plate_synth`

No existe ningún dataset público de placas colombianas con etiqueta a nivel de carácter. Se
construyó un generador que renderiza placas válidas del catálogo nacional (particular
amarilla, público blanca, oficial verde, moto amarilla) y les aplica **degradaciones
controladas**, una variable a la vez.

La ventaja decisiva del dato sintético aquí no es el volumen: es que la **etiqueta es exacta**
y la degradación es una **variable controlada**. Eso permite responder "¿a cuántos píxeles
falla el OCR?", que es la pregunta de la que sale la especificación de la cámara.

```powershell
python scripts/eval_ocr.py --samples 40
```

### Resultados — `cct-xs-v2-global-model`, n=40 placas

Baseline sin degradar (280 px): **97,5%** exactitud de placa completa, 99,6% por carácter.

> **Resolución de la medición:** con n=40, una placa = 2,5%. Cualquier diferencia de ±2,5%
> **es ruido, no señal.**

| Factor | Rango probado | Efecto | Veredicto |
|---|---|---|---|
| **Motion blur** | k=0 → 17 | k≤7: sin efecto · k=9: **−7,5%** · k=13: **−45%** · k=17: **−95%** | 🔴 **el único factor que destruye el OCR** |
| Ancho de placa | 40 → 280 px | 40 px: **−32,5%** · ≥60 px: plano | 🟡 acantilado bajo 60 px, después no mejora |
| Iluminación | contraluz / noche | −5% en los extremos | 🟢 tolerable |
| Yaw (ángulo horizontal) | 0° → 60° | plano hasta 50° · 60°: −7,5% | 🟢 mucho más tolerante de lo esperado |
| Pitch (ángulo vertical) | 0° → 50° | plano | 🟢 sin efecto medible |
| Desenfoque | σ=0 → 3 | −5% en σ=3 | 🟢 casi irrelevante |
| Ruido gaussiano | σ=0 → 35 | plano | 🟢 sin efecto |
| Compresión JPEG | q=100 → 15 | plano | 🟢 **sin efecto ni a q=15** |

### Lo que esto cambia en el proyecto

**1. El obturador es la prioridad número uno, por encima de todo lo demás.**
El motion blur es el único factor con un acantilado real. Confirma y refuerza el requisito de
obturador fijo 1/500–1/1000 s. **Es más importante que los megapíxeles**: una cámara 4K con
obturador automático rendirá peor que una 1080p con obturador rápido.

**2. La resolución exigida es menor de lo que se había documentado.**
Se había escrito "≥100 px de ancho". La medición dice que **60–80 px bastan** y que por encima
de eso no se gana nada. La razón es arquitectónica: el modelo redimensiona internamente a
64×128 px, así que más píxeles de entrada no aportan más información. *La documentación fue
corregida* — ver [02-placas-colombia.md §7](02-placas-colombia.md).

**3. La tolerancia angular es mucho mayor de lo documentado.**
Se había escrito "<30°". Medido: sin degradación hasta **50°**. Esto relaja bastante las
restricciones de montaje del poste en la portería.

**4. Se puede comprimir agresivamente el video, y eso resuelve un problema de costos.**
El OCR no se degrada ni a calidad JPEG 15. Aplicado al almacenamiento de recortes, ataca
directamente el cuello de botella de ~3,1 GB/mes identificado en
[00-arquitectura.md §5](00-arquitectura.md).

### La capa de dominio no aporta exactitud aquí — y eso también es un resultado

La columna `+ dominio` (normalización + coerción por máscara) resultó **idéntica** a la del
OCR crudo en casi todas las variantes. Es un resultado negativo y hay que reportarlo como tal.

La razón: cuando este modelo se equivoca, sustituye un carácter por otro **del mismo tipo**
(`5`→`6`, `I`→`J`), produciendo una cadena que sigue cumpliendo la máscara. La coerción
posicional solo ayuda cuando el OCR pone una letra en una casilla numérica, que con este
modelo es raro.

**Entonces, ¿para qué sirve `plate_rules`?** No para corregir, sino para **detectar**:

- **rechazo de lecturas inválidas** — en el barrido de motion blur k=13, rechazó 13/40 y a
  k=17, 20/40. Esas lecturas basura no llegan a la base de datos.
- **verificación cruzada** contra la etiqueta `car`/`motorcycle` del detector, que atrapa el
  error `ABC12D`→`ABC120` que ninguna máscara puede detectar.
- **agregación temporal**, que es donde sí se recupera exactitud.

El valor de la capa de dominio es *precisión* (no meter basura), no *cobertura*.

### Limitaciones de esta medición — leer antes de citarla

1. **Son placas sintéticas.** Son más limpias que la realidad: sin suciedad, sin brillo
   especular sobre la superficie retrorreflectiva, sin tornillos, sin marcos de concesionario.
   Los números absolutos son **optimistas**. Lo que sí es válido es el **ranking relativo**
   entre factores, que es lo que se usó para decidir.
2. **Artefacto tipográfico conocido.** Arial Bold dibuja la `I` como una barra vertical
   desnuda, confundible con `T`/`1`/`J`; la tipografía real de las placas las distingue. Por
   eso se reporta todo **relativo al baseline** con las mismas placas, para que ese sesgo
   constante se cancele.
3. **Es `fast-plate-ocr`, no PaddleOCR.** Frigate usa PaddleOCR internamente. Hay que repetir
   el barrido contra el OCR de producción antes de dar estos números por definitivos.
4. **Cada factor se probó aislado.** En la portería se combinan (poca luz *y* movimiento *y*
   ángulo), y las degradaciones combinadas suelen ser peores que la suma. Para eso está el
   modo `--mixed`.
5. **La geometría de la placa de moto está sin calibrar** (`MOTO_ASPECT = 1.35` es una
   estimación). Hay que medirla sobre placas reales.

---

## 4. Modelo 2 — Detector de placas: pendiente

Aún no medido. Plan:

1. **Composición sintética**: pegar placas generadas sobre vehículos reales de
   `vehicles-2.mp4`, con posición y tamaño conocidos → ground truth exacto de la caja.
2. **Datos reales**: exportar de Roboflow Universe (necesita cuenta gratuita) los conjuntos
   de placas colombianas listados en [03-datasets.md](03-datasets.md).

Métrica: IoU y tasa de recuperación en función de la distancia del vehículo.

---

## 5. Set de validación congelado — la regla innegociable

Cuando exista video real de la portería:

1. Etiquetar a mano **200 placas** de video real.
2. Ese conjunto **no se toca nunca más**. Es la única vara honesta.
3. **Ningún modelo reentrenado se despliega si no supera al anterior en ese conjunto.**

Sin esta regla no hay forma de saber si un reentrenamiento mejoró o empeoró el sistema.
Los datos sintéticos sirven para caracterizar sensibilidad; **no sustituyen la validación
con datos reales**.
