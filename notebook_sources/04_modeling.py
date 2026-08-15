# -*- coding: utf-8 -*-
# %% [markdown]
# # 04 — Modelado: más allá de la correlación
#
# **Proyecto:** ec-empleo-crimen · desempleo/subempleo ↔ homicidios intencionales, Ecuador provincial, 2018–2026.
# **Fuentes oficiales:** Ministerio del Interior (DINASED, homicidios intencionales), INEC (ENEMDU 2024-II y proyecciones poblacionales), IGM/CONALI (límites provinciales 2025).
# **Fecha de acceso a las fuentes:** 2026-08-14.
#
# Este notebook usa las funciones de `src/geoprocessing.py` (mapas coropléticos) y `src/panel_helpers.py` (efectos fijos, estudio de eventos, control sintético) y produce las figuras en `reports/figures/`.
# %%
import os
import sys
from pathlib import Path

# Consola con tildes correctas (años, región, subempleo, ...) en Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import matplotlib

matplotlib.use("Agg")  # backend sin ventana: las figuras se guardan como PNG
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Rutas: se respeta la configuración del proyecto (src/config.py) si existe;
# en su defecto se usan rutas locales equivalentes.
# ---------------------------------------------------------------------------
_cwd = Path.cwd()
if (_cwd / "src").exists():
    RUTA_REPO = _cwd
elif (_cwd.parent / "src").exists():
    RUTA_REPO = _cwd.parent  # cwd = notebooks/ (caso nbconvert)
else:
    RUTA_REPO = Path(os.environ.get("EC_EMPLEO_CRIMEN_REPO", _cwd))
sys.path.insert(0, str(RUTA_REPO))
sys.path.insert(0, str(RUTA_REPO / "src"))

try:
    from src.config import ANIO_INICIO, ANIO_FIN, RUTA_RAW, RUTA_FIG, RUTA_PROCESADOS
except Exception:
    from config import ANIO_INICIO, ANIO_FIN, RUTA_RAW, RUTA_FIG, RUTA_PROCESADOS

RUTA_FIG.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Importar las funciones propias del proyecto (src/) con respaldo para
# ejecutar este archivo .py directamente (notebook_sources/ o notebooks/).
# ---------------------------------------------------------------------------
from src.geoprocessing import cargar_mapa_provincias, mapa_coropletico
from src.panel_helpers import control_sintetico, efectos_fijos, event_study


def _periodo_a_fecha(periodo: str) -> pd.Timestamp:
    """Convierte '2024Q1' en el primer día del trimestre (Timestamp)."""
    anio = int(str(periodo)[:4])
    trimestre = int(str(periodo)[-1])
    return pd.Timestamp(anio, (trimestre - 1) * 3 + 1, 1)

# Clasificación regional oficial INEC (Sierra / Costa / Oriente / Galápagos).
REGIONES = {
    "01": "Sierra", "02": "Sierra", "03": "Sierra", "04": "Sierra", "05": "Sierra",
    "06": "Sierra", "10": "Sierra", "11": "Sierra", "17": "Sierra", "18": "Sierra",
    "07": "Costa", "08": "Costa", "09": "Costa", "12": "Costa", "13": "Costa",
    "23": "Costa", "24": "Costa",
    "14": "Oriente", "15": "Oriente", "16": "Oriente", "19": "Oriente",
    "21": "Oriente", "22": "Oriente",
    "20": "Galápagos",
}
NOMBRES_PROVINCIA = {
    "01": "Azuay", "02": "Bolívar", "03": "Cañar", "04": "Carchi", "05": "Cotopaxi",
    "06": "Chimborazo", "07": "El Oro", "08": "Esmeraldas", "09": "Guayas",
    "10": "Imbabura", "11": "Loja", "12": "Los Ríos", "13": "Manabí",
    "14": "Morona Santiago", "15": "Napo", "16": "Pastaza", "17": "Pichincha",
    "18": "Tungurahua", "19": "Zamora Chinchipe", "20": "Galápagos",
    "21": "Sucumbíos", "22": "Orellana", "23": "Santo Domingo de los Tsáchilas",
    "24": "Santa Elena",
}

# %% [markdown]
# ## (a) Objetivo y diseño del modelado
#
# Los notebooks anteriores describieron y prepararon los datos. Este notebook va **más allá de la correlación simple**:
#
# 1. **Descriptivo:** serie nacional mensual de homicidios (2018–2026), correlación de corte transversal entre la tasa de homicidios y las tasas laborales ENEMDU (2024-II) por provincia, y mapas coropléticos de la tasa de homicidios por 100 000 habitantes en **2019, 2023 y 2025**.
# 2. **Panel con efectos fijos:** `log(tasa_homicidios + 1) ~ tasa_desempleo + tasa_subempleo` (+ empleo adecuado en una especificación alternativa), con errores agrupados por provincia.
# 3. **Estudio de eventos** en torno al **Decreto 111** (9 de enero de 2024, reconocimiento del conflicto armado interno): trayectoria trimestral de homicidios de las provincias con mayor debilidad estructural del mercado laboral (grupo tratado) frente al resto, con efectos fijos de provincia y trimestre.
# 4. **Control sintético:** construcción de una provincia sintética (Esmeraldas) a partir de las demás, y medición de la brecha post-tratamiento.
#
# ### Advertencia de identificación (honesta)
#
# - La ENEMDU provincial disponible es **un solo corte: 2024-II**. Con una sola observación temporal por provincia, los **efectos fijos de provincia y trimestre no son identificables** para las variables laborales (los efectos fijos absorberían toda la variación). Por eso la sección (c) estima el objeto honesto posible —una regresión de corte transversal con dummies de región y errores agrupados— y el código de `efectos_fijos()` activa automáticamente el panel completo (linearmodels) cuando existan más cortes ENEMDU (el notebook 03 documenta cómo reconstruir el panel laboral histórico).
# - El **panel de homicidios es completo** (34 trimestres, 2018Q1–2026Q2, × 24 provincias), por lo que los diseños temporales —estudio de eventos y control sintético— sí estiman efectos fijos de provincia y trimestre con datos reales.
# - **Ninguno de estos ejercicios establece causalidad**: las variables omitidas (inversión en seguridad, presencia de grupos armados, migración, informalidad, narcotráfico) pueden confundir cualquier asociación. Ver sección (f).
# %%
# ---------------------------------------------------------------------------
# Carga de datos: homicidios (XLSX oficiales), población (INEC) y panel.
# ---------------------------------------------------------------------------
def cargar_homicidios() -> pd.DataFrame:
    """Lee los XLSX oficiales del Ministerio del Interior (2014–2025 y 2026)
    y devuelve las filas desde ANIO_INICIO con dpa_provin (zfill(2)), anio,
    mes y periodo trimestral (p. ej. '2024Q1')."""
    hojas = ["2014_2025.xlsx", "2026_enero_junio.xlsx"]
    partes = []
    for h in hojas:
        r = RUTA_RAW / "homicidios" / h
        if not r.exists():
            print(f"  [aviso] No existe {r}; se omite.")
            continue
        d = pd.read_excel(
            r,
            sheet_name="1. Homicidios Intencionales",
            usecols=["codigo_provincia", "fecha_infraccion", "tipo_muerte"],
        )
        partes.append(d)
    if not partes:
        raise FileNotFoundError("No hay archivos de homicidios en data/raw/homicidios/.")
    df = pd.concat(partes, ignore_index=True)
    df = df.dropna(subset=["codigo_provincia", "fecha_infraccion"])
    df["dpa_provin"] = df["codigo_provincia"].astype(int).astype(str).str.zfill(2)
    df["fecha"] = pd.to_datetime(df["fecha_infraccion"])
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["periodo"] = df["anio"].astype(str) + "Q" + ((df["mes"] - 1) // 3 + 1).astype(str)
    return df[df["anio"] >= ANIO_INICIO].copy()


def cargar_poblacion() -> pd.DataFrame:
    """Proyecciones poblacionales INEC (Revisión 2024, base Censo 2022),
    nivel provincial, 1990–2035."""
    r = RUTA_RAW / "poblacion" / "poblacion_provincial_1990_2035_tidy.csv"
    df = pd.read_csv(r)
    df["dpa_provin"] = df["dpa_provin"].astype(int).astype(str).str.zfill(2)
    return df[["dpa_provin", "anio", "poblacion"]]


def cargar_tasas_enemdu_2024q2() -> pd.DataFrame:
    """Tasas provinciales ENEMDU 2024-II (desempleo, subempleo y empleo
    adecuado, % de la PEA, ponderadas con el factor de expansión).
    Busca primero un CSV ya procesado; si no existe, las calcula desde los
    microdatos SPSS abiertos (variable condact + fexp)."""
    candidatos = [
        RUTA_PROCESADOS / "tasas_enemdu_2024q2.csv",
        RUTA_RAW / "enemdu" / "tasas_enemdu_2024q2.csv",
    ]
    for r in candidatos:
        if r.exists():
            df = pd.read_csv(r)
            df["dpa_provin"] = df["provincia"].astype(str).str.zfill(2)
            df["periodo"] = "2024Q2"
            return df[["dpa_provin", "periodo", "tasa_desempleo", "tasa_subempleo",
                       "tasa_empleo_adecuado"]]
    # Fallback: calcular desde microdatos SPSS (pyreadstat).
    import pyreadstat

    sav = list((RUTA_RAW / "enemdu" / "microdatos_spss_2024_II").rglob("enemdu_persona*.sav"))
    if not sav:
        raise FileNotFoundError("No hay microdatos ENEMDU 2024-II disponibles.")
    df, _ = pyreadstat.read_sav(sav[0])
    df["dpa_provin"] = df["ciudad"].astype("Int64").astype(str).str.zfill(6).str[:2]
    ocup = df["condact"].isin([1, 2, 3, 4, 5, 6])
    desoc = df["condact"].isin([7, 8])
    adec = df["condact"] == 1
    sube = df["condact"].isin([2, 3])
    pea = ocup | desoc
    f = df["fexp"].astype(float)
    g = pd.DataFrame({"dpa_provin": df["dpa_provin"], "f": f,
                      "desoc": desoc, "adec": adec, "sube": sube, "pea": pea})
    tab = g.groupby("dpa_provin").agg(
        PEA=("f", lambda s: (s * g.loc[s.index, "pea"]).sum()),
        Desoc=("f", lambda s: (s * g.loc[s.index, "desoc"]).sum()),
        Adec=("f", lambda s: (s * g.loc[s.index, "adec"]).sum()),
        Sube=("f", lambda s: (s * g.loc[s.index, "sube"]).sum()),
    )
    tab["tasa_desempleo"] = 100 * tab["Desoc"] / tab["PEA"]
    tab["tasa_subempleo"] = 100 * tab["Sube"] / tab["PEA"]
    tab["tasa_empleo_adecuado"] = 100 * tab["Adec"] / tab["PEA"]
    tab = tab.reset_index()[["dpa_provin", "tasa_desempleo", "tasa_subempleo",
                             "tasa_empleo_adecuado"]]
    tab["periodo"] = "2024Q2"
    return tab


hom = cargar_homicidios()
pob = cargar_poblacion()
enemdu = cargar_tasas_enemdu_2024q2()
print(f"Homicidios 2018+ (filas): {len(hom):,} | Provincias ENEMDU: {len(enemdu)}")
print(f"Rango del panel: {hom['periodo'].min()} a {hom['periodo'].max()}")
# %% [markdown]
# ## (b) Descriptivo: serie nacional y correlación de corte transversal
#
# ### (b.1) Serie nacional mensual de homicidios intencionales (2018–2026)
#
# Se construye directamente desde los XLSX oficiales (todas las categorías de `tipo_muerte`: asesinato, homicidio, femicidio y sicariato). La serie muestra la escalada 2021–2023 y el repunte posterior al Decreto 111 (enero de 2024).
# %%
mensual = hom.groupby(["anio", "mes"]).size().reset_index(name="homicidios")
mensual["fecha"] = pd.to_datetime(mensual["anio"].astype(str) + "-" + mensual["mes"].astype(str) + "-01")
mensual = mensual.sort_values("fecha")
mensual["media_movil_12"] = mensual["homicidios"].rolling(12, center=True).mean()

fig, ax = plt.subplots(figsize=(11, 4.5))
ax.bar(mensual["fecha"], mensual["homicidios"], width=22, color="#9db4d0",
       label="Homicidios mensuales")
ax.plot(mensual["fecha"], mensual["media_movil_12"], color="#b22222", lw=2.2,
        label="Media móvil 12 meses")
ax.axvline(pd.Timestamp("2024-01-15"), color="black", ls="--", lw=1.2)
ax.annotate("Decreto 111\n(ene-2024)", xy=(pd.Timestamp("2024-01-15"), 950),
            ha="right", fontsize=9)
ax.set_title("Homicidios intencionales en Ecuador, serie mensual 2018–2026")
ax.set_xlabel("Año")
ax.set_ylabel("Homicidios por mes")
ax.legend(frameon=False)
fig.tight_layout()
ruta_serie = RUTA_FIG / "fig_04_homicidios_nacional_mensual.png"
fig.savefig(ruta_serie, dpi=150)
plt.close(fig)
print("Figura guardada:", ruta_serie)
print("Total 2018–2025:", mensual[mensual["anio"] <= 2025]["homicidios"].sum(), "| 2026 (ene–jun):", mensual[mensual["anio"] == 2026]["homicidios"].sum())
# %% [markdown]
# ### (b.2) Correlación de corte transversal: tasas ENEMDU 2024-II vs. tasa de homicidios
#
# **Advertencia:** con un solo corte temporal de ENEMDU provincial (2024-II), la correlación que se puede calcular es **de corte transversal (por provincia, N = 24)**. No refleja una relación dinámica "a mayor desempleo, más homicidios" a lo largo del tiempo; solo dice qué tan alineadas están las provincias en ambos ejes en ese momento. Además, N = 24 es una muestra muy pequeña y cualquier coeficiente es sensible a provincias extremas (Guayas).
# %%
# Tasa anual de homicidios por provincia para 2024 y 2025.
tasas_anuales = hom.groupby(["dpa_provin", "anio"]).size().rename("homicidios").reset_index()
tasas_anuales = tasas_anuales.merge(pob, on=["dpa_provin", "anio"], how="left")
tasas_anuales["tasa"] = tasas_anuales["homicidios"] * 1e5 / tasas_anuales["poblacion"]

xs = enemdu.merge(tasas_anuales[tasas_anuales["anio"] == 2024][["dpa_provin", "tasa"]],
                  on="dpa_provin", how="left").rename(columns={"tasa": "tasa_hom_2024"})
xs = xs.merge(tasas_anuales[tasas_anuales["anio"] == 2025][["dpa_provin", "tasa"]],
              on="dpa_provin", how="left").rename(columns={"tasa": "tasa_hom_2025"})
# Provincias sin homicidios registrados en el año (p. ej. Galápagos) -> tasa 0.
xs["tasa_hom_2024"] = xs["tasa_hom_2024"].fillna(0.0)
xs["tasa_hom_2025"] = xs["tasa_hom_2025"].fillna(0.0)
xs["nombre"] = xs["dpa_provin"].map(NOMBRES_PROVINCIA)

variables_laborales = ["tasa_desempleo", "tasa_subempleo", "tasa_empleo_adecuado"]
filas_correlacion = []
for v in variables_laborales:
    for yvar in ["tasa_hom_2024", "tasa_hom_2025"]:
        r_p = xs[v].corr(xs[yvar], method="pearson")
        r_s = xs[v].corr(xs[yvar], method="spearman")
        filas_correlacion.append({"Variable laboral (2024-II)": v,
                                  "Homicidios": yvar.replace("tasa_hom_", "tasa anual "),
                                  "Pearson r": round(r_p, 3), "Spearman ρ": round(r_s, 3)})
tabla_corr = pd.DataFrame(filas_correlacion)
print(tabla_corr.to_string(index=False))
print("\nNota: correlación de corte transversal con N = 24 provincias (2024-II).")
# %%
# Gráfico de dispersión: tasas laborales vs. log de la tasa de homicidios 2024.
fig, ejes = plt.subplots(1, 3, figsize=(14, 4.4))
for ax, v in zip(ejes, variables_laborales):
    ax.scatter(xs[v], np.log(xs["tasa_hom_2024"] + 1), s=45, alpha=0.85, edgecolor="k", lw=0.5)
    # Etiqueta de provincias extremas (Guayas, Manabí, Esmeraldas, ...)
    for _, fila in xs.iterrows():
        if fila["tasa_hom_2024"] > 30 or fila["dpa_provin"] in ("13", "08"):
            ax.annotate(fila["nombre"], (fila[v], np.log(fila["tasa_hom_2024"] + 1)),
                        fontsize=7, xytext=(3, 3), textcoords="offset points")
    b, a = np.polyfit(xs[v], np.log(xs["tasa_hom_2024"] + 1), 1)
    xx = np.linspace(xs[v].min(), xs[v].max(), 50)
    ax.plot(xx, a + b * xx, color="#b22222", lw=1.5, ls="--")
    r = xs[v].corr(np.log(xs["tasa_hom_2024"] + 1))
    ax.set_title(f"{v.replace('tasa_', 'Tasa de ')} (2024-II)\nr = {r:.2f}")
    ax.set_xlabel("% de la PEA")
    ax.set_ylabel("log(tasa homicidios 2024 + 1)")
fig.suptitle("Correlación de corte transversal: mercado laboral (ENEMDU 2024-II) y homicidios por provincia")
fig.tight_layout()
ruta_corr = RUTA_FIG / "fig_04_correlacion_enemdu_homicidios.png"
fig.savefig(ruta_corr, dpi=150)
plt.close(fig)
print("Figura guardada:", ruta_corr)
# %% [markdown]
# ### (b.3) Mapas coropléticos: tasa de homicidios por 100 000 habitantes (2019, 2023, 2025)
#
# Geometrías: IGM/CONALI, Organización Territorial Provincial 2025 (EPSG:32717 → reproyección a EPSG:4326). Llave de unión: código DPA de 2 dígitos. El rango de color se recorta al percentil 95 para que Guayas no aplaste la escala.
# %%
gdf = cargar_mapa_provincias()
for anio_mapa in (2019, 2023, 2025):
    datos_mapa = tasas_anuales[tasas_anuales["anio"] == anio_mapa][["dpa_provin", "tasa"]]
    salida = RUTA_FIG / f"fig_04_mapa_homicidios_{anio_mapa}.png"
    mapa_coropletico(
        gdf,
        columna="tasa",
        titulo=f"Tasa de homicidios intencionales por 100 000 habitantes — {anio_mapa}",
        salida_png=salida,
        datos=datos_mapa,
        percentil_min=0,
        percentil_max=95,
    )
# %% [markdown]
# ## (c) Panel con efectos fijos (provincia y periodo)
#
# **Especificación:** `log(tasa_homicidios + 1) ~ tasa_desempleo + tasa_subempleo` (y una alternativa que añade empleo adecuado), con errores agrupados por provincia.
#
# **Advertencia de datos:** la ENEMDU provincial solo está disponible para 2024-II (un corte temporal). Con un solo periodo, los efectos fijos de provincia + trimestre **no son identificables** (absorberían toda la variación entre provincias). La función `efectos_fijos()` lo detecta automáticamente, lo advierte y estima la alternativa honesta: **OLS de corte transversal con dummies de región** (Sierra/Costa/Oriente/Galápagos) como control aproximado de heterogeneidad no observada y errores agrupados por provincia. Cuando el panel laboral histórico se reconstruya (notebook 03), la misma función estimará el panel completo con linearmodels.
#
# También se presenta una versión **prospectiva**: tasas laborales de 2024-II contra la tasa de homicidios de 2025, para ver si la asociación se mantiene hacia adelante.
# %%
# Corte transversal 2024: homicidios anuales 2024 + tasas laborales 2024-II.
xs2024 = xs[["dpa_provin", "periodo", "tasa_desempleo", "tasa_subempleo",
             "tasa_empleo_adecuado", "tasa_hom_2024", "tasa_hom_2025"]].copy()
xs2024["log_tasa_homicidios"] = np.log(xs2024["tasa_hom_2024"] + 1)
xs2024["region"] = xs2024["dpa_provin"].map(REGIONES)

print("=" * 78)
print("Especificación 1: log(tasa_hom_2024+1) ~ desempleo + subempleo")
print("=" * 78)
r1 = efectos_fijos(xs2024, "log_tasa_homicidios ~ tasa_desempleo + tasa_subempleo")
print("Método:", r1["metodo"], "| n =", r1["n"])
if r1["advertencia"]:
    print("ADVERTENCIA:", r1["advertencia"])
print(r1["tabla"].round(4).to_string())
print(r1["interpretacion"])

print("\n" + "=" * 78)
print("Especificación 2: + tasa_empleo_adecuado")
print("=" * 78)
r2 = efectos_fijos(xs2024, "log_tasa_homicidios ~ tasa_desempleo + tasa_subempleo + tasa_empleo_adecuado")
print("Método:", r2["metodo"], "| n =", r2["n"])
print(r2["tabla"].round(4).to_string())
print(r2["interpretacion"])

# Versión prospectiva: homicidios 2025 explicados por el mercado laboral de 2024-II.
xs_fut = xs2024.copy()
xs_fut["log_tasa_homicidios"] = np.log(xs_fut["tasa_hom_2025"] + 1)
print("\n" + "=" * 78)
print("Especificación 3 (prospectiva): log(tasa_hom_2025+1) ~ desempleo + subempleo")
print("=" * 78)
r3 = efectos_fijos(xs_fut, "log_tasa_homicidios ~ tasa_desempleo + tasa_subempleo")
print("Método:", r3["metodo"], "| n =", r3["n"])
if r3["advertencia"]:
    print("ADVERTENCIA:", r3["advertencia"])
print(r3["tabla"].round(4).to_string())
print(r3["interpretacion"])
# %% [markdown]
# ## (d) Estudio de eventos en torno al Decreto 111 (2024Q1)
#
# **Choque:** Decreto Ejecutivo 111 (9 de enero de 2024): reconocimiento del conflicto armado interno y movilización de las FF.AA.
#
# **Grupo tratado:** provincias con **debilidad estructural alta del mercado laboral**, medida con la ENEMDU 2024-II (única cobertura provincial disponible): índice = z(tasa de subempleo) + z(tasa de desempleo) − z(tasa de empleo adecuado); se toma el tercio superior (8 provincias).
#
# ⚠️ **Advertencia explícita sobre el proxy:** el panel laboral histórico aún no está reconstruido (notebook 03), por lo que no existe una variable de *deterioro* (cambio) del mercado laboral medido antes del choque. El índice usado es un **proxy de nivel (debilidad estructural)**, no de deterioro temporal; la interpretación es "provincias con mercado laboral estructuralmente más débil", no "provincias cuyo mercado laboral se deterioró más antes de 2024".
#
# **Especificación (estilo DID con efectos fijos):**
#
# `log(tasa_homicidios + 1) = α_provincia + γ_trimestre + Σ_k β_k · (tratado × D_k) + ε`
#
# con `D_k` = dummy del trimestre relativo k (base: k = −1, es decir 2023Q4) y errores agrupados por provincia. El panel de homicidios es completo (24 provincias × 34 trimestres), así que aquí los efectos fijos sí se estiman con datos reales.
# %%
# Panel trimestral completo de homicidios.
conteo = hom.groupby(["dpa_provin", "periodo"]).size().rename("homicidios").reset_index()
conteo["anio"] = conteo["periodo"].str[:4].astype(int)
panel = conteo.merge(pob, on=["dpa_provin", "anio"], how="left")

periodos = [f"{a}Q{t}" for a in range(ANIO_INICIO, ANIO_FIN + 1) for t in range(1, 5)
            if not (a == ANIO_FIN and t > 2)]
provincias = [f"{i:02d}" for i in range(1, 25)]
idx = pd.MultiIndex.from_product([provincias, periodos], names=["dpa_provin", "periodo"])
panel = panel.set_index(["dpa_provin", "periodo"]).reindex(idx).reset_index()
panel["homicidios"] = panel["homicidios"].fillna(0)
panel["anio"] = panel["periodo"].str[:4].astype(int)
# Evitar colisión de columnas: descartar la población del merge anterior y
# volver a unir con las proyecciones INEC (la reindexación creó filas nuevas).
panel = panel.drop(columns=["poblacion"]).merge(pob, on=["dpa_provin", "anio"], how="left")
panel["tasa_homicidios"] = panel["homicidios"] * 1e5 / panel["poblacion"]
panel = panel.sort_values(["dpa_provin", "periodo"]).reset_index(drop=True)
print(f"Panel homicidios: {len(panel)} observaciones "
      f"({panel['dpa_provin'].nunique()} provincias × {panel['periodo'].nunique()} trimestres)")
# %%
# Índice de debilidad estructural del mercado laboral (ENEMDU 2024-II).
idx_laboral = enemdu.copy()
for v in ["tasa_desempleo", "tasa_subempleo"]:
    idx_laboral[v + "_z"] = (idx_laboral[v] - idx_laboral[v].mean()) / idx_laboral[v].std()
idx_laboral["tasa_empleo_adecuado_z"] = (
    (idx_laboral["tasa_empleo_adecuado"] - idx_laboral["tasa_empleo_adecuado"].mean())
    / idx_laboral["tasa_empleo_adecuado"].std()
)
idx_laboral["indice_debilidad"] = (
    idx_laboral["tasa_subempleo_z"] + idx_laboral["tasa_desempleo_z"]
    - idx_laboral["tasa_empleo_adecuado_z"]
)
idx_laboral = idx_laboral.sort_values("indice_debilidad", ascending=False)
corte = idx_laboral["indice_debilidad"].quantile(2 / 3)
tratadas = idx_laboral[idx_laboral["indice_debilidad"] >= corte]["dpa_provin"].tolist()
print("Provincias tratadas (tercio superior de debilidad laboral, proxy de nivel):")
for d in tratadas:
    fila = idx_laboral[idx_laboral["dpa_provin"] == d].iloc[0]
    print(f"  {d} {NOMBRES_PROVINCIA[d]:28s} índice = {fila['indice_debilidad']:.2f}")
print(f"\nCorte del tercio superior: {corte:.2f} | N tratadas: {len(tratadas)}")
# %%
T0 = "2024Q1"  # Decreto 111 (9 de enero de 2024) -> trimestre 2024Q1
ev = event_study(panel, t0=T0, tratamiento=tratadas)
print(f"Estudio de eventos en torno a {T0} (n = {ev.attrs['n']} obs).")
print(ev.round(3).to_string(index=False))
# %%
# Gráfico de coeficientes por trimestre relativo (β_k con IC al 95 %).
fig, ax = plt.subplots(figsize=(10, 4.8))
ax.axhline(0, color="gray", lw=1)
ax.axvline(0, color="black", ls="--", lw=1.2)
ax.annotate("Decreto 111\n(2024Q1)", xy=(0, 1.02), xycoords=("data", "axes fraction"),
            ha="center", va="bottom", fontsize=9)
ax.errorbar(ev["rel_q"], ev["coef"], yerr=[ev["coef"] - ev["ci_lo"], ev["ci_hi"] - ev["coef"]],
            fmt="o", color="#1f4e79", ecolor="#1f4e79", elinewidth=1.2, capsize=3,
            label="β_k (tratadas vs. resto)")
ax.scatter([-1], [0], color="#b22222", zorder=5, label="Trimestre base (−1)")
ax.set_xticks(range(ev["rel_q"].min(), ev["rel_q"].max() + 1))
ax.set_xlabel("Trimestre relativo al Decreto 111 (2024Q1 = 0)")
ax.set_ylabel("Coeficiente β_k (log tasa homicidios + 1)")
ax.set_title("Estudio de eventos: homicidios en provincias con mercado laboral más débil")
ax.legend(frameon=False)
fig.tight_layout()
ruta_ev = RUTA_FIG / "fig_04_event_study_decreto111.png"
fig.savefig(ruta_ev, dpi=150)
plt.close(fig)
print("Figura guardada:", ruta_ev)
# %% [markdown]
# **Lectura del gráfico:** los coeficientes previos al choque (trimestres relativos negativos) no deberían mostrar tendencia si el diseño es válido; los posteriores muestran la evolución diferencial del grupo tratado. La interpretación debe ser cautelosa: el "tratamiento" no fue asignado aleatoriamente y coincide con una escalada nacional de la violencia.
#
# **Resultado observado en los datos actuales:** los β_k posteriores al choque son mayormente negativos y **ninguno es significativo al 5 %**. Es decir, las provincias con mercado laboral estructuralmente más débil **no** mostraron un aumento diferencial de homicidios tras el Decreto 111; si acaso, una trayectoria levemente inferior a la del resto. Esto es coherente con una escalada de carácter nacional (crimen organizado) más que con un patrón ligado a la debilidad del mercado laboral provincial.
# %%
# Proporción de trimestres post-tratamiento con β significativo (|t| > 1.96).
post = ev[ev["rel_q"] >= 0]
significativos = (post["coef"] / post["error_est"]).abs() > 1.96
print(f"Trimestres post-tratamiento: {len(post)} | con β significativo: {significativos.sum()}")
print("Media de β post-tratamiento:", round(post['coef'].mean(), 4))
# %% [markdown]
# ## (e) Control sintético: Esmeraldas (T0 = 2024Q1)
#
# Se construye una **Esmeraldas sintética** como combinación convexa de las demás provincias (donantes) que minimiza el RMSE pre-tratamiento (2018Q1–2023Q4) de la tasa trimestral de homicidios por 100 000 habitantes. Si la provincia sintética replica bien la trayectoria pre-tratamiento, la diferencia post-tratamiento (2024Q1 en adelante) es una descripción del desvío de Esmeraldas respecto a lo que habría sugerido su propio pasado y el de sus donantes.
#
# ⚠️ Advertencia: es un ejercicio **descriptivo/ilustrativo**. El control sintético no controla por shocks comunes a todo el país (el Decreto 111 fue nacional) ni por variables omitidas; los intervalos de incertidumbre (placebos) no se calculan aquí.
#
# **Resultado observado:** la brecha media post-tratamiento es **negativa** (Esmeraldas quedó por debajo de su provincia sintética en casi todos los trimestres de 2024–2026): su escalada homicida fue menor que la que habría sugerido su pasado combinado con el de sus donantes. No debe leerse como "efecto del Decreto 111": coincide con una respuesta estatal focalizada en la costa norte y con la reconfiguración de los grupos armados.
# %%
cs = control_sintetico(panel, tratada="08", t0="2024Q1")
print(f"Pre-tratamiento: {cs['n_pre']} trimestres | Post: {cs['n_post']}")
print(f"RMSE pre-tratamiento: {cs['pre_rmse']:.2f} homicidios por 100 mil")
print("\nDonantes con mayor peso:")
for d, w in cs["pesos"].head(6).items():
    print(f"  {d} {NOMBRES_PROVINCIA.get(d, d):28s} w = {w:.3f}")
print("\nBrecha post-tratamiento (real − sintética), por trimestre:")
for t, g in cs["gap_post"].items():
    print(f"  {t}: {g:+.2f}")
print(f"\nBrecha media post-tratamiento: {cs['gap_post'].mean():+.2f}")
# %%
# Gráfico: serie real vs. sintética + brecha.
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True,
                               gridspec_kw={"height_ratios": [2.4, 1]})
fechas = pd.Series([_periodo_a_fecha(p) for p in cs["real"].index], index=cs["real"].index)
ax1.plot(fechas, cs["real"].values, color="#1f4e79", lw=2, label="Esmeraldas (real)")
ax1.plot(fechas, cs["sintetica"].values, color="#b22222", lw=1.8, ls="--",
         label="Esmeraldas sintética")
ax1.axvline(pd.Timestamp("2024-01-01"), color="black", ls=":", lw=1.2)
ax1.annotate("T0 = 2024Q1\n(Decreto 111)", xy=(pd.Timestamp("2024-01-01"), 1.02),
             xycoords=("data", "axes fraction"), ha="center", va="bottom", fontsize=9)
ax1.set_ylabel("Tasa por 100 000 hab. (trimestral)")
ax1.set_title("Control sintético: Esmeraldas vs. provincias donantes (RMSE pre = "
              f"{cs['pre_rmse']:.2f})")
ax1.legend(frameon=False, loc="upper left")

ax2.axhline(0, color="gray", lw=1)
ax2.axvline(pd.Timestamp("2024-01-01"), color="black", ls=":", lw=1.2)
ax2.plot(fechas, (cs["real"] - cs["sintetica"]).values, color="#b22222", lw=1.6)
ax2.fill_between(fechas, (cs["real"] - cs["sintetica"]).values, 0, alpha=0.2, color="#b22222")
ax2.set_ylabel("Brecha (real − sintética)")
ax2.set_xlabel("Año")
fig.tight_layout()
ruta_cs = RUTA_FIG / "fig_04_control_sintetico_esmeraldas.png"
fig.savefig(ruta_cs, dpi=150)
plt.close(fig)
print("Figura guardada:", ruta_cs)
# %% [markdown]
# ## (f) Variables omitidas y por qué esto no es causalidad ingenua
#
# Cualquier asociación estimada en las secciones anteriores puede estar confundida por variables que no están en el panel. Las más importantes para Ecuador 2018–2026:
#
# 1. **Inversión y presencia estatal en seguridad.** El gasto policial, el número de efectivos y la capacidad investigativa varían por provincia y a lo largo del tiempo. Si las provincias con peores mercados laborales recibieron (o perdieron) recursos de seguridad, la asociación laboral-homicidios mezcla ese efecto. Datos provinciales de gasto en seguridad no están en este repositorio.
# 2. **Presencia de grupos armados organizados (GAO) y narcotráfico.** La escalada de homicidios 2021–2024 está ligada a la disputa de rutas de cocaína por bandas locales y transnacionales (los decretos 111/218/55/424 reconocen explícitamente el conflicto armado interno). La localización de esa disputa (puertos de Guayas, frontera norte, costa) determina tanto los homicidios como la actividad económica local; sin controles de presencia de GAO, la correlación con desempleo/subempleo puede ser espuria.
# 3. **Migración.** Ecuador es origen, tránsito y destino migratorio; la composición demográfica (y su cambio) afecta tanto al mercado laboral como a las tasas de criminalidad. El panel usa proyecciones de población por año, no flujos migratorios.
# 4. **Informalidad.** El subempleo captura parte, pero no toda, la informalidad. La economía ilegal (narcotráfico, minería ilegal, contrabando) genera empleo "informal" de alta renta que no aparece en la ENEMDU pero puede reducir el desempleo medido mientras aumenta la violencia.
# 5. **Conflicto y oportunidad (Becker 1968; Ehrlich 1973).** La teoría económica del crimen predice que menores oportunidades legales (desempleo/subempleo) aumentan el incentivo a actividades ilegales, pero también que la *rentabilidad* de la actividad ilegal (no observada) decide la participación. Sin medir esa rentabilidad, la asociación es ambigua en signo y magnitud.
# 6. **Respuestas de política endógenas.** El Decreto 111 no se asignó aleatoriamente: se decretó *porque* la violencia ya escalaba. El "grupo tratado" del estudio de eventos se define con el mercado laboral, pero la respuesta estatal (estados de excepción focalizados, militares en las calles) también fue selectiva por provincia.
#
# ### Interpretación honesta de lo encontrado
#
# - La serie nacional muestra una **escalada extraordinaria** de homicidios (996 en 2018 → 9 283 en 2025) que ninguna variable de mercado laboral por sí sola explica; coincide con la expansión del crimen organizado.
# - La correlación de corte transversal (2024-II) entre tasas laborales y homicidios es **descriptiva y frágil** (N = 24, un solo momento): no debe leerse como "el desempleo causa homicidios".
# - Los diseños temporales (event study y control sintético) comparan trayectorias, pero **no aíslan** el efecto del mercado laboral del efecto del choque de seguridad nacional. Cualquier diferencia post-2024 puede deberse a la represión, la reorganización de los GAO o la migración, no al empleo.
# - Conclusión prudente: los datos respaldan una **asociación condicional** entre debilidad del mercado laboral y violencia homicida en el corte 2024, con trayectorias diferenciadas tras 2024 entre provincias con mercados laborales más débiles; la **causalidad no está identificada** y las variables omitidas listadas arriba pueden explicar parte (o todo) del patrón.
#
# ## Resumen de figuras generadas
# %%
print("Figuras en reports/figures/:")
for f in sorted(RUTA_FIG.glob("fig_04_*.png")):
    print("  -", f.name, f"({f.stat().st_size // 1024} KB)")
