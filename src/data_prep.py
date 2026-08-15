# -*- coding: utf-8 -*-
"""
data_prep.py — Preparación de datos para ec-empleo-crimen.

Convierte las fuentes crudas (loaders.py) en el panel provincia-periodo que
alimenta el modelado (notebooks 04/05):

    - normalización de provincia a código DPA de 2 dígitos;
    - agregación trimestral de homicidios intencionales por provincia;
    - tasas ENEMDU provinciales (desempleo, subempleo, empleo adecuado)
      desde microdatos con factor de expansión;
    - panel provincia-trimestre con tasa de homicidios por 100 000 hab.
      (denominador: proyecciones poblacionales INEC por provincia-año);
    - indicador de deterioro del mercado laboral para el diseño de eventos
      (decretos de conflicto armado interno).

Requiere config.py (src/config.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

try:
    from src import config  # tipo: ignore
except ImportError:  # pragma: no cover
    try:
        import config  # tipo: ignore
    except ImportError:
        # Ejecución directa (python src/data_prep.py): el entorno puede
        # excluir el directorio del script de sys.path; se agrega la raíz.
        import pathlib
        _raiz = pathlib.Path(__file__).resolve().parents[1]
        if str(_raiz) not in sys.path:
            sys.path.insert(0, str(_raiz))
        from src import config  # tipo: ignore


def _cfg(nombre: str, valor_por_defecto=None, *alternativos):
    """Lee un atributo de config.py, probando nombres alternativos
    (compatibilidad con src_sources/config.py: RUTA_RAW vs DATA_RAW, etc.)."""
    for n in (nombre,) + alternativos:
        if hasattr(config, n):
            return getattr(config, n)
    return valor_por_defecto


ANIO_INICIO = _cfg("ANIO_INICIO", 2018)
ANIO_FIN = _cfg("ANIO_FIN", 2026)
NIVEL = _cfg("NIVEL", "provincia")
RUTA_RAIZ = Path(_cfg("RAIZ", Path(__file__).resolve().parents[1],
                       "RUTA_RAIZ"))
RUTA_PROCESSED = Path(_cfg("DATA_PROCESSED",
                           RUTA_RAIZ / "data" / "processed",
                           "RUTA_PROCESSED"))
MAPEO_PROVINCIAS = _cfg("MAPEO_PROVINCIAS", {}, "NOMBRES_EXTRA")
DPA_PROVINCIAS = _cfg("DPA_PROVINCIAS", {})

# Mapa inverso: nombre canónico → código DPA (para normalizar desde texto)
NOMBRE_A_DPA = {nombre.upper(): cod for cod, nombre in DPA_PROVINCIAS.items()}
# Aliases observados en los datasets crudos (p. ej. "STO DGO DE LOS
# TSÁCHILAS") → código canónico. Se resuelve alias→canónico→código (nunca
# al revés: los valores de MAPEO_PROVINCIAS son nombres, no códigos).
for _alias, _canonico in MAPEO_PROVINCIAS.items():
    _canon = str(_canonico).upper()
    if _canon in NOMBRE_A_DPA:
        NOMBRE_A_DPA[str(_alias).upper()] = NOMBRE_A_DPA[_canon]


# ---------------------------------------------------------------------------
# Normalización DPA
# ---------------------------------------------------------------------------
def normalizar_provincia(df: pd.DataFrame, col: str) -> pd.Series:
    """
    Normaliza la columna de provincia a código DPA de 2 dígitos (llave del
    proyecto). Acepta tanto códigos (int 1..24, str "1", "09") como nombres
    libres (p. ej. "GUAYAS", "STO DGO DE LOS TSÁCHILAS").

    Los valores no reconocidos se devuelven como NaN y se reporta el conteo.
    """
    serie = df[col]
    # Caso 1: ya son códigos numéricos / de 2 dígitos
    if pd.api.types.is_numeric_dtype(serie) or \
       serie.astype(str).str.fullmatch(r"\d{1,2}").all():
        numerico = pd.to_numeric(serie, errors="coerce")
        return (numerico.round().astype("Int64").astype(str)
                .str.zfill(2).replace("<NA>", pd.NA))
    # Caso 2: nombres libres → mapa inverso (config)
    limpio = (serie.astype(str).str.strip().str.upper()
              .map(lambda n: MAPEO_PROVINCIAS.get(n, n)))
    codigo = limpio.map(NOMBRE_A_DPA)
    n_no = int(codigo.isna().sum())
    if n_no:
        print(f"[data_prep] normalizar_provincia: {n_no} valor(es) no "
              f"reconocido(s) en '{col}' → NaN. Ejemplos: "
              f"{sorted(set(limpio[codigo.isna()]))[:5]}")
    return codigo


# ---------------------------------------------------------------------------
# Agregación de homicidios
# ---------------------------------------------------------------------------
def _mes_a_trimestre(mes: int) -> int:
    """Mapea mes (1–12) a trimestre calendario (1–4)."""
    return (int(mes) - 1) // 3 + 1


def agregar_homicidios(df: pd.DataFrame, frecuencia: str = "trimestre",
                       por_tipo: bool = False) -> pd.DataFrame:
    """
    Agrega homicidios intencionales (nivel incidente) por provincia y periodo.

    Parámetros:
        df: salida de loaders.cargar_homicidios() (requiere dpa_provin y
            fecha_infraccion; opcional tipo_muerte para el desglose).
        frecuencia: "trimestre" (por defecto), "anual" o "mensual".
        por_tipo: si True, agrega además columnas homicidios_<TIPO_MUERTE>
            (ASESINATO, HOMICIDIO, FEMICIDIO, SICARIATO).

    Devuelve DataFrame con columnas: dpa_provin, anio, periodo, homicidios
    (y trimestre/mes según frecuencia; y desglose por tipo si por_tipo=True).
    El periodo usa el formato "AAAA-Tn" (p. ej. "2024-Q2") para ENEMDU.
    """
    df = df.copy()
    df["anio"] = df["fecha_infraccion"].dt.year
    if frecuencia == "trimestre":
        df["trimestre"] = df["fecha_infraccion"].dt.month.map(_mes_a_trimestre)
        df["periodo"] = df["anio"].astype(str) + "-Q" + df["trimestre"].astype(str)
        agrupar = ["dpa_provin", "anio", "trimestre", "periodo"]
    elif frecuencia == "anual":
        df["periodo"] = df["anio"].astype(str)
        agrupar = ["dpa_provin", "anio", "periodo"]
    elif frecuencia == "mensual":
        df["mes"] = df["fecha_infraccion"].dt.month
        df["periodo"] = (df["anio"].astype(str) + "-"
                         + df["mes"].astype(str).str.zfill(2))
        agrupar = ["dpa_provin", "anio", "mes", "periodo"]
    else:
        raise ValueError(f"frecuencia no válida: {frecuencia}")

    # Recorte al rango del proyecto (config: 2018–2026)
    df = df[(df["anio"] >= ANIO_INICIO) & (df["anio"] <= ANIO_FIN)].copy()

    conteo = (df.groupby(agrupar, dropna=False)
              .size().rename("homicidios").reset_index())
    if por_tipo:
        tipos = (df.assign(_n=1)
                 .pivot_table(index=agrupar, columns="tipo_muerte",
                              values="_n", aggfunc="sum", fill_value=0)
                 .add_prefix("homicidios_").reset_index())
        conteo = conteo.merge(tipos, on=agrupar, how="left")

    # --- Relleno del panel: todas las provincias × todos los periodos -------
    # Provincias sin registros en un periodo (p. ej. Galápagos en 2026, o
    # cualquier provincia con 0 homicidios en un trimestre) quedan con
    # homicidios = 0 en vez de desaparecer: el panel debe ser balanceado en
    # la dimensión espacial para el cruce con ENEMDU y el modelado.
    if DPA_PROVINCIAS:
        rejilla = pd.DataFrame(
            [(p, t) for p in sorted(DPA_PROVINCIAS.keys())
             for t in sorted(conteo["periodo"].unique())],
            columns=["dpa_provin", "periodo"])
        conteo = rejilla.merge(conteo, on=["dpa_provin", "periodo"],
                               how="left")
        n_rellenados = int(conteo["homicidios"].isna().sum())
        conteo["homicidios"] = (conteo["homicidios"].fillna(0)
                                 .astype("int64"))
        if por_tipo:
            cols_tipo = [c for c in conteo if c.startswith("homicidios_")]
            conteo[cols_tipo] = (conteo[cols_tipo].fillna(0)
                                 .astype("int64"))
        print(f"[data_prep] agregar_homicidios: {n_rellenados} celdas "
              f"provincia-periodo sin registros → homicidios = 0.")
        # Reconstrucción de anio (y trimestre/mes) desde el periodo
        conteo["anio"] = conteo["periodo"].str[:4].astype("int64")
        if frecuencia == "trimestre":
            conteo["trimestre"] = (conteo["periodo"].str[-1]
                                    .astype("int64"))
        elif frecuencia == "mensual":
            conteo["mes"] = (conteo["periodo"].str[-2:].astype("int64"))
    return conteo.sort_values(["dpa_provin", "periodo"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tasas ENEMDU provinciales desde microdatos
# ---------------------------------------------------------------------------
_ROMANOS = {1: "I", 2: "II", 3: "III", 4: "IV"}


def _periodo_desde_yyyymm(periodo) -> tuple[str, str]:
    """Convierte YYYYMM → (periodo 'AAAA-Tn', etiqueta 'AAAA-n')."""
    p = int(periodo)
    anio, mes = p // 100, p % 100
    t = _mes_a_trimestre(mes)
    return f"{anio}-Q{t}", f"{anio}-{_ROMANOS[t]}"


def tasas_enemdu_provincial(df_enemdu: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula tasas provinciales de desempleo, subempleo y empleo adecuado a
    partir de microdatos ENEMDU (un trimestre), ponderadas con fexp.

    Definiciones oficiales (codificación verificada en fuentes.md):
        PEA         = condact ∈ {1..8}
        Ocupados    = condact ∈ {1..6}
        Desocupados = condact ∈ {7,8}   → tasa_desempleo = 100×Desoc/PEA
        Empleo adecuado = condact == 1  → tasa_empleo_adecuado
        Subempleo   = condact ∈ {2,3}   → tasa_subempleo
    Las tasas se expresan en porcentaje de la PEA.

    Devuelve DataFrame con una fila por provincia: dpa_provin, periodo
    ('AAAA-Tn'), etiqueta_periodo ('AAAA-n'), PEA, ocupados, desocupados y las
    tres tasas.
    """
    df = df_enemdu.copy()
    df["condact"] = pd.to_numeric(df["condact"], errors="coerce")
    ocup = df["condact"].isin([1, 2, 3, 4, 5, 6])
    desoc = df["condact"].isin([7, 8])
    adec = df["condact"] == 1
    sube = df["condact"].isin([2, 3])
    pea = ocup | desoc
    f = df["fexp"]

    g = df.assign(_pea=pea, _ocup=ocup, _desoc=desoc, _adec=adec, _sube=sube)
    tab = (g.groupby("provincia", dropna=False)
           .apply(lambda d: pd.Series({
               "PEA": (d["_pea"] * d["fexp"]).sum(),
               "Ocupados": (d["_ocup"] * d["fexp"]).sum(),
               "Desocupados": (d["_desoc"] * d["fexp"]).sum(),
               "Empleo_adecuado": (d["_adec"] * d["fexp"]).sum(),
               "Subempleo": (d["_sube"] * d["fexp"]).sum(),
           }), include_groups=False)
           .reset_index())

    # Periodo del trimestre (YYYYMM → 'AAAA-Tn'); se toma el primer valor
    periodo_orig = df["periodo"].dropna()
    periodo, etiqueta = _periodo_desde_yyyymm(periodo_orig.iloc[0]) \
        if len(periodo_orig) else ("", "")
    tab["periodo"] = periodo
    tab["etiqueta_periodo"] = etiqueta

    tab["tasa_desempleo"] = 100 * tab["Desocupados"] / tab["PEA"]
    tab["tasa_subempleo"] = 100 * tab["Subempleo"] / tab["PEA"]
    tab["tasa_empleo_adecuado"] = 100 * tab["Empleo_adecuado"] / tab["PEA"]
    tab = tab.rename(columns={"provincia": "dpa_provin"})
    # Normaliza a DPA 2 dígitos (en microdatos ya viene así; por seguridad)
    tab["dpa_provin"] = tab["dpa_provin"].astype(str).str.zfill(2)
    print(f"[data_prep] tasas ENEMDU: {len(tab)} provincias, periodo "
          f"{periodo} ({etiqueta}).")
    return tab


# ---------------------------------------------------------------------------
# Panel provincia-periodo
# ---------------------------------------------------------------------------
def construir_panel(homicidios: pd.DataFrame,
                    poblacion: pd.DataFrame,
                    enemdu: pd.DataFrame | None = None,
                    guardar: bool = True) -> pd.DataFrame:
    """
    Construye el panel provincia-trimestre del proyecto.

    Parámetros:
        homicidios: agregados de agregar_homicidios() (dpa_provin, anio,
            periodo, homicidios).
        poblacion: cargar_poblacion() (dpa_provin, anio, poblacion) — las
            proyecciones INEC son el denominador fijo por provincia-año.
        enemdu: opcional, tasas_enemdu_provincial() (dpa_provin, periodo,
            tasas...). Se une a la izquierda por (dpa_provin, periodo).
        guardar: si True escribe data/processed/panel_provincia_trimestre.csv
            y data/processed/panel_homicidios.csv.

    Devuelve el panel con tasa_homicidios_100k = homicidios × 100 000 /
    población (por provincia-año).
    """
    # Población anual → se propaga al trimestre (denominador fijo por año)
    pob = poblacion[["dpa_provin", "anio", "poblacion"]].copy()
    panel = homicidios.merge(pob, on=["dpa_provin", "anio"], how="left")

    faltantes = int(panel["poblacion"].isna().sum())
    if faltantes:
        print(f"[data_prep] AVISO: {faltantes} filas sin población "
              f"(provincia-año fuera de las proyecciones 1990–2035).")

    panel["tasa_homicidios_100k"] = (
        100_000 * panel["homicidios"] / panel["poblacion"])

    # Panel de homicidios (sin mercado laboral): se guarda aparte
    panel_homicidios = panel.sort_values(["dpa_provin", "periodo"]).copy()

    # Unión con tasas ENEMDU cuando el trimestre esté disponible
    if enemdu is not None and len(enemdu):
        cols_enemdu = ["dpa_provin", "periodo", "etiqueta_periodo", "PEA",
                       "Ocupados", "Desocupados", "Empleo_adecuado",
                       "Subempleo", "tasa_desempleo", "tasa_subempleo",
                       "tasa_empleo_adecuado"]
        panel = panel.merge(enemdu[cols_enemdu], on=["dpa_provin", "periodo"],
                            how="left")
    panel = panel.sort_values(["dpa_provin", "periodo"]).reset_index(drop=True)

    if guardar:
        RUTA_PROCESSED.mkdir(parents=True, exist_ok=True)
        panel.to_csv(RUTA_PROCESSED / "panel_provincia_trimestre.csv",
                     index=False, encoding="utf-8-sig")
        panel_homicidios.to_csv(RUTA_PROCESSED / "panel_homicidios.csv",
                                index=False, encoding="utf-8-sig")
        print(f"[data_prep] guardado: {RUTA_PROCESSED / 'panel_provincia_trimestre.csv'}")
        print(f"[data_prep] guardado: {RUTA_PROCESSED / 'panel_homicidios.csv'}")
    return panel


# ---------------------------------------------------------------------------
# Deterioro del mercado laboral (para el diseño de eventos)
# ---------------------------------------------------------------------------
def deterioro_mercado_laboral(panel: pd.DataFrame,
                              ventana: int = 4) -> pd.DataFrame:
    """
    Calcula el deterioro del mercado laboral como el cambio en la suma
    (tasa_desempleo + tasa_subempleo) entre el periodo actual y el de
    'ventana' trimestres antes (por provincia).

    Uso: clasificar provincias por su deterioro previo al Decreto 111
    (9-ene-2024, conflicto armado interno) y comparar trayectorias.

    Devuelve el panel con las columnas:
        indice_desempleo_subempleo: suma de las dos tasas (puntos %);
        deterioro_ml_{ventana}q: cambio en puntos porcentuales respecto a
        'ventana' trimestres atrás (NaN para los primeros periodos).
    """
    out = panel.copy()
    if "tasa_desempleo" not in out or "tasa_subempleo" not in out:
        raise ValueError("El panel no contiene tasas ENEMDU "
                         "(tasa_desempleo/tasa_subempleo).")
    out = out.sort_values(["dpa_provin", "periodo"]).copy()
    out["indice_desempleo_subempleo"] = (
        out["tasa_desempleo"] + out["tasa_subempleo"])
    out[f"deterioro_ml_{ventana}q"] = (
        out.groupby("dpa_provin")["indice_desempleo_subempleo"]
           .diff(periods=ventana))
    print(f"[data_prep] deterioro_mercado_laboral: ventana de {ventana} "
          f"trimestres; {int(out[f'deterioro_ml_{ventana}q'].notna().sum())} "
          "observaciones con deterioro calculado.")
    return out


if __name__ == "__main__":
    # Prueba rápida (ejecución directa)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from src import loaders
    hom = loaders.cargar_homicidios()
    agg = agregar_homicidios(hom)
    print("  agregación:", agg.shape)
