"""Operaciones analíticas deterministas compartidas por la interfaz y el asistente."""
import math

import pandas as pd
import plotly.express as px

OPERATIONS = {
    "summary": "Resumen y percentiles", "frequency": "Frecuencias",
    "ranking": "Ranking por media", "group": "Comparación por grupos",
    "correlation": "Correlación de Pearson", "series": "Serie temporal por media",
    "regression": "Regresión lineal simple", "outliers": "Atípicos (1,5 × RIC)",
    "scatter": "Dispersión", "histogram": "Histograma", "box": "Boxplot",
}
NEEDS_Y = {"ranking", "group", "series", "correlation", "regression", "scatter"}
NEEDS_NUMERIC_X = {"summary", "outliers", "histogram", "box", "correlation", "regression", "scatter"}


def validate_plan(plan, df):
    if not isinstance(plan, dict) or set(plan) != {"operation", "x", "y"}:
        raise ValueError("El plan debe indicar operación y variables.")
    operation, x, y = (plan[k] for k in ("operation", "x", "y"))
    if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(x, str) or x not in df:
        raise ValueError("Operación o variable no disponible.")
    if operation in NEEDS_Y:
        if not isinstance(y, str) or y not in df or x == y:
            raise ValueError("Selecciona dos variables distintas.")
    elif y is not None:
        raise ValueError("Esta operación solo admite una variable.")
    numeric_columns = set(df.select_dtypes(include="number").columns)
    if (operation in NEEDS_NUMERIC_X and x not in numeric_columns) or (y and y not in numeric_columns):
        raise ValueError("La operación requiere variables numéricas. Puedes convertirlas en Espacio de trabajo.")
    return operation, x, y


def analyze(df, plan):
    operation, x, y = validate_plan(plan, df)
    df = df.reset_index(drop=True)
    data = df[[x, y] if y else [x]].replace([math.inf, -math.inf], float("nan")).dropna()
    if data.empty:
        raise ValueError("No quedan observaciones completas para este análisis.")
    # Standardized internal labels avoid collisions with column names from datasets.
    data.columns = ["x", "y"] if y else ["x"]
    notes = [f"{len(data):,} observaciones completas de {len(df):,} filas filtradas."]
    figure = None
    if operation in {"summary", "histogram", "box"}:
        result = data["x"].describe(percentiles=[.05, .25, .5, .75, .95]).rename(x).rename_axis(
            "Estadístico").reset_index()
        notes.append(f"Media de {x}: {data['x'].mean():.4g}. Mediana: {data['x'].median():.4g}.")
        if operation == "histogram":
            figure = px.histogram(data, x="x", labels={"x": x}, title=f"Distribución de {x}")
        if operation == "box":
            figure = px.box(data, y="x", labels={"x": x}, title=f"Boxplot de {x}")
    elif operation == "frequency":
        result = data["x"].value_counts().rename_axis("Categoría").reset_index(name="Frecuencia")
        notes.append(f"Categoría más frecuente: {result.iloc[0, 0]} ({result.iloc[0, 1]:,} observaciones).")
        figure = px.bar(result.head(30), x="Categoría", y="Frecuencia", title=f"Frecuencias de {x} · hasta 30")
    elif operation in {"ranking", "group", "series"}:
        if operation == "series":
            period = data["x"]
            if not pd.api.types.is_numeric_dtype(period) and not pd.api.types.is_datetime64_any_dtype(period):
                if period.astype("string").str.fullmatch(r"[0-9]{4}").all():
                    data["x"] = period.astype(int)
                else:
                    raise ValueError("Para una serie temporal selecciona un año numérico o convierte la fecha.")
        result = data.groupby("x", observed=True)["y"].agg(Media="mean", Observaciones="count").reset_index()
        result = result.rename(columns={"x": "Grupo"})
        notes.append("Media aritmética sin ponderar. Comprueba unidades y denominadores.")
        if operation == "series":
            figure = px.line(result, x="Grupo", y="Media", markers=True, title=f"Evolución de {y}",
                             labels={"Grupo": x, "Media": f"Media de {y}"})
        else:
            result = result.sort_values("Media", ascending=False)
            notes.append(f"Mayor media: {result.iloc[0, 0]} ({result.iloc[0, 1]:.4g}).")
            figure = px.bar(result.head(30), x="Grupo", y="Media", title=f"Media de {y} por {x} · hasta 30",
                            labels={"Grupo": x, "Media": f"Media de {y}"})
    elif operation == "outliers":
        q1, q3 = data["x"].quantile([.25, .75])
        margin = 1.5 * (q3 - q1)
        mask = (data["x"] < q1 - margin) | (data["x"] > q3 + margin)
        result = df.loc[mask.index[mask]]
        figure = px.box(data, y="x", points="outliers", labels={"x": x}, title=f"Atípicos de {x}")
        notes.append(f"{len(result):,} observaciones fuera del intervalo. Límites de Tukey: {q1-margin:.4g} y {q3+margin:.4g}. Revisa el contexto de los valores señalados.")
    else:
        notes.append("La asociación estadística no permite inferir causalidad.")
        labels = {"x": x, "y": y}
        if operation == "scatter":
            result = data.set_axis([x, y], axis=1).reset_index(drop=True)
            figure = px.scatter(data.head(10_000), x="x", y="y", labels=labels, title=f"{y} frente a {x} · hasta 10.000 puntos")
        else:
            if len(data) < 2 or data["x"].nunique() < 2 or data["y"].nunique() < 2:
                raise ValueError("Se requieren al menos dos pares con variación en ambas variables.")
            corr = data["x"].corr(data["y"])
            result = pd.DataFrame({"Pearson r": [corr], "Pares": [len(data)]})
            notes.append(f"Correlación de Pearson entre {x} y {y}: {corr:.4g}.")
            if operation == "correlation":
                matrix = data.corr().set_axis([x, y], axis=0).set_axis([x, y], axis=1)
                figure = px.imshow(matrix, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                                   title="Matriz de correlación de Pearson")
            else:
                slope = data["x"].cov(data["y"]) / data["x"].var()
                intercept = data["y"].mean() - slope * data["x"].mean()
                result = result.assign(Pendiente=slope, Intercepto=intercept, R2=corr**2)
                figure = px.scatter(data.head(10_000), x="x", y="y", labels=labels,
                                    title=f"Ajuste lineal de {y} sobre {x} · hasta 10.000 puntos")
                endpoints = [data["x"].min(), data["x"].max()]
                figure.add_scatter(x=endpoints, y=[intercept + slope * v for v in endpoints],
                                   mode="lines", name="Ajuste lineal")
                notes.append(f"Pendiente estimada: {slope:.4g} unidades de {y} por unidad de {x}. " 
                             "Mínimos cuadrados ordinarios, sin ajuste por variables de confusión.")
    return result, figure, notes
