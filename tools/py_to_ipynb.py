# -*- coding: utf-8 -*-
"""py_to_ipynb.py — Convierte fuentes estilo jupytext a notebooks .ipynb.

Formato esperado (convención jupytext ligera):
  # %% [markdown]   -> inicio de celda markdown
  # %%              -> inicio de celda de código
  Cualquier línea antes del primer marcador se trata como markdown (encabezado).
Uso: python py_to_ipynb.py entrada.py salida.ipynb
"""
import json
import sys
import pathlib


def convertir(py_path, out_path):
    lineas = pathlib.Path(py_path).read_text(encoding="utf-8").splitlines()
    celdas = []
    actual = None  # {'tipo': 'markdown'|'code', 'lineas': []}

    def vaciar():
        nonlocal actual
        if actual is None:
            return
        fuente = "\n".join(actual["lineas"])
        if actual["tipo"] == "markdown":
            celdas.append({"cell_type": "markdown", "metadata": {}, "source": fuente})
        else:
            celdas.append({"cell_type": "code", "execution_count": None,
                           "metadata": {}, "outputs": [], "source": fuente})
        actual = None

    for linea in lineas:
        limpia = linea.rstrip()
        if limpia.startswith("# %% [markdown]"):
            vaciar()
            actual = {"tipo": "markdown", "lineas": []}
            continue
        if limpia.startswith("# %%"):
            vaciar()
            actual = {"tipo": "code", "lineas": []}
            continue
        if actual is None:
            if limpia.strip() in ("", ","):
                continue
            actual = {"tipo": "markdown", "lineas": []}
            actual["lineas"].append(linea)
        else:
            actual["lineas"].append(linea)
    vaciar()

    nb = {
        "cells": celdas,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.13"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    pathlib.Path(out_path).write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{py_path} -> {out_path}: {len(celdas)} celdas")


if __name__ == "__main__":
    convertir(sys.argv[1], sys.argv[2])
