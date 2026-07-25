# Datasets

Tres necesidades distintas, tres conjuntos de datos distintos. Confundirlas es un error común.

| Necesidad | Qué se necesita | Modelo que alimenta |
|---|---|---|
| **A. Detección de vehículos** | Escenas completas con bounding boxes de carro/moto/bus/camión | Detector de objetos de Frigate |
| **B. Detección de placas** | Escenas con bounding box de la placa | Detector YOLOv9 de placas |
| **C. OCR de placas** | **Recortes** de placas + su texto como etiqueta | PaddleOCR / fast-plate-ocr |
| **D. Extremo a extremo** | Video de la portería real | Evaluación del sistema completo |

Nota importante: para la demo **no se entrena nada**. Los modelos vienen preentrenados. Estos
datasets sirven para **evaluar** (medir qué tan bien lo hacen) y, más adelante, para
**fine-tuning** con datos propios. Evaluar antes de entrenar es el orden correcto: sin una
métrica base no se sabe si el entrenamiento mejoró algo.

---

## A. Detección de vehículos

El detector de Frigate ya viene entrenado en **COCO**, que incluye las clases `car`, `bus`,
`truck` y `motorcycle`. Para el caso de uso eso suele bastar. Estos datasets sirven para
**medir** su desempeño en escenas tipo CCTV, que es donde COCO flaquea (COCO son fotos
"bonitas" de nivel de calle, no vistas cenitales de cámara fija).

| Dataset | Tamaño | Clases | Por qué sirve | Acceso |
|---|---|---|---|---|
| **UA-DETRAC** | 100 videos, >140.000 frames, **1.21 M** bboxes | Car, Bus, Van, Other | **El más parecido a una portería**: cámara fija sobre vía, con atributos de clima (soleado, nublado, lluvia, noche) y de oclusión. El clima etiquetado permite medir degradación por condición. | [Roboflow Universe](https://universe.roboflow.com/cs474-ug2-vehicle-detection/ua-detrac-rvwkg) · [paper](https://faculty.ucmerced.edu/mhyang/papers/cviu2020_detrac.pdf) |
| **BDD100K** | 100.000 frames, 1.84 M bboxes | 10 clases incl. Car, Truck, Bus, **Motor**, Bike, Rider | Es el único grande que separa bien **motos**. Crítico aquí, porque la verificación cruzada depende de distinguir moto de carro. Diversidad enorme de clima y hora. | [descripción](https://www.labellerr.com/blog/bdd100k-a-huge-database-of-diverse-driving-videos/) |
| **COCO** (referencia) | 328k imgs | 80 clases, 3 de vehículo + motorcycle | Es la línea base con la que ya vienen los modelos. Útil para comparar. | público |
| **BMD-45** | CCTV urbano de ciudades en desarrollo | vehículos | Contexto latinoamericano/asiático, tráfico mixto denso con muchas motos — más cercano a Manizales que BDD100K (EE.UU.). | [arXiv](https://arxiv.org/pdf/2604.24419) |

**Recomendación de uso:** UA-DETRAC para medir detección en cámara fija; BDD100K para medir
específicamente la discriminación carro/moto.

---

## B. Detección de placas (localización)

| Dataset | Tamaño | Por qué sirve | Acceso |
|---|---|---|---|
| **Roboflow — License Plate Recognition** | ~10.125 imgs | Formato YOLO listo, export en un clic. El estándar de facto para arrancar. | [Roboflow Universe](https://universe.roboflow.com/roboflow-universe-projects/license-plate-recognition-rxg4e) |
| **Placas Colombia (ITM)** | variable | **Placas colombianas reales.** Único conjunto con el formato y color local. | [Roboflow](https://universe.roboflow.com/itm-mprof/placas-colombia) |
| **placas colombianas** | variable | Segundo conjunto colombiano, complementario. | [Roboflow](https://universe.roboflow.com/licenseplates-gk27i/placas-colombianas) |
| **Kaggle — License Plate Detection** | 10.125 imgs | Complemento genérico. | [Kaggle](https://www.kaggle.com/datasets/barkataliarbab/license-plate-detection-dataset-10125-images) |
| **CCPD** (China) | ~300.000 | Ángulos e iluminación extremos. **Solo para el detector**, no para el OCR: el formato de placa chino es distinto. | público |

---

## C. OCR de placas — recortes con texto etiquetado

Estos son los que el usuario pidió específicamente para probar el modelo lector de caracteres.

| Dataset | Tamaño | Contenido | Acceso |
|---|---|---|---|
| **RodoSol-ALPR** ⭐ | **20.000** imgs | Cámaras **estáticas en peajes** de la autopista ES-060 (Brasil). Reparto: 5.000 autos placa brasileña + 5.000 motos brasileñas + 5.000 autos Mercosur + 5.000 motos Mercosur. | Correo a `rblsantos@inf.ufpr.br` desde correo institucional + acuerdo de licencia. 1–5 días hábiles. [GitHub](https://github.com/raysonlaroca/rodosol-alpr-dataset) |
| **UFPR-ALPR** ⭐ | 4.500 imgs | Bounding boxes de placa **y de cada carácter individual**. El más útil para entrenar/evaluar OCR a nivel de carácter. | Mismo trámite. [UFPR VRI](https://web.inf.ufpr.br/vri/databases/) |
| **Global License Plate Dataset** | 74 países | Texto de placa + bboxes + segmentaciones. Incluye Latinoamérica. | [GitHub](https://github.com/siddagra/Global-License-Plate-Dataset) · [arXiv](https://arxiv.org/html/2405.10949v1) |
| **UC3M-LP** | 1.975 imgs / 2.547 vehículos / **12.757 caracteres** | Español (europeo). Trae versión de **recortes ya cortados** para reconocimiento puro. Split oficial 80/20. | [GitHub](https://github.com/ramajoballester/UC3M-LP), abierto |
| **LPLC** | >10k imgs radar, >12k placas | Clasificación de **legibilidad** de la placa. Sirve para entrenar el umbral de "esto no vale la pena leerlo" y evitar lecturas basura. | [GitHub](https://github.com/lmlwojcik/lplc-dataset) |
| **License Plate Characters — Detection OCR** | 209 recortes / 2.026 cajas de carácter | Pequeño pero anotado carácter por carácter en PascalVOC. Bueno para pruebas rápidas. | [Kaggle](https://www.kaggle.com/datasets/francescopettini/license-plate-characters-detection-ocr) |
| **OpenALPR benchmark** | — | Placas de EE.UU., solo texto sin bboxes. Referencia histórica. | público |

### ⭐ Por qué RodoSol y UFPR son los prioritarios

**RodoSol-ALPR es casi exactamente el escenario de este proyecto**: cámara fija, montada
sobre un carril, vehículo aproximándose y deteniéndose ante una barrera. No es video de
tráfico en movimiento libre — es una portería/peaje. Y trae motos separadas de autos, lo que
permite evaluar la verificación cruzada de §4 de [02-placas-colombia.md](02-placas-colombia.md).

Además las placas **Mercosur** son visualmente cercanas a las colombianas modernas (fondo
claro, caracteres negros, tipografía similar), mucho más que cualquier dataset europeo o
estadounidense.

**Acción:** solicitar ambos **ya** con el correo `@unal.edu.co`, en paralelo al desarrollo.
El trámite tarda días y no bloquea nada mientras tanto.

---

## D. Datos propios — los que más van a rendir

Ningún dataset público reproduce el contraluz de Manizales, el ángulo exacto del poste de la
portería, ni las placas amarillas colombianas con el logo del Ministerio en el centro.

**Plan:**

1. Grabar **2 h de video real** en la portería con celular en trípode, en la posición donde
   iría la cámara. Cuatro condiciones: mañana, mediodía (contraluz fuerte), tarde con lluvia,
   noche.
2. Etiquetar a mano **200 placas** → este es el **set de validación congelado**. No se toca
   nunca más. Es la única vara honesta para comparar versiones del sistema.
3. Dejar el sistema corriendo y auto-guardar cada recorte con su lectura y confianza.
4. El guardia corrige las lecturas dudosas en el panel web (2 clics).
5. Con **500–2.000 recortes corregidos** → fine-tuning del OCR. Ganancia típica reportada:
   **+5 a +15 puntos** sobre el modelo global.

> **Regla innegociable:** un modelo reentrenado solo se despliega si supera al anterior en el
> set de validación congelado. Sin esa regla no se puede saber si el reentrenamiento mejoró o
> empeoró el sistema.

---

## Convenciones del repositorio

```
datasets/
├── raw/          descargas sin tocar, tal cual vienen   (ignorado por git)
├── processed/    convertidos a formato YOLO / recortes  (ignorado por git)
└── scripts/      descarga y conversión (versionados)
```

El contenido de `raw/` y `processed/` **nunca** se commitea: son gigabytes y muchos tienen
licencias que prohíben la redistribución (RodoSol y UFPR explícitamente). Solo se versionan
los scripts que los obtienen y transforman.
