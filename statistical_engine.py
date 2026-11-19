"""Validated statistics. Inference is opt-in and always reports complete cases."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import plotly.express as px

from profiling import CATEGORIES, NUMERIC, TIME

FAMILIES = {
    "Descriptivos": ["Distribución", "Frecuencias"],
    "Correlación y asociación": ["Pearson", "Spearman", "Contingencia y chi-cuadrado"],
    "Comparar grupos": ["t independiente (Welch)", "t pareada", "ANOVA", "Mann–Whitney", "Wilcoxon", "Kruskal–Wallis"],
    "Regresión": ["Lineal simple", "Lineal múltiple", "Logística binaria", "Poisson"],
    "Series temporales": ["Evolución y cambios"],
    "Análisis geográfico": ["Comparación municipal"],
}
PAIRED = {"t pareada", "Wilcoxon"}
GROUPED = {"t independiente (Welch)", "ANOVA", "Mann–Whitney", "Kruskal–Wallis"}
MODELS = set(FAMILIES["Regresión"])


@dataclass
class Result:
    table: pd.DataFrame
    summary: str
    notes: list = field(default_factory=list)
    figure: object = None
    charts: list = field(default_factory=list)


def numeric_values(values):
    return pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)


def compatible(df, roles):
    nums = [c for c, role in roles.items() if c in df and role in NUMERIC and numeric_values(df[c]).count() >= 2]
    varied = [c for c in nums if numeric_values(df[c]).nunique() >= 2]
    cats = [c for c, role in roles.items() if c in df and role in CATEGORIES and 2 <= df[c].nunique() <= 20]
    time = [c for c, role in roles.items() if c in df and role in TIME]
    geo = [c for c, role in roles.items() if c in df and role == "Código municipal"]
    counts = []
    for column in varied:
        values = numeric_values(df[column]).dropna()
        if (values.ge(0) & values.mod(1).eq(0)).all():
            counts.append(column)
    two_groups = [c for c in cats if df[c].nunique() == 2]
    binary = [c for c in df if roles.get(c) in NUMERIC | CATEGORIES and df[c].nunique() == 2]
    return {"numeric": nums, "varied": varied, "category": cats, "time": time, "geo": geo, "binary": binary, "counts": counts, "two_groups": two_groups}


def descriptive(values):
    clean = numeric_values(values).dropna()
    if clean.empty:
        raise ValueError("La variable carece de observaciones numéricas válidas.")
    modes = clean.mode()
    mode = ", ".join(f"{value:g}" for value in modes.head(5)) if clean.duplicated().any() else "Sin moda repetida"
    summary = {
        "Observaciones": len(clean), "Ausentes (%)": 100 * (len(values) - len(clean)) / len(values),
        "Media": clean.mean(), "Mediana": clean.median(), "Moda": mode, "Desviación estándar": clean.std(),
        "Varianza": clean.var(), "Mínimo": clean.min(), "Máximo": clean.max(),
        "Rango intercuartílico": clean.quantile(.75) - clean.quantile(.25),
    }
    summary.update({f"P{p}": clean.quantile(p / 100) for p in (5, 10, 25, 50, 75, 90, 95)})
    table = pd.DataFrame({"Estadístico": summary.keys(), "Valor": list(summary.values())})
    plot_data = clean.rename("Valor").to_frame()
    return Result(table, f"La mediana es {clean.median():.4g} y la media es {clean.mean():.4g}.",
                  [case_note(len(clean), len(values))], px.histogram(plot_data, x="Valor", title="Distribución"),
                  [px.box(plot_data, y="Valor", title="Diagrama de caja")])


def frequencies(values):
    clean = values.astype("string").str.strip().replace("", pd.NA).dropna()
    if clean.empty:
        raise ValueError("La variable carece de categorías observadas.")
    table = clean.astype(str).value_counts().rename_axis("Categoría").reset_index(name="Frecuencia")
    table["Porcentaje válido"] = 100 * table["Frecuencia"] / len(clean)
    return Result(table, f"La categoría más frecuente es {table.iloc[0, 0]}.", [case_note(len(clean), len(values))],
                  px.bar(table.head(20), x="Categoría", y="Frecuencia", title="Frecuencias · hasta 20 categorías"))


def case_note(n, total):
    return f"Se incluyeron {n} observaciones completas y se excluyeron {total - n} filas por datos ausentes o inválidos."


def association(df, test, x, y):
    from scipy import stats

    if x == y:
        raise ValueError("Selecciona dos variables distintas.")
    if test == "Contingencia y chi-cuadrado":
        clean = df[[x, y]].dropna()
        counts = pd.crosstab(clean[x], clean[y])
        if min(counts.shape) < 2 or max(counts.shape) > 20:
            raise ValueError("Se necesitan entre 2 y 20 categorías observadas en cada variable.")
        stat = stats.chi2_contingency(counts, correction=False)
        v = np.sqrt(stat.statistic / (counts.to_numpy().sum() * (min(counts.shape)-1)))
        small = float((stat.expected_freq < 5).mean())
        notes = ["El contraste supone observaciones independientes."]
        if small > .2 or stat.expected_freq.min() < 1:
            notes.append(f"El {100*small:.1f} % de celdas tiene frecuencia esperada menor de 5. Interpreta el valor p con cautela.")
        table = counts.rename_axis("Categoría").reset_index()
        notes.extend([f"χ² = {stat.statistic:.4g} · gl = {stat.dof} · p = {stat.pvalue:.4g}.",
                      case_note(len(clean), len(df))])
        return Result(table, f"La V de Cramér es {v:.3f} (0 indica ausencia de asociación en la tabla).", notes,
                      px.imshow(counts, text_auto=True, title="Frecuencias observadas"),
                      charts=[])
    clean = df[[x, y]].apply(numeric_values).dropna()
    if len(clean) < 3 or min(clean.nunique()) < 2:
        raise ValueError("Se necesitan al menos tres pares completos y variación en ambas variables.")
    method = stats.pearsonr if test == "Pearson" else stats.spearmanr
    answer = method(clean[x], clean[y])
    direction = "positiva" if answer.statistic > 0 else "negativa" if answer.statistic < 0 else "nula"
    label = "lineal" if test == "Pearson" else "monótona de rangos"
    return Result(pd.DataFrame({"Método": [test], "Coeficiente": [answer.statistic], "p": [answer.pvalue],
                                "Observaciones": [len(clean)]}),
                  f"La asociación {label} es {direction}, con coeficiente {answer.statistic:.3f}. No implica causalidad.",
                  [case_note(len(clean), len(df)), "El valor p presupone pares independientes. Revisa atípicos y estructura temporal o espacial."],
                  px.scatter(clean.head(5000), x=x, y=y, title=test))


def group_test(df, test, x, y, *, design_confirmed=False):
    from scipy import stats

    if not design_confirmed:
        raise ValueError("Confirma el diseño de observación antes de ejecutar la prueba.")
    if x == y:
        raise ValueError("Selecciona dos variables distintas.")
    notes = []
    if test in PAIRED:
        clean = df[[x, y]].apply(numeric_values).dropna()
        if len(clean) < 3:
            raise ValueError("Se requieren al menos tres pares completos.")
        a, b = clean[x], clean[y]
        diffs = a - b
        if diffs.nunique() < 2:
            raise ValueError("Las diferencias no presentan variación suficiente.")
        result = stats.ttest_rel(a, b) if test == "t pareada" else stats.wilcoxon(a, b)
        notes.append("Cada fila debe representar el mismo individuo en ambas mediciones. Revisa la normalidad de las diferencias "
                     "para t pareada, o su simetría para Wilcoxon.")
        if test == "t pareada" and stats.shapiro(diffs.head(5000)).pvalue < .05:
            notes.append("Shapiro–Wilk sugiere desviación de la normalidad de las diferencias.")
        chart = px.histogram(diffs.rename("Diferencia").to_frame(), x="Diferencia")
    else:
        clean = df[[x, y]].assign(**{x: numeric_values(df[x])}).dropna()
        groups = list(clean.groupby(y, observed=True)[x])
        two = test in {"t independiente (Welch)", "Mann–Whitney"}
        if len(groups) < 2 or len(groups) > 20 or (two and len(groups) != 2):
            raise ValueError("Se requieren exactamente dos grupos." if two else "Se requieren entre dos y veinte grupos.")
        sample = [values.to_numpy(dtype=float) for _, values in groups]
        if min(map(len, sample)) < 3 or clean[x].nunique() < 2:
            raise ValueError("Cada grupo necesita al menos tres observaciones y debe existir variación.")
        if test in {"ANOVA", "t independiente (Welch)"} and all(np.ptp(values) == 0 for values in sample):
            raise ValueError("No hay variación interna en los grupos.")
        functions = {"t independiente (Welch)": lambda *a: stats.ttest_ind(*a, equal_var=False),
                     "ANOVA": stats.f_oneway, "Mann–Whitney": stats.mannwhitneyu, "Kruskal–Wallis": stats.kruskal}
        result = functions[test](*sample)
        notes.append("Las filas de los grupos deben ser independientes. Una agrupación geográfica o longitudinal puede invalidar el valor p.")
        if test in {"ANOVA", "t independiente (Welch)"}:
            if any(np.ptp(v) > 0 and stats.shapiro(v[:5000]).pvalue < .05 for v in sample):
                notes.append("Shapiro–Wilk sugiere desviación de la normalidad en algún grupo.")
            if test == "ANOVA" and stats.levene(*sample).pvalue < .05:
                notes.append("Levene sugiere varianzas distintas. Interpreta ANOVA con cautela.")
        else:
            notes.append("Las pruebas de rangos comparan distribuciones. Para interpretarlas como diferencias de localización revisa su forma.")
        chart = px.box(clean, x=y, y=x, title="Distribución por grupo")
    return Result(pd.DataFrame({"Prueba": [test], "Estadístico": [result.statistic], "p": [result.pvalue],
                                "Observaciones": [len(clean)]}),
                  f"{test} da un estadístico de {result.statistic:.4g} y un valor p de {result.pvalue:.4g}. "
                  "Interprétalo junto con el diseño y los supuestos.",
                  [case_note(len(clean), len(df)), *notes], chart)


def regression(df, model, response, predictors, exposure=None, *, positive=None):
    import statsmodels.api as sm
    from statsmodels.tools.sm_exceptions import PerfectSeparationError

    columns = [response, *predictors, *([exposure] if exposure else [])]
    if len(set(columns)) != len(columns) or len(predictors) > 10 or not predictors:
        raise ValueError("Elige variables distintas y entre uno y diez predictores.")
    if (model == "Lineal simple" and len(predictors) != 1) or (model == "Lineal múltiple" and len(predictors) < 2):
        raise ValueError("La regresión simple requiere un predictor y la múltiple al menos dos.")
    clean = df[columns].copy()
    for col in columns:
        if model != "Logística binaria" or col != response:
            clean[col] = numeric_values(clean[col])
    clean = clean.dropna()
    if len(clean) < max(6, len(predictors) + 3):
        raise ValueError("Hay pocos casos completos para estimar el modelo.")
    X = clean[predictors].astype(float)
    constant = "Intercepto"
    while constant in X:
        constant += " (modelo)"
    X.insert(0, constant, 1.0)
    if np.linalg.matrix_rank(X) < X.shape[1]:
        raise ValueError("El modelo no es identificable: hay predictores constantes o colineales.")
    y = clean[response]
    if y.nunique() < 2:
        raise ValueError("La respuesta debe tener variación.")
    notes = [case_note(len(clean), len(df)),
             "Los coeficientes son asociaciones condicionadas. Revisa independencia, especificación y observaciones influyentes."]
    extra = None
    try:
        if model == "Logística binaria":
            if y.nunique() != 2 or positive not in y.unique():
                raise ValueError("La respuesta requiere dos clases y una clase positiva elegida.")
            y = y.eq(positive).astype(float)
            if y.value_counts().min() < 3:
                raise ValueError("Se requieren al menos tres casos completos por clase.")
            fitted = sm.Logit(y, X).fit(disp=False, maxiter=100)
            if not fitted.mle_retvals["converged"] or np.abs(fitted.params).max() > 40:
                raise ValueError("La logística no converge de forma fiable o presenta separación.")
            extra = "Odds ratio"
            summary = f"Pseudo-R² de McFadden = {fitted.prsquared:.3f}. La clase positiva es {positive}."
            if y.value_counts().min() < 10 * len(predictors):
                notes.append("Hay pocos casos por clase y predictor. Los intervalos pueden ser inestables.")
        elif model == "Poisson":
            y = y.astype(float)
            if ((y < 0) | (y % 1 != 0)).any():
                raise ValueError("Poisson requiere recuentos enteros no negativos.")
            if exposure and (clean[exposure] <= 0).any():
                raise ValueError("La exposición debe ser estrictamente positiva.")
            offset = np.log(clean[exposure].astype(float)) if exposure else None
            fitted = sm.GLM(y, X, family=sm.families.Poisson(), offset=offset).fit()
            if not fitted.converged:
                raise ValueError("El modelo Poisson no convergió.")
            dispersion = fitted.pearson_chi2 / fitted.df_resid
            summary = f"La dispersión de Pearson es {dispersion:.3f} (cerca de 1 según el modelo Poisson)."
            if dispersion > 1.5:
                notes.append("Posible sobredispersión. Los errores estándar e intervalos Poisson pueden ser demasiado estrechos.")
            if exposure:
                notes.append(f"Se usó el logaritmo de {exposure} como offset de exposición.")
            extra = "Razón de tasas"
        else:
            fitted = sm.OLS(y.astype(float), X).fit(cov_type="HC3")
            summary = f"El modelo explica aproximadamente el {100*fitted.rsquared:.1f} % de la variabilidad observada."
            notes.append(f"R² ajustado = {fitted.rsquared_adj:.3f}. Errores estándar HC3 y gráfico de residuos.")
    except (np.linalg.LinAlgError, PerfectSeparationError) as exc:
        raise ValueError("El modelo no es estimable con los datos y predictores seleccionados.") from exc
    interval = fitted.conf_int().to_numpy()
    table = pd.DataFrame({"Variable": X.columns, "Coeficiente": fitted.params.to_numpy(), "Error estándar": fitted.bse.to_numpy(),
                          "IC 95 % inferior": interval[:, 0], "IC 95 % superior": interval[:, 1], "p": fitted.pvalues.to_numpy()})
    if extra:
        with np.errstate(over="ignore"):
            table[extra] = np.exp(table["Coeficiente"])
            table[f"{extra} · IC inferior"] = np.exp(interval[:, 0])
            table[f"{extra} · IC superior"] = np.exp(interval[:, 1])
    predicted = fitted.fittedvalues if model != "Logística binaria" else fitted.predict(X)
    diag = pd.DataFrame({"Predicción": predicted, "Residuo": y.astype(float) - predicted})
    return Result(table, summary, notes,
                  px.scatter(diag.head(5000), x="Predicción", y="Residuo", title="Diagnóstico · residuos frente a predicción"))


def temporal(df, period, target, role, by=None, window=3):
    if period == target or by in {period, target} or window < 2:
        raise ValueError("Selecciona variables distintas y al menos dos observaciones para la media móvil.")
    cols = [period, target, *([by] if by else [])]
    clean = df[cols].copy()
    clean[target] = numeric_values(clean[target])
    if role == "Año":
        years = numeric_values(clean[period])
        clean[period] = years.where(years.between(1, 9999) & years.mod(1).eq(0)).astype("Int64")
    else:
        clean[period] = pd.to_datetime(clean[period], errors="coerce", format="ISO8601")
    clean = clean.dropna().sort_values(period)
    if len(clean) < 2 or clean.duplicated([period, *([by] if by else [])]).any():
        raise ValueError("Se necesitan al menos dos filas y una fila por periodo y grupo. Filtra los totales o agrega de forma explícita.")
    if not by:
        clean["Serie"] = target
        by = "Serie"
    if clean[by].nunique() > 30:
        raise ValueError("Filtra a un máximo de 30 series antes de comparar.")
    groups = clean.groupby(by, sort=False, observed=True)
    previous = groups[target].shift()
    clean["Cambio absoluto"] = clean[target] - previous
    clean["Cambio (%)"] = 100 * clean["Cambio absoluto"] / previous.where(previous.ne(0))
    clean["Media móvil"] = groups[target].transform(lambda v: v.rolling(window, min_periods=window).mean())
    if role == "Año":
        frequency = "anual"
    else:
        dates = pd.DatetimeIndex(clean[period].drop_duplicates().sort_values())
        frequency = (pd.infer_freq(dates) if len(dates) >= 3 else None) or "irregular o indeterminada"
    spans = groups[target].agg(["first", "last"])
    notes = [case_note(len(clean), len(df)),
             f"Frecuencia {frequency}. Los cambios comparan observaciones consecutivas disponibles y no se interpolan huecos.",
             f"Media móvil de {window} observaciones consecutivas. Cambio porcentual omitido cuando la base es cero."]
    for name, first, last in spans.head(6).itertuples():
        notes.append(f"{name}: cambio entre primera y última observación = {last-first:.4g}.")
    figure = px.line(clean, x=period, y=target, color=by, markers=True, title="Evolución")
    return Result(clean, f"Se comparan {len(spans)} series ordenadas por {period}.", notes, figure,
                  [px.line(clean, x=period, y="Media móvil", color=by, title="Tendencia suavizada")])
