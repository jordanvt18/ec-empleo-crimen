# -*- coding: utf-8 -*-
"""geoprocessing.py — mapas coropléticos provinciales de Ecuador.

Fuente de geometrías: IGM/CONALI, "Organización Territorial Provincial 2025"
(https://www.geoportaligm.gob.ec/portal/). El shapefile trae 26 features:
las 24 provincias (DPA_PROVIN 01–24) más dos features especiales que se
excluyen del análisis provincial ("ZONA EN ESTUDIO: JUVAL (CAÑAR)" con código
90 e "ISLA"). La llave de unión con el panel es SIEMPRE el código DPA de
2 dígitos (nunca el nombre en texto libre).

Funciones públicas:
- cargar_mapa_provincias(ruta_shapefile=None) -> gpd.GeoDataFrame (24 provincias)
- mapa_coropletico(gdf, columna, titulo, salida_png, ...) -> gpd.GeoDataFrame

Los mapas se guardan como PNG en reports/figures/ con títulos y etiquetas en
español (incluidas las tildes).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import Normalize

# Códigos DPA de las 24 provincias (llave de unión del proyecto).
CODIGOS_PROVINCIAS = [f"{i:02d}" for i in range(1, 25)]


def _raiz_repo() -> Path:
    """Devuelve la raíz del repositorio.

    Orden de preferencia: (1) config del proyecto (src/config.py) si está
    importable; (2) variable de entorno EC_EMPLEO_CRIMEN_REPO; (3) heurística
    sobre el directorio actual (cwd o su padre si contiene src/). Esto hace
    que las rutas funcionen tanto ejecutando desde la raíz como desde
    notebooks/ (caso jupyter/nbconvert).
    """
    try:
        from src import config  # type: ignore

        return config.RAIZ
    except Exception:
        pass
    import os

    env = os.environ.get("EC_EMPLEO_CRIMEN_REPO")
    if env:
        return Path(env)
    cwd = Path.cwd()
    if (cwd / "src").exists():
        return cwd
    if (cwd.parent / "src").exists():
        return cwd.parent
    return cwd


def cargar_mapa_provincias(ruta_shapefile: str | Path | None = None) -> gpd.GeoDataFrame:
    """Carga el shapefile CONALI 2025 y devuelve solo las 24 provincias.

    Parámetros
    ----------
    ruta_shapefile : ruta al .shp. Si es None, se busca la ruta por defecto
        ``data/raw/geografia/conali_ot_provincial_2025_shp/ORGANIZACION_TERRITORIAL_PROVINCIAL.shp``
        relativa a la raíz del repositorio.

    Devuelve
    --------
    GeoDataFrame con las columnas originales (DPA_PROVIN, DPA_DESPRO, ...) y
    ``DPA_PROVIN`` normalizado a str de 2 dígitos (zfill(2)). Se mantiene el
    CRS original del shapefile (EPSG:32717, UTM 17S); la reproyección a
    EPSG:4326 la hace ``mapa_coropletico``.
    """
    if ruta_shapefile is None:
        ruta_shapefile = (
            _raiz_repo()
            / "data"
            / "raw"
            / "geografia"
            / "conali_ot_provincial_2025_shp"
            / "ORGANIZACION_TERRITORIAL_PROVINCIAL.shp"
        )
    ruta_shapefile = Path(ruta_shapefile)
    if not ruta_shapefile.exists():
        raise FileNotFoundError(
            f"No existe el shapefile CONALI en {ruta_shapefile}. "
            "Descárguelo desde el Geoportal IGM (ver fuentes.md) o ajuste la ruta."
        )

    # encoding utf-8 (el .cpg del shapefile lo indica); fallback latin-1.
    try:
        gdf = gpd.read_file(ruta_shapefile, encoding="utf-8")
    except UnicodeDecodeError:
        gdf = gpd.read_file(ruta_shapefile, encoding="latin-1")

    # Normalizar el código DPA a str de 2 dígitos (p. ej. 9 -> "09").
    gdf["DPA_PROVIN"] = gdf["DPA_PROVIN"].astype(str).str.strip().str.zfill(2)

    # Filtrar las 24 provincias: excluye código 90 (zona JUVAL) e "ISLA".
    gdf = gdf[gdf["DPA_PROVIN"].isin(CODIGOS_PROVINCIAS)].copy()
    gdf = gdf.sort_values("DPA_PROVIN").reset_index(drop=True)
    return gdf


def mapa_coropletico(
    gdf: gpd.GeoDataFrame,
    columna: str,
    titulo: str,
    salida_png: str | Path,
    datos: pd.DataFrame | None = None,
    columna_dpa_datos: str = "dpa_provin",
    columna_dpa_mapa: str = "DPA_PROVIN",
    fmt: str = "{:.1f}",
    cmap: str = "YlOrRd",
    percentil_min: float | None = None,
    percentil_max: float | None = 95.0,
    nota_pie: str = "Fuente: Ministerio del Interior (DINASED) e INEC. Elaboración propia.",
) -> gpd.GeoDataFrame:
    """Dibuja un mapa coroplético provincial y lo guarda como PNG.

    Parámetros
    ----------
    gdf : geometrías de ``cargar_mapa_provincias()`` (o un gdf ya unido).
    columna : nombre de la columna con el valor a colorear (tasa, conteo, ...).
    titulo : título del mapa (español).
    salida_png : ruta de salida; se crea el directorio si falta (reports/figures/).
    datos : opcional, DataFrame con la columna de datos y la llave DPA
        (``columna_dpa_datos``). Si se entrega, se fusiona con el mapa por DPA.
    percentil_min / percentil_max : recorte del rango de color por percentiles
        (útil con datos muy asimétricos como los homicidios: Guayas domina).
        None = usar el rango completo de los datos.
    nota_pie : texto de fuente bajo el mapa.

    Devuelve
    --------
    El GeoDataFrame fusionado (ya reproyectado a EPSG:4326), para inspección.
    """
    salida_png = Path(salida_png)
    salida_png.parent.mkdir(parents=True, exist_ok=True)

    if datos is not None:
        # Fusionar el panel con las geometrías usando el código DPA de 2 dígitos.
        gdf = gdf.merge(
            datos[[columna_dpa_datos, columna]],
            left_on=columna_dpa_mapa,
            right_on=columna_dpa_datos,
            how="left",
        )

    if columna not in gdf.columns:
        raise ValueError(f"La columna '{columna}' no está en el GeoDataFrame.")

    # Provincias sin dato (p. ej. Galápagos sin homicidios en 2026) -> 0.
    faltantes = int(gdf[columna].isna().sum())
    if faltantes:
        print(f"  [aviso] {faltantes} provincia(s) sin dato en '{columna}'; se imputa 0.")
        gdf[columna] = gdf[columna].fillna(0.0)

    # Reproyección a EPSG:4326 (lat/lon) para un dibujo consistente.
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Rango de color: por percentiles si se pide (robusto a valores extremos).
    valores = gdf[columna].astype(float)
    if percentil_min is None:
        vmin = float(valores.min())
    else:
        vmin = float(np.nanpercentile(valores, percentil_min))
    if percentil_max is None:
        vmax = float(valores.max())
    else:
        vmax = float(np.nanpercentile(valores, percentil_max))
    if vmax <= vmin:
        vmin, vmax = float(valores.min()), float(valores.max())

    fig, ax = plt.subplots(figsize=(8, 9))
    gdf.plot(
        column=columna,
        cmap=cmap,
        edgecolor="white",
        linewidth=0.6,
        ax=ax,
        norm=Normalize(vmin=vmin, vmax=vmax),
    )
    ax.set_axis_off()
    ax.set_title(titulo, fontsize=13, pad=12)

    # Barra de color con etiqueta en español.
    sm = cm.ScalarMappable(cmap=cmap, norm=Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.03)
    cbar.set_label("Tasa por 100 000 habitantes", fontsize=10)
    cbar.ax.tick_params(labelsize=9)

    fig.text(0.5, 0.01, nota_pie, ha="center", fontsize=8, color="gray")
    fig.savefig(salida_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Mapa guardado: {salida_png}")
    return gdf
