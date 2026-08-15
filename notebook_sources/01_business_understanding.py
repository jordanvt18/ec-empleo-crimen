# %% [markdown]
# # Notebook 01 — Comprensión del negocio (Business Understanding)
#
# **Proyecto:** ec-empleo-crimen — Relación entre desempleo/subempleo y homicidios intencionales en Ecuador (nivel provincial, 2018–2026).
# **Metodología:** CRISP-DM (fase 1 de 5).
# **Fecha de acceso a las fuentes:** 2026-08-14.
# **Fuentes oficiales:** INEC (ENEMDU y proyecciones poblacionales), Ministerio del Interior — Dirección de Estadística y Economía de la Seguridad (homicidios intencionales), IGM/CONALI (límites provinciales).
#
# Este notebook documenta **por qué** hacemos el proyecto, **qué** sabemos del contexto y **cómo** lo abordaremos. No carga datos todavía: eso es tarea del notebook 02 (Data Understanding).

# %% [markdown]
# ## 1. Pregunta de investigación
#
# > **¿Existe una asociación entre el deterioro del mercado laboral (desempleo y subempleo) y la tasa de homicidios intencionales en las provincias del Ecuador entre 2018 y 2026, una vez controlada la heterogeneidad no observada entre provincias y periodos?**
#
# Preguntas secundarias:
#
# 1. ¿Cómo evolucionaron ambas variables a nivel nacional y provincial en 2018–2026?
# 2. ¿La concentración geográfica de los homicidios (Guayas concentra el 44,2 % del total 2018–2025) se corresponde con un patrón laboral particular?
# 3. ¿Cambió la trayectoria de los homicidios después de los decretos que declararon el conflicto armado interno (2024–2026)?
#
# El análisis es **descriptivo y correlacional con control de efectos fijos**, no un ejercicio de causalidad ingenua (ver sección 8).

# %% [markdown]
# ## 2. Contexto: choques de política (decretos del "conflicto armado interno")
#
# Ecuador pasó de 996 homicidios intencionales en 2018 a 9 283 en 2025 (fuente: Ministerio del Interior, dataset oficial). En ese período el país declaró formalmente un "conflicto armado interno" en cuatro hitos normativos, usados en este proyecto como **choques de política** para el diseño de eventos:
#
# | Decreto | Fecha | Contenido verificado | Fuente |
# |---|---|---|---|
# | **111** | 9 de enero de 2024 | Reconocimiento del conflicto armado interno y movilización de las Fuerzas Armadas. | [lexis.com.ec](https://www.lexis.com.ec/noticias/decreto-ejecutivo-reconocimiento-de-conflicto-armado-interno) · [comunicacion.gob.ec](https://www.comunicacion.gob.ec/decreto-ejecutivo-n-111/) · [CNN en español](https://cnnespanol.cnn.com/2024/01/10/que-es-conflicto-armado-interno-noboa-ecuador-orix) |
# | **218** | 7 de abril de 2024 | Documento oficial No. 218 (Noboa) relacionado con el marco del conflicto armado interno. | [esacc.corteconstitucional.gob.ec](https://esacc.corteconstitucional.gob.ec) (expediente No. 218) — contenido puntual *no verificado en detalle* |
# | **55** | 16 de julio de 2025 | Persistencia del conflicto armado interno; actualización de información del CNI sobre grupos armados organizados (GAO). | [lexis.com.ec](https://www.lexis.com.ec/noticias/decreto-ejecutivo-55-persistencia-de-conflicto-armado-interno-a-cargo-de-grupos-armados-organizados) · [primicias.ec](https://www.primicias.ec/politica/daniel-noboa-decreto-conflicto-armado-interno-ley-solidaridad-ecuador-100797/) · [lahora.com.ec](https://www.lahora.com.ec/seguridad/Daniel-Noboa-emite-decreto-para-reconocer-la-persistencia-de-un-conflicto-armado-interno-en-Ecuador-20250716-0033.html) |
# | **424** | 18 de junio de 2026 | Oficializa/reglamenta el reconocimiento del conflicto armado interno (procedimientos, identificación de GAO). | teleSUR + bnperiodismo — *fecha según prensa; verificar en el Registro Oficial* |
#
# **Uso en el proyecto:** estos decretos delimitan los periodos "antes/después" del evento en el diseño de eventos y control sintético (notebook 04), comparando la trayectoria de homicidios entre provincias con distinto deterioro previo del mercado laboral.

# %% [markdown]
# ## 3. Marco teórico breve
#
# El vínculo entre condiciones económicas y crimen tiene una larga tradición en economía:
#
# - **Becker, G. (1968). "Crime and Punishment: An Economic Approach", *Journal of Political Economy* 76(2).** Modelo de elección racional: el individuo decide participar en actividades ilegales comparando beneficios esperados, probabilidad de castigo y costo de oportunidad (incluido el ingreso legal). [DOI: 10.1086/259394](https://www.journals.uchicago.edu/doi/10.1086/259394)
# - **Ehrlich, I. (1973). "Participation in Illegitimate Activities: A Theoretical and Empirical Investigation", *JPE* 81(3).** Extiende a Becker con evidencia empírica; el desempleo y la desigualdad de ingresos aparecen como determinantes del crimen contra la propiedad y, en menor medida, del violento. [DOI: 10.1086/260058](https://www.journals.uchicago.edu/doi/10.1086/260058)
# - **BID (2017). "Los costos del crimen y la violencia: ampliación y actualización de las estimaciones para América Latina y el Caribe".** Documenta que América Latina es la región más violenta del mundo y cuantifica sus costos económicos (≈3,5 % del PIB regional), lo que motiva estudiar el crimen como problema económico y de desarrollo. [publications.iadb.org](https://publications.iadb.org/es/los-costos-del-crimen-y-la-violencia-ampliacion-y-actualizacion-de-las-estimaciones-para-america)
# - **UNODC. *Global Study on Homicide*.** Referencia internacional para definir, medir y comparar homicidios intencionales entre países (tasas por 100 000 habitantes). [unodc.org](https://www.unodc.org/unodc/en/data-and-analysis/global-study-on-homicide.html)
#
# **Lectura para este proyecto:** el desempleo y el subempleo reducen el costo de oportunidad del crimen (canal de Becker-Ehrlich), pero el homicidio en Ecuador 2021–2026 está fuertemente asociado a la violencia organizada (sicariato, GAO), que responde a otras variables (presencia de grupos armados, disputas territoriales, política de seguridad). Por eso el marco teórico informa las hipótesis pero **no** autoriza interpretaciones causales directas.

# %% [markdown]
# ## 4. Definiciones operativas (INEC y Ministerio del Interior)
#
# ### 4.1 Mercado laboral — ENEMDU (INEC)
#
# La Encuesta Nacional de Empleo, Desempleo y Subempleo (ENEMDU) clasifica a la población en edad de trabajar mediante la variable `condact` (condición de actividad) de la base de microdatos de personas:
#
# | Código `condact` | Categoría | Uso |
# |---|---|---|
# | 0 | Menores de 15 años | Excluida |
# | 1 | Empleo adecuado/pleno | Empleo adecuado |
# | 2 | Subempleo por insuficiencia de tiempo | Subempleo |
# | 3 | Subempleo por insuficiencia de ingresos | Subempleo |
# | 4 | Otro empleo no pleno | Ocupados |
# | 5 | Empleo no remunerado | Ocupados |
# | 6 | Empleo no clasificado | Ocupados |
# | 7 | Desempleo abierto | Desocupados |
# | 8 | Desempleo oculto | Desocupados |
# | 9 | Población económicamente inactiva | Excluida |
#
# **Definiciones de tasas** (todas ponderadas por el factor de expansión `fexp`):
#
# - **PEA** (población económicamente activa) = `condact` ∈ {1,…,8}.
# - **Ocupados** = {1,…,6}; **Desocupados** = {7, 8}.
# - **Tasa de desempleo** = 100 × desocupados / PEA.
# - **Tasa de subempleo** = 100 × subempleo ({2, 3}) / PEA.
# - **Tasa de empleo adecuado** = 100 × empleo adecuado ({1}) / PEA.
#
# Las tasas se calculan por provincia usando el código DPA de 6 dígitos de la variable `ciudad` (provincia = `str(ciudad).zfill(6)[:2]`).
#
# ### 4.2 Homicidio intencional — Ministerio del Interior / DINASED
#
# La operación estadística "Homicidios Intencionales" de la Dirección de Estadística y Economía de la Seguridad (Ministerio del Interior) registra **una fila por víctima** y clasifica cada caso en cuatro categorías (`tipo_muerte`):
#
# - **ASESINATO** (Art. 140 COIP), **HOMICIDIO** (Art. 144 COIP), **FEMICIDIO** (Art. 141 COIP) y **SICARIATO**.
#
# Los "homicidios intencionales" del proyecto = **todas** las filas (suma de las cuatro categorías), siguiendo el conteo oficial del dataset. El diccionario de datos (`diccionario_2025.xlsx`) referencia la operación `MDI_HomicidiosIntencionales_PM_2025` con esas definiciones legales del COIP (2014).

# %% [markdown]
# ## 5. Hipótesis
#
# - **H1 (asociación laboral):** las provincias con mayor desempleo y subempleo tienden a presentar mayores tasas de homicidios, controlando por efectos fijos de provincia y periodo (canal de costo de oportunidad, Becker–Ehrlich).
# - **H2 (escala y concentración):** la asociación está dominada por pocas provincias (Guayas ≈ 44,2 % del total nacional 2018–2025), por lo que se probará la robustez excluyendo Guayas.
# - **H3 (choque de política):** tras los decretos del conflicto armado interno (ene-2024 en adelante) la trayectoria de homicidios se aceleró de forma heterogénea entre provincias; el deterioro laboral previo modula esa aceleración.
#
# Todas las hipótesis son **descriptivas/correlacionales** con controles de efectos fijos; la causalidad estricta queda fuera del alcance.

# %% [markdown]
# ## 6. Fases CRISP-DM aplicadas a este proyecto
#
# | Fase CRISP-DM | Entregable | Notebook |
# |---|---|---|
# | 1. Comprensión del negocio | Pregunta, contexto, marco teórico, hipótesis, criterios de éxito | **01 (este)** |
# | 2. Comprensión de los datos | Carga, perfilado y calidad de las 4 fuentes; figura exploratoria | 02 |
# | 3. Preparación de datos | Normalización DPA, agregación provincia-periodo, panel con tasas por 100 000 | 03 |
# | 4. Modelado | Series + mapas, efectos fijos (statsmodels/linearmodels), event study y control sintético con los decretos 111/218/55/424 | 04 |
# | 5. Evaluación | Robustez sin Guayas, contraste con OECO, limitaciones honestas | 05 |
#
# **Criterio de éxito:** entregar un panel provincia-periodo reproducible y un análisis que responda a la pregunta con controles de heterogeneidad, documentando explícitamente qué NO se puede concluir.

# %% [markdown]
# ## 7. Limitaciones éticas e interpretativas
#
# 1. **No causalidad ingenua:** una correlación (incluso con efectos fijos) no demuestra que el desempleo *cause* homicidios. La violencia organizada responde a dinámicas propias.
# 2. **Variables omitidas:** inversión en seguridad, presencia/fortaleza de grupos armados (GAO), migración, informalidad, narcotráfico y capacidad institucional local pueden confundir la relación. Se dejan explícitas para el notebook 04.
# 3. **Calidad del registro:** el propio metadato del Ministerio del Interior advierte que la cifra "está sujeta a variaciones"; hay 187 filas duplicadas en el histórico (0,47 %) y 295 nulos en `edad`. En 2026 no hay filas de Galápagos (0 casos o registro pendiente).
# 4. **Ética del uso:** los datos son agregados a nivel provincial, lo que evita riesgos de reidentificación de víctimas; no se publican microdatos individuales. El análisis no debe usarse para estigmatizar territorios ni comunidades.
# 5. **Honestidad de cobertura laboral:** los microdatos ENEMDU del repo cubren el trimestre 2024-II; los demás periodos se documentan y descargan en fases posteriores, advirtiendo si faltan trimestres.

# %% [markdown]
# ## 8. Entorno y versiones
#
# Cargamos las librerías del proyecto y verificamos versiones. Nada de esto descarga datos; solo confirma el entorno reproducible del `requirements.txt`.

# %%
# -*- coding: utf-8 -*-
"""Entorno: importación de librerías y verificación de versiones."""

import platform
import sys

import matplotlib
import numpy
import openpyxl
import pandas
import requests

print(f"Python: {platform.python_version()} ({platform.system()})")
print(f"pandas: {pandas.__version__}")
print(f"numpy: {numpy.__version__}")
print(f"matplotlib: {matplotlib.__version__}")
print(f"openpyxl: {openpyxl.__version__}")
print(f"requests: {requests.__version__}")

# Librerías opcionales (requeridas en fases posteriores): se reportan si están.
try:
    import pyreadstat
    print(f"pyreadstat: {pyreadstat.__version__}")
except ImportError:
    print("pyreadstat: NO instalado (necesario para leer microdatos ENEMDU .sav)")

try:
    import geopandas
    print(f"geopandas: {geopandas.__version__}")
except ImportError:
    print("geopandas: NO instalado (necesario para mapas)")

try:
    import statsmodels
    print(f"statsmodels: {statsmodels.__version__}")
except ImportError:
    print("statsmodels: NO instalado (necesario para efectos fijos)")

try:
    import linearmodels
    print(f"linearmodels: {linearmodels.__version__}")
except ImportError:
    print("linearmodels: NO instalado (necesario para panel FE)")

print("\nEntorno listo. Siguiente paso: Notebook 02 — Data Understanding.")
