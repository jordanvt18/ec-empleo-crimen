# -*- coding: utf-8 -*-
"""
app.py — App Streamlit del proyecto ec-empleo-crimen.

Visualización interactiva del panel provincia-trimestre:
series de tiempo, mapa coroplético y tabla resumen.

Ejecutar desde la raíz del repositorio:
    streamlit run app.py

Requisito de datos: ejecutar primero los notebooks 01–03 para generar
data/processed/panel_provincia_trimestre.csv (si no existe, la app lo indica).
"""

import pathlib

import pandas as pd
import streamlit as st  # noqa: E402  (se usa en decoradores @st.cache_data y en la UI)

# --- Rutas del repositorio --------------------------------------------------
RAIZ = pathlib.Path(__file__).resolve().parent
RUTA_PANEL = RAIZ / "data" / "processed" / "panel_provincia_trimestre.csv"
RUTA_SHAPEFILE = (
    RAIZ / "data" / "raw" / "geografia" / "conali_ot_provincial_2025_shp"
    / "ORGANIZACION_TERRITORIAL_PROVINCIAL.shp"
)
RUTA_GEOJSON_CACHE = RAIZ / "data" / "processed" / "geojson_provincias.json"

# Variable que la app grafica por defecto y sus etiquetas en español
VARIABLES = {
    "tasa_homicidios_100k": "Homicidios por 100 000 hab.",
    "tasa_desempleo": "Tasa de desempleo (%)",
    "tasa_subempleo": "Tasa de subempleo (%)",
}

ANIO_INICIO = 2018
ANIO_FIN = 2026


@st.cache_data(show_spinner=False)
def cargar_panel(ruta):
    """Carga el panel provincia-trimestre y normaliza los tipos básicos."""
    df = pd.read_csv(ruta)
    if "dpa" in df.columns:
        df["dpa"] = df["dpa"].astype(str).str.zfill(2)
    if "periodo" in df.columns:
        # El periodo se guarda como AAAAT (ej. 202404 → año 2024, trimestre 4)
        df["anio"] = df["periodo"] // 100
        df["trimestre"] = df["periodo"] % 100
        df["fecha"] = pd.to_datetime(df["anio"].astype(str) + "-" +
                                     ((df["trimestre"] - 1) * 3 + 1).astype(str) + "-01")
    if "provincia" in df.columns:
        df["provincia"] = df["provincia"].astype(str).str.title()
    return df


@st.cache_data(show_spinner=False)
def cargar_geometrias():
    """
    Carga las geometrías provinciales para el mapa coroplético.

    Orden de búsqueda:
      1) Shapefile IGM/CONALI en data/raw/geografia (fuente primaria).
      2) GeoJSON cacheado en data/processed/geojson_provincias.json
         (generado por geoprocessing.py del notebook 04).
      3) Si no hay ninguno, se devuelve None y la app muestra un aviso
         (no se inventan geometrías; ejecutar los notebooks 02–04).
    """
    try:
        import geopandas as gpd
    except ImportError:
        return None, "geopandas no está instalado (ver requirements.txt)"

    if RUTA_SHAPEFILE.exists():
        gdf = gpd.read_file(RUTA_SHAPEFILE)
        # El shapefile CONALI usa DPA_PROVIN (int) y DPA_DESPRO (nombre en mayúsculas)
        if "DPA_PROVIN" in gdf.columns:
            gdf["dpa"] = gdf["DPA_PROVIN"].astype(str).str.zfill(2)
        # Excluir filas sin código provincial (zona JUVAL e isla)
        gdf = gdf[gdf["dpa"].str.isdigit()]
        return gdf, None

    if RUTA_GEOJSON_CACHE.exists():
        gdf = gpd.read_file(RUTA_GEOJSON_CACHE)
        return gdf, None

    return None, "No se encontraron geometrías (shapefile ni GeoJSON cacheado). Ejecuta los notebooks 02–04."


# --- Carga de datos (fuera de la UI para que el título se renderice rápido) --
panel = None
if RUTA_PANEL.exists():
    try:
        panel = cargar_panel(RUTA_PANEL)
    except Exception as exc:  # archivo corrupto o vacío
        panel = None
        print("Error al leer el panel:", exc)

# --- Interfaz ----------------------------------------------------------------
st.set_page_config(page_title="Empleo y Crimen — Ecuador", layout="wide")
st.title("📊 Empleo y criminalidad en Ecuador (2018–2026)")
st.caption("Panel provincia-trimestre: homicidios intencionales por 100 000 hab. y tasas de "
           "desempleo/subempleo ENEMDU. Fuentes oficiales: Ministerio del Interior e INEC "
           "(descarga 2026-08-14).")

if panel is None:
    st.warning(
        "⚠️ **No se encontró `data/processed/panel_provincia_trimestre.csv`.**\n\n"
        "Ejecuta primero los notebooks **01–03** (o la secuencia completa con "
        "`jupyter nbconvert --to notebook --execute`) para generar el panel, y vuelve a "
        "lanzar `streamlit run app.py`."
    )
    st.stop()

# --- Barra lateral: filtros ---------------------------------------------------
st.sidebar.header("Filtros")

provincias = sorted(panel["provincia"].dropna().unique().tolist()) if "provincia" in panel.columns else []
lista_provincias = ["Todas"] + provincias
provincia_sel = st.sidebar.selectbox("Provincia", lista_provincias)

anios = sorted(panel["anio"].unique().tolist())
anio_min, anio_max = st.sidebar.slider("Rango de años",
                                       min_value=max(ANIO_INICIO, min(anios)),
                                       max_value=min(ANIO_FIN, max(anios)),
                                       value=(max(ANIO_INICIO, min(anios)),
                                              min(ANIO_FIN, max(anios))))

variable_sel = st.sidebar.selectbox("Variable", list(VARIABLES.keys()),
                                    format_func=lambda v: VARIABLES[v])
if variable_sel not in panel.columns:
    st.sidebar.warning(f"La variable «{VARIABLES[variable_sel]}» no está en el panel aún "
                       "(puede faltar el periodo laboral correspondiente).")

# --- Filtrado del panel --------------------------------------------------------
df_filtrado = panel[(panel["anio"] >= anio_min) & (panel["anio"] <= anio_max)].copy()
if provincia_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado["provincia"] == provincia_sel]

# --- 1) Serie de tiempo interactiva (plotly) ------------------------------------
st.subheader("📈 Serie de tiempo")
st.caption("Promedio provincial ponderado; si se selecciona «Todas», se muestra el promedio "
           "de las provincias disponibles (serie nacional aproximada).")

if not df_filtrado.empty and variable_sel in df_filtrado.columns:
    serie = (df_filtrado.groupby("fecha", as_index=False)[variable_sel]
             .mean(numeric_only=True).dropna())
    if not serie.empty:
        import plotly.graph_objects as go
        fig_linea = go.Figure()
        fig_linea.add_trace(go.Scatter(x=serie["fecha"], y=serie[variable_sel],
                                       mode="lines+markers",
                                       name=VARIABLES[variable_sel]))
        fig_linea.update_layout(
            title=f"{VARIABLES[variable_sel]} — {provincia_sel}",
            xaxis_title="Trimestre",
            yaxis_title=VARIABLES[variable_sel],
            template="plotly_white", height=420,
        )
        st.plotly_chart(fig_linea, use_container_width=True)
    else:
        st.info("No hay datos numéricos de la variable seleccionada para el filtro actual.")
else:
    st.info("No hay datos para el filtro seleccionado.")

# --- 2) Mapa coroplético (plotly + shapefile CONALI) ------------------------------
st.subheader("🗺️ Mapa provincial (último trimestre disponible)")

gdf, aviso_geo = cargar_geometrias()
if gdf is not None and "dpa" in panel.columns:
    ultimo_periodo = panel["periodo"].max()
    mapa_data = panel[panel["periodo"] == ultimo_periodo][["dpa", variable_sel]].dropna()
    gdf_map = gdf.merge(mapa_data, on="dpa", how="left")
    gdf_map = gdf_map[gdf_map["dpa"].str.isdigit()]

    if variable_sel in gdf_map.columns:
        # Reproyección a EPSG:4326 (el shapefile CONALI está en UTM 17S) y a plotly
        if gdf_map.crs is not None and gdf_map.crs.to_epsg() != 4326:
            gdf_map = gdf_map.to_crs(epsg=4326)
        gdf_map["lon"] = gdf_map.geometry.centroid.x
        gdf_map["lat"] = gdf_map.geometry.centroid.y
        gdf_map["texto"] = (gdf_map.get("DPA_DESPRO", gdf_map.get("nombre", gdf_map["dpa"]))
                            .astype(str) + "<br>" + VARIABLES[variable_sel] + ": " +
                            gdf_map[variable_sel].round(2).astype(str))

        import plotly.express as px
        fig_mapa = px.choropleth_mapbox(
            gdf_map, geojson=gdf_map.geometry.__geo_interface__,
            locations=gdf_map.index, color=variable_sel,
            hover_name="texto", hover_data={variable_sel: True},
            mapbox_style="carto-positron",
            center={"lat": gdf_map["lat"].mean(), "lon": gdf_map["lon"].mean()},
            zoom=5, opacity=0.75,
            title=f"{VARIABLES[variable_sel]} — trimestre {ultimo_periodo}",
        )
        fig_mapa.update_layout(height=520, margin={"r": 0, "t": 40, "l": 0, "b": 0})
        st.plotly_chart(fig_mapa, use_container_width=True)
    else:
        st.info("La variable seleccionada no tiene datos para el último trimestre.")
else:
    st.info(aviso_geo or "No se encontraron geometrías provinciales.")
    st.caption("Ejecuta los notebooks 02–04 para generar `data/raw/geografia` "
               "(shapefile IGM/CONALI) o `data/processed/geojson_provincias.json`.")

# --- 3) Tabla resumen por provincia-periodo ---------------------------------------
st.subheader("📋 Tabla resumen (provincia × trimestre)")

columnas_tabla = [c for c in ["dpa", "provincia", "periodo", "anio", "trimestre",
                              "tasa_homicidios_100k", "tasa_desempleo", "tasa_subempleo"]
                  if c in df_filtrado.columns]
if columnas_tabla:
    tabla = df_filtrado[columnas_tabla].sort_values(["provincia", "periodo"]
                                                    if "provincia" in columnas_tabla
                                                    else ["dpa", "periodo"])
    st.dataframe(tabla, use_container_width=True, hide_index=True)

    # Descarga del subconjunto filtrado en CSV
    csv_bytes = tabla.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar tabla filtrada (CSV)", data=csv_bytes,
                       file_name="ec_empleo_crimen_filtrado.csv", mime="text/csv")
else:
    st.info("No hay columnas de resumen disponibles en el panel.")

st.caption("Nota: tasa_homicidios_100k = homicidios intencionales × 100 000 / población "
           "proyectada (INEC, revisión 2024). tasas laborales = ENEMDU ponderadas con factor "
           "de expansión. Fuentes oficiales, descarga 2026-08-14.")
