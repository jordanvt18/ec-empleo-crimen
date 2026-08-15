# -*- coding: utf-8 -*-
"""
loaders.py — Carga de fuentes oficiales para el proyecto ec-empleo-crimen.

Fuentes (todas oficiales del Estado ecuatoriano, acceso 2026-08-14):
  1. Homicidios intencionales — Ministerio del Interior (datosabiertos.gob.ec).
  2. Población provincial — Proyecciones INEC, Revisión 2024 (base Censo 2022).
  3. ENEMDU (empleo/desempleo/subempleo) — INEC: microdatos abiertos (CSV o SPSS)
     y tabulados de Mercado Laboral (tasas nacionales).

Convención del proyecto: el código DPA de 2 dígitos del INEC es SIEMPRE la llave
de unión (nunca nombres libres, para evitar errores por tildes/mayúsculas).

Requiere config.py (src/config.py) con las rutas y mapas del repositorio.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Importación de config.py: se intenta primero como paquete (repo raíz en
# sys.path, uso normal desde los notebooks) y luego como módulo suelto.
# ---------------------------------------------------------------------------
try:
    from src import config  # tipo: ignore
except ImportError:  # pragma: no cover
    try:
        import config  # tipo: ignore
    except ImportError:
        # Ejecución directa (python src/loaders.py): el entorno puede excluir
        # el directorio del script de sys.path; se agrega la raíz del repo.
        import pathlib
        _raiz = pathlib.Path(__file__).resolve().parents[1]
        if str(_raiz) not in sys.path:
            sys.path.insert(0, str(_raiz))
        from src import config  # tipo: ignore


def _cfg(nombre: str, valor_por_defecto=None, *alternativos):
    """Lee un atributo de config.py, probando nombres alternativos.

    Compatibilidad con el esquema de nombres de src_sources/config.py
    (p. ej. RUTA_RAW vs DATA_RAW, RUTA_RAIZ vs RAIZ, MAPEO_PROVINCIAS vs
    NOMBRES_EXTRA).
    """
    for n in (nombre,) + alternativos:
        if hasattr(config, n):
            return getattr(config, n)
    return valor_por_defecto


# ---------------------------------------------------------------------------
# Constantes de configuración (con respaldo local si config.py aún no define
# algún atributo; el contrato completo está documentado en subagent_06.md).
# ---------------------------------------------------------------------------
ANIO_INICIO = _cfg("ANIO_INICIO", 2018)
ANIO_FIN = _cfg("ANIO_FIN", 2026)
NIVEL = _cfg("NIVEL", "provincia")

RUTA_RAIZ = Path(_cfg("RAIZ", Path(__file__).resolve().parents[1],
                       "RUTA_RAIZ"))
RUTA_RAW = Path(_cfg("DATA_RAW", RUTA_RAIZ / "data" / "raw", "RUTA_RAW"))
RUTA_PROCESSED = Path(_cfg("DATA_PROCESSED",
                           RUTA_RAIZ / "data" / "processed",
                           "RUTA_PROCESSED"))
RUTA_HOMICIDIOS = Path(_cfg("DATA_RAW_HOMICIDIOS",
                            RUTA_RAW / "homicidios", "RUTA_HOMICIDIOS"))
RUTA_POBLACION = Path(_cfg("DATA_RAW_POBLACION",
                           RUTA_RAW / "poblacion", "RUTA_POBLACION"))
RUTA_ENEMDU = Path(_cfg("DATA_RAW_ENEMDU", RUTA_RAW / "enemdu",
                        "RUTA_ENEMDU"))

HOJA_HOMICIDIOS = _cfg("HOJA_HOMICIDIOS", "1. Homicidios Intencionales")

# Mapa de normalización de nombres de provincia (texto del dataset → canónico).
# La fuente de homicidios usa "STO DGO DE LOS TSÁCHILAS"; la forma oficial DPA
# es "SANTO DOMINGO DE LOS TSÁCHILAS". Se normaliza SIEMPRE por código DPA.
MAPEO_PROVINCIAS = _cfg("MAPEO_PROVINCIAS", {
    "STO DGO DE LOS TSÁCHILAS": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "STO. DGO. DE LOS TSÁCHILAS": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "SANTO DOMINGO DE LOS TSACHILAS": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "SANTO DOMINGO": "SANTO DOMINGO DE LOS TSÁCHILAS",
}, "NOMBRES_EXTRA")

# Código DPA de 2 dígitos → nombre canónico de provincia (24 provincias).
DPA_PROVINCIAS = _cfg("DPA_PROVINCIAS", {
    "01": "AZUAY", "02": "BOLÍVAR", "03": "CAÑAR", "04": "CARCHI",
    "05": "COTOPAXI", "06": "CHIMBORAZO", "07": "EL ORO", "08": "ESMERALDAS",
    "09": "GUAYAS", "10": "IMBABURA", "11": "LOJA", "12": "LOS RÍOS",
    "13": "MANABÍ", "14": "MORONA SANTIAGO", "15": "NAPO", "16": "PASTAZA",
    "17": "PICHINCHA", "18": "TUNGURAHUA", "19": "ZAMORA CHINCHIPE",
    "20": "GALÁPAGOS", "21": "SUCUMBÍOS", "22": "ORELLANA",
    "23": "SANTO DOMINGO DE LOS TSÁCHILAS", "24": "SANTA ELENA",
})

TAMAÑO_MAX_MB = _cfg("TAMAÑO_MAX_MB", 150)  # límite defensivo de descarga


# ---------------------------------------------------------------------------
# Helpers de descarga (portales oficiales)
# ---------------------------------------------------------------------------
def _headers() -> dict:
    """User-Agent de navegador: los portales oficiales rechazan bots por defecto."""
    return {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0.0.0 Safari/537.36"),
        "Accept": "*/*",
    }


def descargar_archivo(url: str, destino: str | Path,
                      tamaño_max_mb: float = TAMAÑO_MAX_MB,
                      timeout: int = 120) -> Path:
    """
    Descarga un archivo desde un portal oficial con requests (streaming).

    Parámetros:
        url: URL directa del recurso.
        destino: ruta donde guardar el archivo.
        tamaño_max_mb: aborta si el archivo supera este tamaño (defensivo;
            el servidor de INEC no emite Content-Length en HEAD).
        timeout: segundos de espera por respuesta.

    Devuelve la ruta del archivo descargado.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=_headers(), timeout=timeout, stream=True) as r:
        r.raise_for_status()
        total = 0
        with open(destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                total += len(chunk)
                if total > tamaño_max_mb * 1024 * 1024:
                    f.close()
                    destino.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"Descarga abortada: {url} supera {tamaño_max_mb:.0f} MB.")
                f.write(chunk)
    return destino


def descargar_y_descomprimir(url: str, destino_dir: str | Path,
                             patrón_archivo: str | None = None) -> list[Path]:
    """
    Descarga un ZIP oficial y extrae su contenido a destino_dir.

    Parámetros:
        url: URL del ZIP.
        destino_dir: carpeta donde extraer.
        patrón_archivo: opcional, solo extrae archivos que coincidan (p. ej.
            "*persona*"). None extrae todo.

    Devuelve la lista de archivos extraídos.
    """
    destino_dir = Path(destino_dir)
    tmp = destino_dir / "descarga_tmp.zip"
    descargar_archivo(url, tmp)
    extraídos: list[Path] = []
    with zipfile.ZipFile(tmp) as z:
        for nombre in z.namelist():
            if patrón_archivo is not None and not Path(nombre).match(patrón_archivo):
                continue
            info = z.getinfo(nombre)
            if info.is_dir():
                continue
            salida = destino_dir / Path(nombre).name
            with z.open(nombre) as src, open(salida, "wb") as f:
                f.write(src.read())
            extraídos.append(salida)
    tmp.unlink(missing_ok=True)
    return extraídos


# ---------------------------------------------------------------------------
# 1) HOMICIDIOS INTENCIONALES (Ministerio del Interior / datosabiertos.gob.ec)
# ---------------------------------------------------------------------------
def cargar_homicidios() -> pd.DataFrame:
    """
    Lee los XLSX de homicidios intencionales de data/raw/homicidios y los
    concatena en un único DataFrame a nivel de incidente (una fila = víctima).

    Archivos esperados (hoja '1. Homicidios Intencionales'):
        - 2014_2025.xlsx          (histórico 2014–2025)
        - 2026_enero_junio.xlsx   (2026 parcial, enero–junio)

    Estandarización aplicada:
        - fecha_infraccion → datetime64 (con coerción de errores).
        - codigo_provincia → str de 2 dígitos (zfill), llave DPA.
        - provincia → nombre normalizado según config.MAPEO_PROVINCIAS.
        - se eliminan filas duplicadas completas (0.5 % del histórico;
          decisión documentada: evita doble conteo en la agregación).
    """
    xlsx = sorted(RUTA_HOMICIDIOS.glob("*.xlsx"))
    datos = [p for p in xlsx if "diccionario" not in p.name.lower()]
    if not datos:
        raise FileNotFoundError(
            "No se encontraron archivos XLSX de homicidios en "
            f"{RUTA_HOMICIDIOS}. Descárgalos de "
            "https://datosabiertos.gob.ec/dataset/homicidios-intencionales "
            "(recursos 2014–2025 y 2026; hoja '" + HOJA_HOMICIDIOS + "').")

    marcos = []
    for ruta in datos:
        df = pd.read_excel(ruta, sheet_name=HOJA_HOMICIDIOS)
        df["_origen"] = ruta.name  # trazabilidad del archivo
        marcos.append(df)

    hom = pd.concat(marcos, ignore_index=True)

    # --- Estandarización ---------------------------------------------------
    hom["fecha_infraccion"] = pd.to_datetime(hom["fecha_infraccion"],
                                             errors="coerce")
    # codigo_provincia: int sin cero inicial (9=Guayas) → DPA de 2 dígitos
    codigo = pd.to_numeric(hom["codigo_provincia"], errors="coerce")
    hom["dpa_provin"] = (codigo.round().astype("Int64").astype(str)
                         .str.zfill(2).replace("<NA>", pd.NA))
    # Normalización del nombre (la fuente usa "STO DGO DE LOS TSÁCHILAS")
    hom["provincia"] = (hom["provincia"].astype(str).str.strip().str.upper()
                        .map(lambda n: MAPEO_PROVINCIAS.get(n, n)))
    # Duplicados completos: se eliminan (auditables con parámetro duplicados)
    n_dup = int(hom.duplicated().sum())
    hom = hom.drop_duplicates().reset_index(drop=True)
    print(f"[loaders] homicidios: {len(hom)} filas únicas "
          f"(se eliminaron {n_dup} duplicados de fila completa).")
    return hom


# ---------------------------------------------------------------------------
# 2) POBLACIÓN PROVINCIAL (Proyecciones INEC, Revisión 2024, base Censo 2022)
# ---------------------------------------------------------------------------
def cargar_poblacion() -> pd.DataFrame:
    """
    Lee el CSV tidy de proyecciones poblacionales provinciales
    (poblacion_provincial_1990_2035_tidy.csv, 24 provincias × 46 años).

    Columnas de salida: provincia (nombre), anio (int), poblacion (float),
    dpa_provin (str de 2 dígitos, llave DPA).
    """
    csvs = sorted(RUTA_POBLACION.glob("*tidy*.csv"))
    if not csvs:
        raise FileNotFoundError(
            "No se encontró el CSV tidy de población en "
            f"{RUTA_POBLACION}. Descarga 'Provincial.zip' de "
            "https://www.ecuadorencifras.gob.ec/proyecciones-poblacionales/ "
            "y deriva el tidy (provincia, anio, poblacion, dpa_provin).")
    pob = pd.read_csv(csvs[0])
    pob["dpa_provin"] = (pd.to_numeric(pob["dpa_provin"], errors="coerce")
                         .round().astype("Int64").astype(str)
                         .str.zfill(2).replace("<NA>", pd.NA))
    pob["anio"] = pd.to_numeric(pob["anio"], errors="coerce").astype("Int64")
    print(f"[loaders] población: {len(pob)} filas (provincia-año), "
          f"años {pob['anio'].min()}–{pob['anio'].max()}.")
    return pob


# ---------------------------------------------------------------------------
# 3) ENEMDU — MICRODATOS (tasas provinciales con factor de expansión)
# ---------------------------------------------------------------------------
def _normalizar_periodo(ruta_o_periodo: str | Path) -> tuple[str, str | None]:
    """
    Interpreta el argumento de cargar_enemdu_microdatos.

    Devuelve (ruta, token_periodo): si ruta_o_periodo es un archivo existente,
    token_periodo es None; si es un periodo (p. ej. "2024-II" o "2024Q2"),
    devuelve ("", token_normalizado) para buscar en RUTA_ENEMDU.
    """
    ruta = Path(ruta_o_periodo)
    if ruta.exists():
        return str(ruta.resolve()), None
    token = re.sub(r"[\s\-/]+", "_", str(ruta_o_periodo).strip().lower())
    return "", token


def _buscar_microdato_enemdu(token: str) -> Path:
    """
    Busca el archivo de microdatos de personas (CSV o SPSS) para el periodo
    indicado (p. ej. "2024_ii") dentro de data/raw/enemdu.
    """
    candidatos = [p for p in RUTA_ENEMDU.rglob("*persona*")
                  if p.suffix.lower() in (".sav", ".csv")]
    if not candidatos:
        raise FileNotFoundError(
            "No hay microdatos ENEMDU descargados en " + str(RUTA_ENEMDU) +
            ". Descarga el ZIP '2_BDD_DATOS_ABIERTOS_ENEMDU_<AÑO>_<TRIM>_"
            "TRIMESTRE_CSV.zip' (o '1_BDD_..._SPSS.zip') desde "
            "https://www.ecuadorencifras.gob.ec/estadisticas-laborales-enemdu/ "
            "y descomprímelo en data/raw/enemdu/.")

    anio_m = re.search(r"(20\d{2})", token)
    anio = anio_m.group(1) if anio_m else None
    # Trimestre del token: romano (I..IV) o formato Q1..Q4; se tolera "Il"/"I1"
    # por "II" (el CSV descargado usa "2024_Il"). Ojo: "_" es carácter de
    # palabra en regex, así que no se usa \b antes de "_".
    romano = None
    q_m = re.search(r"q([1-4])", token)
    for rom, patrón in (("iii", r"iii"), ("iv", r"iv"),
                        ("ii", r"i[il1]"), ("i", r"\bi\b")):
        if re.search(patrón, token):
            romano = rom
            break
    if romano is None and q_m:
        romano = {"1": "i", "2": "ii", "3": "iii", "4": "iv"}[q_m.group(1)]

    def puntaje(p: Path) -> int:
        s = p.as_posix().lower()
        pts = 0
        if anio and anio in s:
            pts += 3
        if romano:
            if romano == "ii" and re.search(r"i[il1]", s):
                pts += 2
            elif romano == "i" and re.search(r"\bi\b", s) and "ii" not in s:
                pts += 2
            elif romano in ("iii", "iv") and romano in s:
                pts += 2
        return pts

    mejores = sorted(((puntaje(p), p) for p in candidatos), reverse=True)
    if not mejores or mejores[0][0] == 0:
        raise FileNotFoundError(
            f"No se encontró microdatos ENEMDU para el periodo "
            f"'{token}' (año {anio}, trimestre {romano}). Periodos disponibles: "
            + ", ".join(sorted({p.name for _, p in mejores})) +
            ". El patrón de descarga por trimestre está documentado en "
            "fuentes.md (sección ENEMDU).")
    return mejores[0][1]


def cargar_enemdu_microdatos(ruta_o_periodo: str | Path) -> pd.DataFrame:
    """
    Carga microdatos de personas de la ENEMDU (un trimestre) y deriva la
    provincia a partir del código DPA de 6 dígitos de la variable 'ciudad'.

    Argumentos:
        ruta_o_periodo: ruta a un archivo .sav (pyreadstat) o .csv abierto
            (sep=';', decimales con coma), o un periodo a buscar en
            data/raw/enemdu (p. ej. "2024-II", "2024Q2", "2024_II").

    Columnas de salida (nivel persona):
        provincia (DPA 2 dígitos), condact, fexp (float), periodo (YYYYMM),
        mes, p03 (edad), ciudad, y las columnas originales relevantes.

    Si el archivo no existe → FileNotFoundError con instrucciones claras.
    """
    ruta, token = _normalizar_periodo(ruta_o_periodo)
    if token:
        ruta = str(_buscar_microdato_enemdu(token))

    ruta = Path(ruta)
    if ruta.suffix.lower() == ".sav":
        import pyreadstat
        df, _meta = pyreadstat.read_sav(ruta)
    elif ruta.suffix.lower() == ".csv":
        # CSV abierto del INEC: separador ';', BOM utf-8-sig, decimales con coma
        df = pd.read_csv(ruta, sep=";", encoding="utf-8-sig",
                         low_memory=False)
    else:
        raise ValueError(f"Formato no soportado: {ruta.suffix} (use .sav o .csv)")

    # fexp: en CSV viene como texto con coma decimal ("127,777...") → float
    df["fexp"] = (df["fexp"].astype(str).str.replace(",", ".")
                  .astype(float))

    # provincia = str(ciudad).zfill(6)[:2]  (10150 → "01" Azuay; 90150 → "09")
    ciudad = pd.to_numeric(df["ciudad"], errors="coerce")
    df["ciudad"] = ciudad.round().astype("Int64")
    df["provincia"] = (df["ciudad"].astype("string")
                       .str.zfill(6).str[:2].replace("<NA>", pd.NA))

    # Columnas mínimas para el panel laboral (se conservan también ciudad, p03)
    conservar = [c for c in ("provincia", "ciudad", "condact", "fexp",
                             "periodo", "mes", "p03") if c in df.columns]
    df = df[conservar].copy()
    df["periodo"] = pd.to_numeric(df["periodo"], errors="coerce").astype("Int64")
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").astype("Int64")
    df["p03"] = pd.to_numeric(df["p03"], errors="coerce").astype("Int64")
    print(f"[loaders] ENEMDU microdatos: {len(df)} personas desde {ruta.name} "
          f"({df['periodo'].dropna().nunique()} periodo(s)).")
    return df


# ---------------------------------------------------------------------------
# 4) ENEMDU — TABULADOS (tasas NACIONALES; los tabulados no traen provincia)
# ---------------------------------------------------------------------------
def cargar_tabulados_enemdu(ruta: str | Path | None = None) -> pd.DataFrame:
    """
    (Opcional) Lee un XLSX de tabulados ENEMDU 'Mercado Laboral' y devuelve la
    serie de indicadores NACIONALES.

    Nota verificada (fuentes.md): los tabulados solo traen desagregación
    Nacional/Área/Dominios urbanos; las tasas provinciales se obtienen de los
    MICRODATOS (cargar_enemdu_microdatos). Esta función sirve de contraste
    nacional (p. ej. 2024-II: desempleo 3.48 %, subempleo 20.97 %).

    Devuelve DataFrame con columnas: trimestre, indicador, nacional.
    """
    if ruta is None:
        tabulados = sorted(RUTA_ENEMDU.glob("*Tabulados*.xls*"))
        if not tabulados:
            raise FileNotFoundError(
                "No hay tabulados ENEMDU en " + str(RUTA_ENEMDU) + ".")
        # Prioriza el trimestral 2024-II si existe (contraste del panel)
        ruta = next((p for p in tabulados if "2024_II" in p.name), tabulados[0])
    ruta = Path(ruta)

    xls = pd.ExcelFile(ruta)
    hoja = next((s for s in xls.sheet_names if s.strip().startswith("2.")),
                xls.sheet_names[1])
    raw = pd.read_excel(ruta, sheet_name=hoja, header=None)

    # Detección de columnas: 'Trimestre'/'Periodo' (col 0), 'Indicadores' (col 1),
    # 'Nacional' (col 2). Las filas de datos empiezan cuando col0 es un trimestre.
    filas = []
    for _, fila in raw.iterrows():
        t = str(fila.iloc[0]).strip()
        if re.match(r"^([IVX]+|[A-Za-z]{3})\s*[-–]\s*20\d{2}$", t) or \
           re.match(r"^20\d{2}\s*[-–]", t) or \
           re.match(r"^([IVX]+)\s*[-–]\s*20\d{2}$", t):
            try:
                valor = float(fila.iloc[2])
            except (TypeError, ValueError):
                continue
            filas.append({"trimestre": t, "indicador": str(fila.iloc[1]).strip(),
                          "nacional": valor})
    if not filas:
        raise ValueError(
            f"No se pudo interpretar la hoja '{hoja}' de {ruta.name}: "
            f"hojas disponibles: {xls.sheet_names}.")
    tab = pd.DataFrame(filas)
    print(f"[loaders] tabulados ENEMDU: {len(tab)} filas (nacional) desde "
          f"{ruta.name} (hoja '{hoja}').")
    return tab


if __name__ == "__main__":
    # Prueba rápida de los cargadores (ejecución directa: python src/loaders.py)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    h = cargar_homicidios()
    print("  homicidios:", h.shape, "| provincias:", h["dpa_provin"].nunique())
    p = cargar_poblacion()
    print("  población:", p.shape)
