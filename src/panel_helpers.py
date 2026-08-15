# -*- coding: utf-8 -*-
"""panel_helpers.py — modelos de panel para el proyecto ec-empleo-crimen.

Herramientas de modelado (todas comentadas en español):
- efectos_fijos(df, formula, cluster): regresión con efectos fijos de
  provincia y periodo (linearmodels.PanelOLS) con fallback a statsmodels
  OLS con dummies cuando el panel no tiene variación temporal (p. ej. un
  solo corte ENEMDU). Errores agrupados por provincia.
- event_study(df, t0, tratamiento): estudio de eventos en torno a un
  choque (Decreto 111, 2024Q1) con grupo tratado; OLS con efectos fijos
  y errores agrupados; devuelve coeficientes por trimestre relativo.
- control_sintetico(df, tratada, t0, donors): pesos óptimos con
  scipy.optimize.minimize (RMSE pre-tratamiento mínimo) para la
  trayectoria de tasa_homicidios; devuelve pesos, serie sintética y
  brecha (gap) post-tratamiento.

ADVERTENCIA GENERAL: estos modelos estiman ASOCIACIONES condicionales.
La identificación causal requeriría supuestos adicionales (variables
omitidas, ausencia de anticipación, etc.) que este proyecto no puede
verificar con los datos disponibles; ver sección (f) del notebook 04.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# scipy se usa en control_sintetico (optimización de pesos).
from scipy.optimize import minimize


# ---------------------------------------------------------------------------
# 1) Efectos fijos (panel) con fallback a OLS de corte transversal
# ---------------------------------------------------------------------------
def efectos_fijos(
    df: pd.DataFrame,
    formula: str,
    cluster: str = "dpa_provin",
    columna_id: str = "dpa_provin",
    columna_tiempo: str = "periodo",
    regiones: str | None = "region",
) -> dict:
    """Regresión con efectos fijos de provincia y periodo.

    Parámetros
    ----------
    df : panel con al menos las columnas ``columna_id``, ``columna_tiempo``
        y las variables de la fórmula.
    formula : fórmula estilo patsy con columnas EXISTENTES de ``df``
        (p. ej. ``"log_tasa_homicidios ~ tasa_desempleo + tasa_subempleo"``).
        Calcule las transformaciones (p. ej. log) como columnas antes de llamar.
    cluster : columna por la que se agrupan los errores (provincia por defecto).
    columna_id, columna_tiempo : nombres de las dimensiones del panel.
    regiones : si el panel tiene UN solo periodo (corte transversal), los
        efectos fijos de provincia no son identificables (absorberían toda la
        variación); entonces se usa OLS con dummies de región (columna
        ``regiones``) como control aproximado de heterogeneidad no observada.
        Pase None para omitirlas.

    Devuelve
    --------
    dict con: metodo, tabla (coeficientes), n, advertencia e interpretacion.
    """
    df = df.copy()
    n_periodos_por_provincia = df.groupby(columna_id)[columna_tiempo].nunique()
    multiperiodo = (n_periodos_por_provincia > 1).any() and len(df) > n_periodos_por_provincia.max()

    advertencia = ""
    tabla = None
    interpretacion = ""
    metodo = ""
    n = 0
    ok = False

    if multiperiodo:
        # ---- Vía 1: linearmodels.PanelOLS con efectos de entidad y tiempo ----
        try:
            from linearmodels.panel import PanelOLS

            metodo = "PanelOLS (linearmodels): efectos fijos de provincia y periodo"
            pdata = df.set_index([columna_id, columna_tiempo])
            modelo = PanelOLS.from_formula(formula, data=pdata, entity_effects=True, time_effects=True)
            res = modelo.fit(cov_type="clustered", cluster_entity=True)
            tabla = pd.DataFrame(
                {
                    "coef": res.params,
                    "error_est": res.std_errors,
                    "t": res.tstats,
                    "p": res.pvalues,
                }
            )
            n = int(res.nobs)
            ok = True
        except Exception as exc:  # pragma: no cover - fallback ante cualquier error
            advertencia = f"No se pudo estimar PanelOLS ({exc}); se usa OLS con dummies."

    if not ok:
        # ---- Vía 2 (fallback / corte transversal): OLS con dummies ----
        if not multiperiodo:
            advertencia = (
                f"El panel solo tiene UN corte temporal por provincia (periodos "
                f"únicos por provincia: {n_periodos_por_provincia.min()}–"
                f"{n_periodos_por_provincia.max()}). Con un solo corte, los efectos "
                f"fijos de provincia + periodo NO son identificables (absorberían toda "
                f"la variación). Se estima OLS de corte transversal con dummies de "
                f"región como control de heterogeneidad no observada, y errores "
                f"agrupados por provincia (cautela: pocos clústeres)."
            )
        metodo = "OLS (statsmodels) de corte transversal con dummies de región"
        import statsmodels.formula.api as smf

        # Construir la fórmula con dummies de región si la columna existe.
        formula_ols = formula
        if regiones and regiones in df.columns:
            formula_ols = formula + f" + C({regiones})"
            metodo += f" (C({regiones}))"
        modelo = smf.ols(formula_ols, data=df)
        try:
            # Alinear los grupos con las filas realmente usadas por el modelo
            # (patsy descarta filas con NaN antes de estimar).
            grupos = df.loc[modelo.data.row_labels, cluster]
            res = modelo.fit(cov_type="cluster", cov_kwds={"groups": grupos})
        except Exception:
            # Si la agrupación falla (pocos clústeres), errores robustos HC3.
            res = modelo.fit(cov_type="HC3")
            advertencia += " (agrupación por provincia no disponible; se usó HC3)"
        tabla = pd.DataFrame(
            {
                "coef": res.params,
                "error_est": res.bse,
                "t": res.tvalues,
                "p": res.pvalues,
            }
        )
        n = int(res.nobs)
        ok = True

    # ---- Interpretación breve en español (por regresor, sin la constante) ----
    lineas = []
    for nombre in tabla.index:
        if nombre == "Intercept" or nombre.startswith("C("):
            continue
        beta = float(tabla.loc[nombre, "coef"])
        p = float(tabla.loc[nombre, "p"])
        signo = "positiva" if beta > 0 else "negativa"
        sig = "estadísticamente significativa" if p < 0.05 else "NO significativa"
        lineas.append(
            f"  - {nombre}: β = {beta:+.4f} (p = {p:.3f}) → asociación {signo} "
            f"y {sig} al 5%."
        )
    interpretacion = (
        "Interpretación breve (asociación condicional, no causal):\n" + "\n".join(lineas)
    )

    return {
        "metodo": metodo,
        "tabla": tabla,
        "n": n,
        "advertencia": advertencia,
        "interpretacion": interpretacion,
    }


# ---------------------------------------------------------------------------
# 2) Estudio de eventos (event study) en torno a un choque de política
# ---------------------------------------------------------------------------
def event_study(
    df: pd.DataFrame,
    t0: str,
    tratamiento: dict | list | pd.Series,
    columna_id: str = "dpa_provin",
    columna_tiempo: str = "periodo",
    columna_y: str = "tasa_homicidios",
    ventana: tuple[int, int] = (-8, 9),
    trimestre_base: int = -1,
) -> pd.DataFrame:
    """Estudio de eventos con dummies de trimestre relativo × grupo tratado.

    Especificación (estilo DID con efectos fijos):
        y_it = α_i + γ_t + Σ_k β_k · (tratado_i × D_{k,it}) + ε_it
    donde D_k es dummy del trimestre relativo k (k = trimestre − t0) y la
    categoría base es k = ``trimestre_base``. Los β_k miden la desviación del
    grupo tratado respecto a la trayectoria común (controles + FE de tiempo).

    Parámetros
    ----------
    df : panel provincia × trimestre con ``tasa_homicidios`` (u otra y).
    t0 : trimestre del choque, formato 'AAAAQT' (p. ej. '2024Q1', Decreto 111).
    tratamiento : grupo tratado. Puede ser un dict {dpa: bool}, una lista de
        DPAs tratados, o una Series indexada por DPA con valores bool.
    ventana : rango (mín, máx) de trimestres relativos; los valores fuera del
        rango se agrupan en el extremo (binning).
    trimestre_base : trimestre relativo de referencia (β = 0 por construcción).

    Devuelve
    --------
    DataFrame con columnas: rel_q (trimestre relativo), coef, error_est,
    p, ci_lo, ci_hi y n (obs del panel).
    """
    import statsmodels.api as sm

    df = df.copy()
    if isinstance(tratamiento, dict):
        trat = set(k for k, v in tratamiento.items() if v)
    elif isinstance(tratamiento, list):
        trat = {str(x) for x in tratamiento}
    else:  # Series
        trat = set(str(k) for k, v in tratamiento.items() if bool(v))

    # Trimestre relativo: '2024Q1' -> (2024, 1)
    t0_anio, t0_trim = int(t0[:4]), int(t0[-1])
    df["_anio"] = df[columna_tiempo].str[:4].astype(int)
    df["_trim"] = df[columna_tiempo].str[-1].astype(int)
    df["_rel"] = (df["_anio"] - t0_anio) * 4 + (df["_trim"] - t0_trim)

    # Variable dependiente: log(tasa + 1) (estabiliza varianza y asimetría).
    df["_y"] = np.log(df[columna_y].astype(float) + 1.0)
    df["_trat"] = df[columna_id].astype(str).isin(trat).astype(int)

    # Binning de los trimestres relativos extremos.
    kmin, kmax = ventana
    df["_rel_bin"] = df["_rel"].clip(kmin, kmax)

    # Dummies de trimestre relativo interactuadas con el grupo tratado.
    dummies = pd.get_dummies(df["_rel_bin"], prefix="rel", prefix_sep="_")
    inter = dummies.mul(df["_trat"], axis=0).astype(float)
    col_base = f"rel_{trimestre_base}"
    if col_base in inter.columns:
        inter = inter.drop(columns=[col_base])

    # Efectos fijos: provincia + periodo (dummies).
    fe_id = pd.get_dummies(df[columna_id], prefix="p", drop_first=True).astype(float)
    fe_t = pd.get_dummies(df[columna_tiempo], prefix="q", drop_first=True).astype(float)

    X = pd.concat([inter, fe_id, fe_t], axis=1)
    X = sm.add_constant(X)

    modelo = sm.OLS(df["_y"], X)
    res = modelo.fit(cov_type="cluster", cov_kwds={"groups": df[columna_id]})

    # Recuperar coeficientes β_k (base = 0).
    filas = []
    for k in range(kmin, kmax + 1):
        nombre = f"rel_{k}"
        if k == trimestre_base:
            filas.append({"rel_q": k, "coef": 0.0, "error_est": 0.0, "p": 1.0,
                          "ci_lo": 0.0, "ci_hi": 0.0})
        else:
            coef = float(res.params[nombre])
            se = float(res.bse[nombre])
            # IC al 95% con t crítico (n grande -> ~1.96).
            tcrit = 1.96
            filas.append({
                "rel_q": k,
                "coef": coef,
                "error_est": se,
                "p": float(res.pvalues[nombre]),
                "ci_lo": coef - tcrit * se,
                "ci_hi": coef + tcrit * se,
            })

    out = pd.DataFrame(filas)
    out.attrs["n"] = int(res.nobs)
    out.attrs["tratadas"] = sorted(trat)
    out.attrs["t0"] = t0
    return out


# ---------------------------------------------------------------------------
# 3) Control sintético (pesos óptimos con scipy)
# ---------------------------------------------------------------------------
def control_sintetico(
    df: pd.DataFrame,
    tratada: str,
    t0: str,
    donors: list[str] | None = None,
    columna_id: str = "dpa_provin",
    columna_tiempo: str = "periodo",
    columna_y: str = "tasa_homicidios",
) -> dict:
    """Control sintético de la trayectoria de tasa_homicidios.

    Encuentra pesos w_j ≥ 0 (Σ w_j = 1) sobre las provincias donantes que
    minimizan el RMSE pre-tratamiento de la trayectoria de la provincia
    tratada. Luego construye la serie sintética (pre y post) y la brecha
    post-tratamiento (real − sintética).

    Parámetros
    ----------
    df : panel provincia × trimestre.
    tratada : código DPA (str, p. ej. '08' para Esmeraldas).
    t0 : trimestre del tratamiento (los periodos < t0 son pre-tratamiento).
    donors : lista de DPAs donantes (por defecto: todas las demás provincias).

    Devuelve
    --------
    dict con: pesos (Series), sintetica (Series completa), real (Series),
    pre_rmse, gap_post (Series), tratada, t0, donors, n_pre, n_post.
    """
    tratada = str(tratada).zfill(2)
    df = df.copy()
    df[columna_id] = df[columna_id].astype(str).str.zfill(2)

    if donors is None:
        donors = [d for d in sorted(df[columna_id].unique()) if d != tratada]
    donors = [str(d).zfill(2) for d in donors]

    # Matriz ancha: filas = periodos, columnas = provincias.
    ancho = df.pivot_table(index=columna_tiempo, columns=columna_id, values=columna_y)
    ancho = ancho.reindex(sorted(ancho.index))
    pre = ancho[ancho.index < t0]
    post = ancho[ancho.index >= t0]

    if len(pre) < 5:
        raise ValueError(f"Periodo pre-tratamiento muy corto ({len(pre)} trimestres).")

    y_trat_pre = pre[tratada].astype(float).values
    X_don = pre[donors].astype(float).values

    # Función objetivo: RMSE pre-tratamiento.
    def objetivo(w: np.ndarray) -> float:
        sint = X_don @ w
        return float(np.sqrt(np.mean((y_trat_pre - sint) ** 2)))

    # Restricciones: w >= 0 y suma(w) = 1.
    restricciones = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    limites = [(0.0, 1.0)] * len(donors)
    w0 = np.ones(len(donors)) / len(donors)  # punto de partida: pesos iguales

    resultado = minimize(objetivo, w0, method="SLSQP", bounds=limites,
                         constraints=restricciones, options={"maxiter": 2000})
    if not resultado.success:
        print(f"  [aviso] Optimización SLSQP: {resultado.message}")

    pesos = pd.Series(resultado.x, index=donors)
    pesos = pesos[pesos > 1e-6].sort_values(ascending=False)

    # Serie sintética completa (pre + post) y brecha post-tratamiento.
    sintetica = ancho[donors].astype(float).values @ resultado.x
    sintetica = pd.Series(sintetica, index=ancho.index, name="sintetica")
    real = ancho[tratada].astype(float)

    pre_rmse = float(np.sqrt(np.mean((real[pre.index] - sintetica[pre.index]) ** 2)))
    gap_post = real[post.index] - sintetica[post.index]

    return {
        "pesos": pesos,
        "sintetica": sintetica,
        "real": real,
        "pre_rmse": pre_rmse,
        "gap_post": gap_post,
        "tratada": tratada,
        "t0": t0,
        "donors": donors,
        "n_pre": len(pre),
        "n_post": len(post),
    }
