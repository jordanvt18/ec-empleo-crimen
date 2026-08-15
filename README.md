# ec-empleo-crimen

Análisis CRISP-DM de la relación entre **desempleo/subempleo** y **homicidios intencionales** en Ecuador a nivel provincial (2018–2026), con fuentes oficiales exclusivamente.

## Pregunta de investigación

¿Cómo evolucionó la criminalidad letal (homicidios intencionales por 100 000 habitantes) en las provincias de Ecuador entre 2018 y 2026, y qué asociación (no causal) guarda con el deterioro del mercado laboral (desempleo y subempleo por provincia), controlando por heterogeneidad geográfica y temporal?

## Estructura del repositorio

```
ec-empleo-crimen/
├── data/
│   ├── raw/            # Fuentes oficiales descargadas (ENEMDU, homicidios, población, geografía)
│   └── processed/      # Panel provincia-trimestre y datos intermedios
├── notebooks/
│   ├── 01_business_understanding.ipynb
│   ├── 02_data_understanding.ipynb
│   ├── 03_data_preparation.ipynb
│   ├── 04_modeling.ipynb
│   └── 05_evaluation.ipynb
├── src/                # Funciones reutilizables (config, loaders, data_prep, geoprocessing, panel_helpers)
├── reports/figures/    # Gráficos principales
├── app.py              # App Streamlit interactiva
├── requirements.txt
└── README.md
```

## Fuentes (todas descargadas el **2026-08-14**)

| Dato | Fuente oficial | URL | Notas |
|---|---|---|---|
| Homicidios intencionales (nivel incidente, 2014–2026) | Ministerio del Interior — DINASED, vía datos abiertos | https://datosabiertos.gob.ec/dataset/homicidios-intencionales | 39 822 filas 2014–2025 + 4 154 (ene–jun 2026); actualizado 15-jul-2026. API CKAN bloquea bots (documentado en notebook 02). |
| Desempleo, subempleo y empleo adecuado por provincia | INEC — ENEMDU (microdatos trimestrales) | https://www.ecuadorencifras.gob.ec/estadisticas-laborales-enemdu/ · microdatos: https://anda.inec.gob.ec | Tabulados oficiales no traen desagregación provincial; se usan microdatos (BDD) con factor de expansión. Repo inicial: 2024-II completo. |
| Población provincial (denominador de tasas) | INEC — Proyecciones poblacionales, revisión 2024 (base Censo 2022) | https://www.ecuadorencifras.gob.ec/proyecciones-poblacionales/ | `poblacion_provincial_1990_2035_tidy.csv`, años 1990–2035. |
| Límites provinciales (mapas) | IGM/CONALI — Organización Territorial Provincial 2025 | https://www.geoportaligm.gob.ec/portal/index.php/descargas/cartografia-de-libre-acceso/registro/ | Shapefile 24 provincias, CRS EPSG:32717 → reproyectado a EPSG:4326. |
| Contraste externo (no usado como fuente primaria) | OECO (Observatorio Ecuatoriano de Crimen Organizado, PADF) — boletín semestral S1-2025 | https://oeco.padf.org/boletin-semestral-de-homicidios-intencionales-en-ecuador-semestre-2025/ | 4 619 homicidios en S1-2025 (+47 % vs S1-2024), vs 4 659 del dataset oficial (Δ≈0,9 %). |

## Metodología (CRISP-DM)

1. **Comprensión del negocio** — definir la pregunta, las fuentes oficiales y los choques de política (decretos de "conflicto armado interno": D111 9-ene-2024, D218 7-abr-2024, D55 16-jul-2025, D424 18-jun-2026).
2. **Comprensión de los datos** — inspeccionar ENEMDU (microdatos y diccionario), homicidios (una fila por víctima), proyecciones poblacionales y shapefile CONALI; documentar limitaciones (tabulados sin provincia, API CKAN con 403).
3. **Preparación de datos** — normalizar provincias con **código DPA de 2 dígitos** como llave, agregar homicidios a provincia-trimestre, calcular tasas por 100 000 hab. y tasas laborales ponderadas con `fexp` (ENEMDU 2024-II validado contra el boletín oficial).
4. **Modelado** — panel con efectos fijos de provincia y periodo (statsmodels/linearmodels), diseño de eventos (event study) alrededor de los decretos de 2024, mapas coropléticos con geopandas/plotly.
5. **Evaluación** — robustez sin Guayas (44,2 % de los homicidios), placebo con pseudo-tratamiento en 2021-Q1, contraste externo con OECO (este notebook).

## Hallazgos principales

1. **Explosión de homicidios con aceleración desde 2021 y récord en 2025.** La serie nacional pasó de 996 víctimas (2018) a 9 283 (2025), con un salto de 2 495 (2021) → 8 248 (2023) y niveles altos sostenidos en 2024–2025; el primer semestre de 2026 suma 4 154. Ver `reports/figures/fig_homicidios_nacional.png`.

2. **El aumento es nacional, no un fenómeno de Guayas.** Guayas concentra 44,2 % de los homicidios 2018–2025, pero al re-estimar la serie sin Guayas el crecimiento interanual se mantiene en la misma dirección (ver `notebooks/05_evaluation.ipynb` y los mapas por provincia del notebook 04 en `reports/figures/`): el deterioro de seguridad se extendió a costa, Los Ríos, Manabí, El Oro y Esmeraldas.

3. **No hay "efecto" espurio en el placebo, y la ola precedió a los decretos de 2024.** El event study con un pseudo-tratamiento en 2021-Q1 no muestra respuesta inmediata (placebo plano en t≈0), mientras que el repunte tardío de la ventana placebo coincide con 2023-Q1, el inicio real de la escalada. El event study centrado en 2024-Q1 (decreto 111) confirma que la ola ya estaba en curso antes de los decretos: estos formalizaron la respuesta estatal (figura `reports/figures/fig_placebo_event_study.png`). El contraste externo con el boletín OECO S1-2025 (4 619 homicidios) coincide con el dataset oficial (4 659; Δ≈0,9 %, atribuible a cortes de fecha).

## Limitaciones

- **Cobertura ENEMDU parcial:** el repositorio inicial incluye microdatos provinciales de un solo trimestre (2024-II); el resto del periodo 2018–2026 requiere descarga (patrones documentados en el notebook 03) o acceso a ANDA. Por eso el panel laboral no permite estimar elasticidades de largo plazo.
- **No es un ejercicio de causalidad:** los efectos fijos no eliminan variables omitidas (inversión en seguridad, presencia de grupos armados, migración, informalidad, demanda de drogas).
- **Datos administrativos:** los homicidios están "sujetos a variaciones" según el propio metadato oficial; no incluyen otros delitos ni muertes no clasificadas; Galápagos no reporta homicidios en 2026.
- **Población proyectada:** las tasas por 100 000 usan proyecciones INEC (revisión 2024, base Censo 2022), no conteos censales puntuales.

## Cómo ejecutar

```bash
# 1. Entorno virtual e instalación
python -m venv .venv
# Windows: .venv\Scripts\activate · Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 2. Notebooks (de principio a fin)
jupyter notebook notebooks/01_business_understanding.ipynb
# o ejecución completa sin abrir el navegador:
jupyter nbconvert --to notebook --execute notebooks/01_business_understanding.ipynb --output executed_01.ipynb

# 3. App interactiva
streamlit run app.py
```

Los notebooks están escritos como `.py` estilo jupytext en `notebook_sources/`; el conversor del repo (`tools/py_to_ipynb.py`) genera los `.ipynb` del directorio `notebooks/`.

## Cómo publicar en GitHub

Este repositorio ya está publicado en:

```bash
git remote add origin https://github.com/jordanvt18/ec-empleo-crimen.git
git branch -M main
git push -u origin main
```

Para clonarlo en otra máquina:

```bash
git clone https://github.com/jordanvt18/ec-empleo-crimen.git
```

> El repositorio incluye `.gitignore` para no subir geodatos pesados (>50 MB) ni archivos temporales; los datasets pequeños (homicidios agregados, población, panel) sí se versionan.

## Licencia y contacto

- Datos: propiedad de sus fuentes oficiales (INEC, Ministerio del Interior, IGM/CONALI); uso académico/de divulgación citando la fuente.
- Código: uso libre con atribución.
- Contacto: abrir un issue en el repositorio.
