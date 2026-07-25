# Placas colombianas: formatos, colores y tipo de vehículo

Este documento es la base teórica de `packages/plate_rules`. Explica cómo se deduce el tipo
de vehículo a partir de la placa, por qué el texto solo no alcanza, y cómo se contrasta con
lo que ve la cámara.

---

## 1. Catálogo de placas vigentes

Sistema nacional estandarizado en 1988. `L` = letra, `N` = dígito.

| Tipo | Patrón | Fondo | Caracteres | Clase de vehículo |
|---|---|---|---|---|
| Particular (auto) | `LLLNNN` | **Amarillo** | Negro | carro |
| Público / comercial (auto) | `LLLNNN` | **Blanco** | Negro | carro |
| Oficial | `LLLNNN` (inicia en `O`) | **Verde** | Blanco | carro |
| Antiguo / clásico | `LLLNNN` | Blanco + franjas azules | Negro | carro |
| Diplomático | `LLLNNN` (inicia en `D`) | Blanco + franja azul | Negro | carro |
| Consular | `LLLNNN` (inicia en `C`) | Blanco + franja azul | Negro | carro |
| Moto (formato actual) | `LLLNNL` | **Amarillo** | Negro | moto |
| Moto (formato antiguo) | `LLLNN` | **Amarillo** | Negro | moto |
| Mototaxi / motocarro particular | `NNNLLL` | **Amarillo** | Negro | moto |
| Mototaxi / motocarro público | `NNNLLL` | **Blanco** | Negro | moto |
| Remolque | `RNNNNN` | **Verde** | Blanco | remolque |
| Temporal / importado | `TNNNN` | **Rojo** | Negro | carro |
| Policía Nacional | `NNNNNN` (se ve `NN-NNNN`) | Blanco | Verde | carro/moto |
| Fuerza Aérea | `FAC` + `NNNNNN` | Negro | Amarillo | carro |

Fuente: [Anexo:Matrículas automovilísticas de Colombia (Wikipedia)](https://es.wikipedia.org/wiki/Anexo:Matr%C3%ADculas_automovil%C3%ADsticas_de_Colombia),
[CarroYa — los 6 tipos de placas](https://www.carroya.com/noticias/guia-para-conductores/asi-puedes-identificar-los-6-tipos-de-placas-de-carros-que-circulan-en).

Las placas colombianas son **retrorreflectivas**: de noche con iluminación IR se leen
excelente, a menudo mejor que de día. Es un dato a favor del sistema, no en contra.

---

## 2. El problema central: el texto solo no basta

Mírese la tabla: **seis tipos distintos comparten el patrón `LLLNNN`**. Particular, público,
oficial, antiguo, diplomático y consular producen exactamente la misma cadena para el OCR.

```
"ABC123"  →  ¿carro particular?  ¿taxi?  ¿vehículo oficial?
             el OCR no puede saberlo. El color sí.
```

Peor: los prefijos `O`, `D` y `C` **no son exclusivos**. Un particular corriente puede tener
la placa `DAB123` sin ser diplomático. Cualquier regla del tipo "si empieza por D es
diplomático" produce falsos positivos.

**Conclusión de diseño:** la clasificación necesita señales independientes. El sistema usa
tres y las combina explícitamente.

---

## 3. Las tres señales

### Señal 1 — Patrón del texto (`plate_rules.patterns`)

Regex sobre el texto normalizado. Devuelve el conjunto de **candidatos** compatibles, no una
respuesta única.

```
"ABC123"  → [PARTICULAR_CAR, PUBLIC_CAR, OFFICIAL_CAR, ANTIQUE_CAR, DIPLOMATIC, CONSULAR]
"ABC12D"  → [MOTORCYCLE]                       ← inequívoco
"R12345"  → [TRAILER]                          ← inequívoco
"T1234"   → [TEMPORARY]                        ← inequívoco
"123ABC"  → [MOTOCARRO_PRIVATE, MOTOCARRO_PUBLIC]
```

Fuerza: barata, determinista, sin falsos negativos si el OCR acertó.
Debilidad: ambigua para el caso más común (`LLLNNN`), y totalmente dependiente de que el OCR
no se haya equivocado.

### Señal 2 — Color de fondo de la placa (`edge_agent.vision.plate_color`)

Se calcula sobre el recorte de la placa: se convierte a **HSV** y se toma la mediana del
matiz y la saturación de los píxeles del fondo (se descartan los píxeles oscuros, que son los
caracteres). HSV y no RGB porque separa el *color* (H) de la *iluminación* (V), y en la
portería la iluminación varía brutalmente entre el contraluz de mediodía y la noche.

```
amarillo (H≈25-35°, S alta)   → particular  o  moto  o  motocarro particular
blanco   (S baja, V alta)     → público     o  diplomático/consular/antiguo
verde    (H≈70-90°)           → oficial     o  remolque
rojo     (H≈0-10° o 170-180°) → temporal
```

Esta señal **resuelve la ambigüedad principal** (particular vs público), que es justamente la
que más importa operativamente en una universidad.

> ⚠️ Los rangos HSV están marcados `# CALIBRAR` en el código. Los valores anteriores son un
> punto de partida razonable, no una medición. Se ajustan con el script
> `scripts/calibrate_plate_color.py` sobre recortes reales de la portería.

### Señal 3 — Etiqueta del detector de objetos (Frigate)

Frigate ya clasifica el objeto que contiene la placa como `car`, `motorcycle`, `bus` o
`truck` (clases COCO). Es una señal **completamente independiente** del texto y del color:
viene de la forma del vehículo, no de la placa.

```
frigate label "motorcycle"  → clase esperada: moto
frigate label "car"/"truck"/"bus" → clase esperada: carro
```

### Señal 4 (auxiliar) — Geometría de la placa

La relación de aspecto del bounding box de la placa discrimina carro de moto: las placas de
carro son notoriamente más anchas que las de moto.

> ⚠️ **Sin calibrar.** No se han medido las relaciones de aspecto reales con la óptica que se
> va a usar, y dependen del ángulo de la cámara. Por eso esta señal está implementada pero
> **desactivada por defecto** (`ENABLE_GEOMETRY_SIGNAL = False`). Se activa cuando
> `scripts/calibrate_plate_geometry.py` haya corrido sobre datos reales.

---

## 4. Verificación cruzada: el corazón del módulo

El valor real no está en cada señal, sino en **contrastarlas**. La función
`plate_rules.classify.cross_check()` compara la clase que sugiere la placa con la clase que
ve la cámara y emite un veredicto:

| Patrón dice | Detector ve | Veredicto | Acción |
|---|---|---|---|
| moto | `motorcycle` | `CONFIRMED` | registrar con confianza alta |
| carro | `car`/`truck`/`bus` | `CONFIRMED` | registrar con confianza alta |
| moto | `car` | `CONFLICT` | **a cola de revisión** |
| carro | `motorcycle` | `CONFLICT` | **a cola de revisión** |
| desconocido (no matchea patrón) | cualquiera | `UNRECOGNIZED_PATTERN` | a cola de revisión |
| cualquiera | sin etiqueta | `UNVERIFIED` | registrar, confianza media |

**Por qué esto importa tanto:** un conflicto casi siempre significa que el **OCR se equivocó**.
Ejemplo real y frecuente: la moto `ABC12D` se lee como `ABC120` (`D`→`0`). El patrón resultante
`LLLNNN` dice "carro", pero la cámara ve una moto → conflicto → se detecta un error que de
otro modo habría entrado silenciosamente a la base de datos como un vehículo inexistente.

Es un **detector de errores gratuito**, construido sobre señales que ya se tenían. Y la cola
de conflictos alimenta directamente el active learning: son exactamente los casos difíciles
que más valen para reentrenar.

---

## 5. Corrección de OCR guiada por patrón

El OCR confunde sistemáticamente caracteres de forma parecida. Como se conoce la **máscara**
que debe cumplir cada posición (`LLLNNN`: tres letras y luego tres dígitos), se puede forzar
la coerción posición por posición.

```
letra → dígito        dígito → letra
  O,D,Q → 0             0 → O
  I,L   → 1             1 → I
  Z     → 2             2 → Z
  E     → 3             4 → A
  A     → 4             5 → S
  S     → 5             6 → G
  G     → 6             8 → B
  T     → 7
  B     → 8
```

Ejemplo: el OCR devuelve `A8C1Z3`. Contra la máscara `LLLNNN`:

```
posición 1: 'A' letra ✓
posición 2: '8' debe ser letra → coerción 8→B  ⇒ 'B'
posición 3: 'C' letra ✓
posición 4: '1' dígito ✓
posición 5: 'Z' debe ser dígito → coerción Z→2 ⇒ '2'
posición 6: '3' dígito ✓
resultado: ABC123, con corrections=2
```

Cuesta ~30 líneas de código y recupera lecturas que de otro modo se descartarían.

**Salvaguarda:** `MAX_COERCIONS` (por defecto 2). Si hay que corregir más de dos caracteres,
la lectura es demasiado dudosa y se manda a revisión en vez de "arreglarla". Sin este límite
el corrector inventaría placas plausibles pero falsas — un error mucho peor que no leer.

Además, cada corrección **baja la confianza** del resultado, lo que se propaga a la
agregación temporal del paso siguiente.

---

## 6. Agregación temporal (dónde se usa todo esto)

Un vehículo aparece en 20–40 frames. Cada frame produce una lectura con su confianza. En vez
de quedarse con la última:

```
track_id 42 → ["ABC123" 0.91, "ABC128" 0.62, "ABC123" 0.88,
               "A8C123" 0.71, "ABC123" 0.94, ...]
   ↓ normalizar cada una con plate_rules
   ↓ votación ponderada por confianza
   → "ABC123", votos 4/5, confianza agregada 0.93
```

Una precisión por frame del ~90% agregada sobre 30 frames sube a ~98-99%. Es el paso
individual que más precisión aporta en todo el pipeline y casi ningún tutorial lo implementa.

Frigate ya hace una versión de esto internamente (refina mientras el vehículo se mueve y se
queda con el resultado más confiado), pero el agente reaplica normalización y verificación
cruzada sobre el resultado final.

---

## 7. Cómo *debería* verse una placa para que esto funcione

Requisitos ópticos que condicionan la instalación en sitio:

| Parámetro | Valor objetivo | Por qué |
|---|---|---|
| Ancho de la placa en la imagen | **≥ 100 px** (mínimo absoluto ~70 px) | Debajo de eso el OCR degrada rápido. Frigate lo filtra con `min_area` (default 1000 px²). |
| Ángulo horizontal respecto al plano de la placa | **< 30°** | Más allá, la perspectiva deforma los caracteres |
| Ángulo vertical | **< 30°** | idem |
| Obturador (shutter) | **fijo, 1/500–1/1000 s** | El *motion blur* es el asesino nº1 del OCR. Más importante que los megapíxeles. |
| WDR / HDR | **≥ 120 dB** | En las fotos de referencia el cielo está quemado; sin WDR el vehículo entra en silueta |
| Altura de montaje | 1.5–2.5 m, apuntando ligeramente abajo | Saca el cielo del encuadre |
| Iluminación nocturna | IR | Las placas son retrorreflectivas |

**Motos:** en Colombia las motos llevan **solo placa trasera**. Una cámara de entrada que
mira de frente **no leerá motos**. Decisión pendiente para producción: cámara adicional
mirando de espaldas por carril, o aceptar que las motos solo se registran en un sentido.

---

## 8. Limitaciones conocidas y honestas

- **Placas de Policía (`NNNNNN`) y FAC** están en el catálogo pero son raras en el campus;
  no se han visto en datos reales y su regex no está validada.
- **Placas antiguas, diplomáticas y consulares** no se distinguen del público solo por color
  de fondo: llevan una franja azul vertical que el módulo actual **no detecta**. Se clasifican
  como `PUBLIC_CAR`. Aceptable para el caso de uso (una portería universitaria), pero es una
  simplificación consciente.
- Los rangos HSV y la geometría **no están calibrados con datos reales**. Todo lo marcado
  `# CALIBRAR` es un punto de partida documentado, no una medición.
- No hay ninguna métrica de precisión medida todavía. Se obtendrá con la evaluación de la
  Fase 0 sobre video real de la portería.
