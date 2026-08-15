# %% [markdown]
# # 03 — Preparación de datos: panel provincia-trimestre (2018–2026)
#
# **Proyecto:** ec-empleo-crimen — relación entre desempleo/subempleo y
# homicidios intencionales en Ecuador, nivel provincial (2018–2026).
# **Etapa CRISP-DM:** preparación de datos.
# **Fuentes (acceso 2026-08-14):** Ministerio del Interior (homicidios
# intencionales), INEC (proyecciones poblacionales Revisión 2024, ENEMDU).
# **Llave de unión:** código DPA de 2 dígitos del INEC (nunca nombres libres).
#
# Este notebook construye el panel `data/processed/panel_provincia_trimestre.csv`
# que usan los notebooks 04 (modelado) y 05 (evaluación).

# %%
# --- Entorno: asegura que la raíz del repositorio esté en sys.path ----------
import sys
import pathlib

# Salida UTF-8 en consola (evita errores de codificación con tildes/→ en Windows)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:  # pragma: no cover
    pass

try:
    RAIZ = pathlib.Path(__file__).resolve().parents[1]  # al ejecutar como .py
except NameError:
    RAIZ = None  # al ejecutar como notebook: __file__ no existe

if RAIZ is None or not (RAIZ / "src").exists():
    candidato = pathlib.Path.cwd()
    RAIZ = candidato if (candidato / "src").exists() else candidato.parent
sys.path.insert(0, str(RAIZ))
print("Raíz del repositorio:", RAIZ)

import pandas as pd
import numpy as np

from src import config, loaders, data_prep

# %%
# ### 1. Homicidios intencionales (Ministerio del Interior)
#
# Dos libros XLSX (hoja '1. Homicidios Intencionales'), concatenados:
# `2014_2025.xlsx` (39 822 víctimas) y `2026_enero_junio.xlsx` (4 154).
# Una fila = una víctima; "homicidio intencional" = todas las categorías de
# `tipo_muerte` (ASESINATO, HOMICIDIO, FEMICIDIO, SICARIATO).

homicidios = loaders.cargar_homicidios()
print("Dimensiones:", homicidios.shape)
print(homicidios[["fecha_infraccion", "dpa_provin", "provincia",
                  "tipo_muerte"]].head().to_string())
print("\nDesglose por tipo de muerte:")
print(homicidios["tipo_muerte"].value_counts().to_string())
print("\nAños cubiertos:", homicidios["fecha_infraccion"].dt.year.min(),
      "→", homicidios["fecha_infraccion"].dt.year.max())

# %%
# ### 2. Población provincial (Proyecciones INEC, Revisión 2024)
#
# CSV tidy `poblacion_provincial_1990_2035_tidy.csv` (24 provincias × 46 años,
# valores al 30 de junio). Es el denominador de las tasas por 100 000 hab.

poblacion = loaders.cargar_poblacion()
print("Dimensiones:", poblacion.shape)
print(poblacion[poblacion["anio"].isin([2018, 2022, 2026])].head(8).to_string())
print("\nRango de años:", poblacion["anio"].min(), "→", poblacion["anio"].max(),
      "| provincias:", poblacion["dpa_provin"].nunique())

# %%
# ### 3. ENEMDU — microdatos de personas (2024-II, INEC)
#
# Vía correcta para tasas PROVINCIALES: los tabulados XLSX de Mercado Laboral
# solo traen Nacional/Área/Dominios urbanos (verificado en fuentes.md). Los
# microdatos abiertos (CSV con `;` y decimales con coma, o SPSS .sav) traen
# `ciudad` (DPA de 6 dígitos), `condact` (condición de actividad) y `fexp`
# (factor de expansión). Provincia = `str(ciudad).zfill(6)[:2]`.
#
# `cargar_enemdu_microdatos` acepta una ruta o un periodo ("2024-II") y lo
# busca dentro de `data/raw/enemdu/`.

enemdu = loaders.cargar_enemdu_microdatos("2024-II")
print("Dimensiones:", enemdu.shape)
print(enemdu.head().to_string())
print("\nProvincias detectadas:", enemdu["provincia"].nunique(),
      "| Periodo(s):", sorted(enemdu["periodo"].dropna().unique()))

# %%
# ### 4. Limpieza y normalización DPA
#
# La fuente de homicidios trae `codigo_provincia` como int sin cero inicial
# (9 = Guayas, 17 = Pichincha) y nombres en MAYÚSCULAS con abreviaturas:
# **"STO DGO DE LOS TSÁCHILAS"** → se normaliza al nombre oficial
# "SANTO DOMINGO DE LOS TSÁCHILAS" (código DPA **23**). El `zfill(2)` restaura
# el cero inicial (07 = El Oro) para unir con población y geografía.

# Ejemplos de normalización de código → DPA de 2 dígitos
ejemplos = pd.DataFrame({"provincia": ["GUAYAS", "EL ORO", "PICHINCHA",
                                       "STO DGO DE LOS TSÁCHILAS",
                                       "SANTO DOMINGO DE LOS TSÁCHILAS",
                                       "MANABÍ"]})
ejemplos["dpa_provin"] = data_prep.normalizar_provincia(ejemplos, "provincia")
print(ejemplos.to_string())
print("\nCódigos en homicidios (muestra):",
      sorted(homicidios["dpa_provin"].dropna().unique())[:8], "...")
print("Códigos en población (muestra):",
      sorted(poblacion["dpa_provin"].dropna().unique())[:8], "...")

# Verificación cruzada: el nombre estandarizado coincide con el código
cruce = homicidios[["dpa_provin", "provincia"]].drop_duplicates()
tabla_nombre = cruce.groupby("dpa_provin")["provincia"].nunique()
print("\nNombres por código DPA (debe ser 1 en todos):",
      tabla_nombre.max(), "máximo")

# %%
# ### 5. Agregación trimestral de homicidios (2018 – 2026-Q2) y cruce con población
#
# Se cuentan víctimas por provincia-trimestre y se cruzan con la población
# proyectada del año correspondiente → `panel_homicidios.csv` con la tasa de
# homicidios por 100 000 habitantes (denominador fijo por provincia-año).

hom_trim = data_prep.agregar_homicidios(homicidios, frecuencia="trimestre",
                                        por_tipo=True)
print("Provincia-trimestre:", hom_trim.shape)
print(hom_trim.head().to_string())

# Serie anual nacional (control contra fuentes.md; las cifras oficiales
# incluyen las filas duplicadas que este pipeline elimina en el cargador,
# por eso algunos años quedan ligeramente por debajo; 2018 coincide: 996)
oficial = {2018: 996, 2019: 1189, 2020: 1371, 2021: 2495, 2022: 4886,
           2023: 8248, 2024: 7065, 2025: 9283, 2026: 4154}
anual = hom_trim.groupby("anio")["homicidios"].sum()
print("Total nacional anual 2018–2026 (panel tras eliminar duplicados):")
print(anual.to_string())
print("\nDiferencia vs cifra oficial (filas duplicadas eliminadas):")
print((anual - pd.Series(oficial)).to_string())

# Construcción del panel (guarda panel_homicidios.csv y
# panel_provincia_trimestre.csv en data/processed/)
panel_hom = data_prep.construir_panel(hom_trim, poblacion, enemdu=None)
print("\nPanel de homicidios:", panel_hom.shape)
print(panel_hom[panel_hom["dpa_provin"] == "09"].tail(4).to_string())

# %%
# ### 6. Tasas ENEMDU provinciales desde microdatos (2024-II)
#
# Definiciones oficiales (condact): PEA = {1..8}; Ocupados = {1..6};
# Desocupados = {7,8}; Empleo adecuado = {1}; Subempleo = {2,3}.
# Tasas = 100 × ponderado(fexp) / PEA. Validación nacional 2024-II:
# desempleo 3.48 %, subempleo 20.97 %, empleo adecuado 35.01 %
# (coincide con el boletín oficial del INEC).
#
# **Cómo ampliar a otros trimestres:** los microdatos siguen el patrón de URL
#   `https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/<AÑO>/<Mes-AAAA>/
#   2_BDD_DATOS_ABIERTOS_ENEMDU_<AÑO>_<TRIMESTRE>_TRIMESTRE_CSV.zip`
# (p. ej. 2024/Trimestre_II/...). Descargar con `loaders.descargar_archivo`,
# descomprimir en `data/raw/enemdu/` y volver a llamar
# `cargar_enemdu_microdatos("<AÑO>-<TRIM>")`; `tasas_enemdu_provincial` hará
# el resto y el panel se reconstruye con más trimestres (ver fuentes.md,
# sección ENEMDU, para 2023–2026 y mensuales 2020–2022).

tasas = data_prep.tasas_enemdu_provincial(enemdu)
print(tasas.round(2).to_string())

# Contraste nacional ponderado
tot = tasas[["PEA", "Desocupados", "Subempleo", "Empleo_adecuado"]].sum()
print("\nNacional 2024-II: desempleo {:.2f}% | subempleo {:.2f}% | "
      "empleo adecuado {:.2f}%".format(
      100 * tot["Desocupados"] / tot["PEA"],
      100 * tot["Subempleo"] / tot["PEA"],
      100 * tot["Empleo_adecuado"] / tot["PEA"]))

# Guarda las tasas provinciales para reproducibilidad
ruta_tasas = loaders.RUTA_PROCESSED / "tasas_enemdu_provincial.csv"
ruta_tasas.parent.mkdir(parents=True, exist_ok=True)
tasas.round(4).to_csv(ruta_tasas, index=False, encoding="utf-8-sig")
print("\nGuardado:", ruta_tasas)

# %%
# ### 7. Unión en panel provincia-periodo y tasa por 100 000
#
# Se unen los homicidios agregados + población + tasas ENEMDU (solo los
# trimestres disponibles) y se guarda el panel final.

panel = data_prep.construir_panel(hom_trim, poblacion, enemdu=tasas)
print("Panel provincia-trimestre:", panel.shape)
print("\nPrimeras filas:")
print(panel.head().to_string())
print("\nÚltimas filas (2026):")
print(panel[panel["periodo"] >= "2026-Q1"].head().to_string())

# %%
# ### 8. VERIFICACIÓN: shape, head y tabla de cobertura
#
# Cobertura del panel: 24 provincias × 34 trimestres (2018-Q1 … 2026-Q2).
# Las provincias sin homicidios en un trimestre se rellenan con 0 (panel
# balanceado). ENEMDU solo está presente en 2024-Q2 (24 provincias); el
# resto de trimestres tienen únicamente homicidios + población (las tasas
# laborales se amplían descargando más microdatos, ver celda 6).

print("Shape del panel:", panel.shape)
print("Provincias:", panel["dpa_provin"].nunique(),
      "| Trimestres:", panel["periodo"].nunique(),
      "| Rango:", panel["periodo"].min(), "→", panel["periodo"].max())

cobertura = (panel.groupby("periodo")
             .agg(provincias=("dpa_provin", "nunique"),
                  con_enemdu=("tasa_desempleo",
                              lambda s: int(s.notna().sum())),
                  solo_homicidios=("tasa_desempleo",
                                   lambda s: int(s.isna().sum())))
             .reset_index())
print("\nTabla de cobertura (primeras y últimas filas):")
print(pd.concat([cobertura.head(3), cobertura.tail(3)]).to_string())

n_enemdu = int(panel["tasa_desempleo"].notna().sum())
trim_completos = int((cobertura["con_enemdu"] == 24).sum())
print(f"\nResumen: {n_enemdu} filas provincia-trimestre CON tasas ENEMDU "
      f"({trim_completos} trimestre(s) completo(s): 2024-Q2) y "
      f"{int(panel['tasa_desempleo'].isna().sum())} solo con homicidios.")

# Controles finales
assert panel["dpa_provin"].nunique() == 24, "Deben ser 24 provincias"
esperado = int(homicidios["fecha_infraccion"].dt.year
               .between(config.ANIO_INICIO, config.ANIO_FIN).sum())
assert panel["homicidios"].sum() == esperado, \
    "El total de homicidios 2018–2026 debe conservarse tras la agregación"
print("\n✓ Verificación superada: 24 provincias y total de homicidios "
      "conservado en el panel.")

# %%
# ### 9. Decisiones de preparación y limitaciones
#
# **Decisiones:**
# - **Llave DPA de 2 dígitos** en todo el pipeline; los nombres de provincia
#   solo se usan para etiquetar. "STO DGO DE LOS TSÁCHILAS" → "SANTO DOMINGO
#   DE LOS TSÁCHILAS" (código 23).
# - **Homicidios**: se cuentan TODAS las categorías de `tipo_muerte`
#   (definición oficial de homicidio intencional); se eliminaron filas
#   duplicadas completas (~0.5 %) para evitar doble conteo. Desglose por tipo
#   disponible en columnas `homicidios_*` del panel de homicidios.
# - **Trimestre** = trimestre calendario ("AAAA-Tn"): ENEMDU-II (abril–junio)
#   = 2024-Q2. Rango del panel: 2018-Q1 … 2026-Q2 (2026 solo enero–junio,
#   último archivo publicado).
# - **Denominador**: proyecciones INEC Revisión 2024 (base Censo 2022),
#   población al 30 de junio, **fija por provincia-año** (no se interpola por
#   trimestre): la tasa por 100 000 es exacta a nivel anual y aproximada a
#   nivel trimestral.
# - **Galápagos (código 20)**: presente en población y en homicidios
#   2018–2025; ausente en 2026 (0 casos registrados en el archivo parcial).
#
# **Limitaciones honestas:**
# - **ENEMDU**: solo hay microdatos 2024-II en el repositorio; el resto de
#   trimestres del panel no tiene tasas laborales. El notebook documenta el
#   patrón de descarga (celda 6) para ampliar la cobertura. Los tabulados
#   XLSX no traen provincia (solo Nacional/Área/Dominios urbanos).
# - La **población proyectada** es una estimación (no un censo); la Revisión
#   2024 es la vigente a la fecha de acceso.
# - **Duplicados**: 187 (histórico) y 32 (2026) filas idénticas se eliminaron;
#   si representaran registros reales repetidos, el conteo estaría
#   ligeramente subestimado.
# - El panel es **no balanceado** en la dimensión laboral: la cobertura de
#   ENEMDU debe ampliarse antes de interpretar los modelos de panel (04).
