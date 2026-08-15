# -*- coding: utf-8 -*-
"""
config.py — Configuración central del proyecto ec-empleo-crimen.

Proyecto: relación entre desempleo/subempleo y homicidios intencionales en
Ecuador a nivel provincial (2018–2026). Metodología CRISP-DM.
Fuentes oficiales: INEC (ENEMDU, proyecciones poblacionales), Ministerio del
Interior — Dirección de Estadística y Economía de la Seguridad (homicidios),
IGM/CONALI (cartografía provincial).

Este módulo centraliza rutas, parámetros del panel y la tabla DPA de 2 dígitos
(la llave de unión de todo el proyecto; nunca unir por nombres en texto libre).

Uso típico desde un notebook (ejecutado en notebooks/ o en la raíz):

    import sys, pathlib
    _candidatas = [pathlib.Path.cwd(), pathlib.Path.cwd().parent]
    RAIZ = next(p for p in _candidatas if (p / "data" / "raw").exists())
    sys.path.insert(0, str(RAIZ / "src"))
    import config
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Parámetros del análisis
# ---------------------------------------------------------------------------

# Rango de años del panel. Parametrizado para cambio fácil.
ANIO_INICIO = 2018
ANIO_FIN = 2026

# Nivel de agregación del análisis: "provincia" (24 provincias).
# Alternativa futura: "canton".
NIVEL = "provincia"

# Periodicidad del panel: "trimestre". La ENEMDU es trimestral y los
# homicidios (mensuales) se agregan a trimestre en la fase de preparación.
PERIODICIDAD = "trimestre"

# Trimestre de microdatos ENEMDU ya descargados y verificados (2024-II).
ENEMDU_TRIMESTRE_REFERENCIA = "2024_II"
ENEMDU_TRIMESTRE_LABEL = "2024-II"

# ---------------------------------------------------------------------------
# Rutas (relativas a la raíz del repositorio)
# ---------------------------------------------------------------------------

# RAIZ se deriva de la ubicación de este archivo (src/config.py):
# parents[0] = src, parents[1] = raíz del repositorio.
RAIZ = Path(__file__).resolve().parents[1]

DATA_RAW = RAIZ / "data" / "raw"
DATA_PROCESSED = RAIZ / "data" / "processed"
DATA_RAW_HOMICIDIOS = DATA_RAW / "homicidios"
DATA_RAW_POBLACION = DATA_RAW / "poblacion"
DATA_RAW_GEOGRAFIA = DATA_RAW / "geografia"
DATA_RAW_ENEMDU = DATA_RAW / "enemdu"

REPORTS = RAIZ / "reports"
REPORTS_FIGURES = REPORTS / "figures"

# Alias RUTA_* (compatibilidad con notebooks que usan esta convención).
RUTA_RAIZ = RAIZ
RUTA_RAW = DATA_RAW
RUTA_PROCESSED = DATA_PROCESSED
RUTA_HOMICIDIOS = DATA_RAW_HOMICIDIOS
RUTA_POBLACION = DATA_RAW_POBLACION
RUTA_GEOGRAFIA = DATA_RAW_GEOGRAFIA
RUTA_ENEMDU = DATA_RAW_ENEMDU
RUTA_FIG = REPORTS_FIGURES
RUTA_PROCESADOS = DATA_PROCESSED
RUTA_FIGURES = REPORTS_FIGURES

# Archivos clave ya descargados (fecha de acceso: 2026-08-14).
ARCHIVO_HOMICIDIOS_2014_2025 = DATA_RAW_HOMICIDIOS / "2014_2025.xlsx"
ARCHIVO_HOMICIDIOS_2026 = DATA_RAW_HOMICIDIOS / "2026_enero_junio.xlsx"
ARCHIVO_POBLACION_TIDY = DATA_RAW_POBLACION / "poblacion_provincial_1990_2035_tidy.csv"
SHAPEFILE_PROVINCIAS = (
    DATA_RAW_GEOGRAFIA
    / "conali_ot_provincial_2025_shp"
    / "ORGANIZACION_TERRITORIAL_PROVINCIAL.shp"
)
SPSS_ENEMDU_2024_II = (
    DATA_RAW_ENEMDU / "microdatos_spss_2024_II" / "enemdu_persona_2024_II_trimestre.sav"
)
TABULADO_ENEMDU_2026_05 = DATA_RAW_ENEMDU / "202605_Tabulados_Mercado_Laboral_EXCEL.xlsx"

# ---------------------------------------------------------------------------
# Tabla DPA: código de 2 dígitos → nombre oficial de la provincia.
# (INEC/IGM; llave de unión de todas las fuentes del proyecto.)
# ---------------------------------------------------------------------------

DPA_PROVINCIAS = {
    "01": "AZUAY",
    "02": "BOLÍVAR",
    "03": "CAÑAR",
    "04": "CARCHI",
    "05": "COTOPAXI",
    "06": "CHIMBORAZO",
    "07": "EL ORO",
    "08": "ESMERALDAS",
    "09": "GUAYAS",
    "10": "IMBABURA",
    "11": "LOJA",
    "12": "LOS RÍOS",
    "13": "MANABÍ",
    "14": "MORONA SANTIAGO",
    "15": "NAPO",
    "16": "PASTAZA",
    "17": "PICHINCHA",
    "18": "TUNGURAHUA",
    "19": "ZAMORA CHINCHIPE",
    "20": "GALÁPAGOS",
    "21": "SUCUMBÍOS",
    "22": "ORELLANA",
    "23": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "24": "SANTA ELENA",
}

# Nombres alternativos observados en los datasets crudos → nombre oficial DPA.
# El dataset de homicidios del Ministerio del Interior usa mayúsculas sin
# tildes y abreviaturas (p. ej. "STO DGO DE LOS TSÁCHILAS"). Este diccionario
# es un respaldo: la unión canónica siempre usa el código DPA, nunca el nombre.
NOMBRES_EXTRA = {
    "STO DGO DE LOS TSÁCHILAS": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "STO DGO DE LOS TSACHILAS": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "SANTO DOMINGO": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "TSACHILAS": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "GALAPAGOS": "GALÁPAGOS",
    "LOS RIOS": "LOS RÍOS",
    "BOLIVAR": "BOLÍVAR",
    "CANAR": "CAÑAR",
    "MANABI": "MANABÍ",
    "SUCUMBIOS": "SUCUMBÍOS",
}
