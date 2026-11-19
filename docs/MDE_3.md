# Implementación 3.0

1. Unificar tema oscuro en Streamlit, gráficas, mapa e informes.
2. Perfilar tablas al incorporarlas y conservar el perfil y las correcciones semánticas por sesión.
3. Presentar recomendaciones revisables y registrar las transformaciones como versiones derivadas.
4. Incorporar análisis deterministas con validaciones explícitas y exportaciones reproducibles.
5. Integrar fichas del catálogo y verificar flujos, supuestos y resultados numéricos.

La interfaz anterior disponía de estadísticas básicas y de transformaciones manuales. Las herramientas de 3.0 aprovechan los mismos importadores, fuentes, espacio de trabajo y controles de exportación.

## Uso

Abre una ficha del Catálogo, elige un recurso y pulsa **Explorar este dataset**, **Analizar** o **Combinar con otro dataset**. En **Analizar → Estudio estadístico** encontrarás el diagnóstico y un informe exploratorio. Puedes corregir el rol de cada columna. Un año sigue siendo un periodo anual y los códigos municipales se conservan como texto.

En **Limpieza recomendada**, selecciona una sugerencia y compara la vista previa. Aplicar crea una versión con procedencia e historial. El original continúa disponible. Deshacer vuelve a la versión anterior. Las alertas sobre unidades, valores ausentes, rangos y totales requieren una decisión informada y no cambian los datos.

## Módulos y criterio estadístico

- `dataset_cards.py` conserva lo que publica CKAN y avisa cuando falta una ficha, un campo o una definición. El diagnóstico estructural procede del archivo.
- `profiling.py` infiere roles por nombre y contenido y propone correcciones sin modificar la tabla durante el diagnóstico.
- `statistical_engine.py` separa compatibilidad, estadística descriptiva, asociación, contrastes, ajuste y series. Usa SciPy para contrastes y statsmodels para regresión. Reporta casos completos, requisitos, supuestos y advertencias. Las regresiones lineales usan errores estándar HC3. Poisson admite exposición y muestra dispersión de Pearson.
- `analysis_workspace.py` orquesta la selección de parámetros, las versiones y el análisis y comparaciones en el mapa. Las pruebas de grupos requieren confirmar el diseño. Los años y códigos se excluyen de las variables numéricas del estudio salvo que el usuario cambie el rol.
- `reports.py` genera un HTML con tabla, gráficos y metadatos de procedencia. La exportación CSV usa la protección contra fórmulas de la aplicación.
- `.streamlit/config.toml` y `interface.py` contienen el tema general. `map_view.py` aplica el tema al lienzo Leaflet y calcula el encuadre con todas las geometrías. La capa IGN se dibuja sobre fondo oscuro sin teselas externas ni nuevas condiciones de atribución.

El diagnóstico de supuestos es parcial. El estudio no modela autocorrelación espacial o longitudinal, ni aplica corrección automática por comparaciones múltiples. Una advertencia de normalidad o dispersión ayuda a interpretar el resultado y no demuestra que un modelo sea apropiado. La fuente y las unidades deben revisarse antes de combinar indicadores.
