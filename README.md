# Madrid Data Explorer · DATAMAD 2026

Aplicación Streamlit en español para descubrir, combinar y analizar datos abiertos de la Comunidad de Madrid. Incluye tres demostraciones reproducibles con extractos oficiales.

## Explora Madrid con una pregunta

- **Explorar** interpreta preguntas en español y ordena fuentes del catálogo. Para los indicadores validados, abre directamente un mapa, ranking, serie histórica, resumen o cruce.
- **Mapa** colorea los 179 municipios con límites oficiales del IGN. Busca o pulsa hasta seis municipios, cambia indicador, año, colores y clasificación (cuantiles, intervalos iguales o Jenks), consulta su posición y evolución, y descarga el mapa o sus datos.
- **Analizar** reúne preparación, uniones, análisis estadístico, gráficos y asistente opcional. Permite crear mapas de cualquier tabla cargada con ubicaciones utilizables.
- **Catálogo** muestra solo la selección auditada para mapas: búsqueda y filtros sobre el índice local, selección múltiple e importación de archivos.

La portada incluye un buscador central y accesos temáticos a población, economía, empleo, salud, educación, vivienda y transporte. Los informes muestran primero la respuesta, sus indicadores y una visualización con vistas intercambiables. Los filtros y descargas siguen disponibles junto a cada informe. Desde Explorar puedes abrir cinco consultas preparadas con datos oficiales: renta por habitante, envejecimiento, evolución del paro registrado, crecimiento poblacional y relación entre renta y envejecimiento. Los extractos permiten ejecutar esos ejemplos sin credenciales ni consultas CKAN. El padrón cubre 2015–2025. El crecimiento se calcula como variación porcentual entre los extremos con datos para cada municipio.

La recuperación temática funciona con un vocabulario configurable en Python. Un tema, territorio, unidad o año sin análisis validado puede devolver fichas relacionadas para explorar. La búsqueda del catálogo funciona con un índice local; las descargas oficiales y los recursos Leaflet del mapa necesitan conexión. La selección municipal es compartida por los informes y el mapa dentro de la sesión. Consulta [el diseño 2.0, los códigos y la licencia cartográfica](docs/UX_2.md).

## Estudio estadístico 3.0

En **Analizar → Estudio estadístico**, cada tabla tiene un diagnóstico, un informe exploratorio y recomendaciones revisables de limpieza. Las correcciones crean versiones comparables con el original. El estudio propone análisis por rol de variable y ejecuta los contrastes y regresiones solo al pulsar **Ejecutar análisis**. Puedes descargar datos, resultados, gráficos e informes HTML. El tema oscuro también se aplica a los mapas y las visualizaciones. Consulta [la guía técnica y las limitaciones estadísticas](docs/MDE_3.md).

## Ejecutar en macOS o Linux

Usa Python 3.11 para reproducir la configuración de CI y Community Cloud. El entorno local también admite Python 3.10.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

La aplicación abre en `http://localhost:8501`. La búsqueda oficial requiere Internet. La importación, las demostraciones incluidas y el análisis manual funcionan con archivos locales.

## Flujo de trabajo

1. En **Catálogo**, busca por tema, revisa los metadatos y selecciona uno o varios recursos. Los resultados y filtros se calculan sobre los datasets admitidos para mapas. También puedes importar CSV, TSV, XLSX, XLS o JSON tabular.
2. En **Analizar → Preparar y combinar tablas**, revisa las primeras 100 filas, los valores faltantes y los duplicados. Puedes convertir números y fechas, normalizar nombres y categorías, o quitar duplicados mediante una transformación confirmada.
3. En **Combinar tablas**, elige claves equivalentes en el mismo orden. Para datos municipales longitudinales, usa código municipal y periodo si ambos son comparables. Previsualiza, revisa coincidencias y cardinalidad, y confirma para guardar. Puedes cruzar el resultado con más tablas o deshacer la última operación.
4. En **Analizar → Resultados y gráficos**, selecciona una operación manual o formula una pregunta si la IA está configurada. Los resultados incluyen estadísticas, gráficos cuando corresponden, CSV y un JSON de metodología. Para capas alternativas se puede aportar un GeoJSON municipal WGS84.

## Demostraciones

Los ejemplos de economía y mercado laboral se pueden abrir en Explorar. La colección original, que incluye el cruce sanitario, está en **Más demostraciones** antes de iniciar una búsqueda. Los extractos se obtuvieron el 18 de noviembre de 2026 y conservan los códigos de territorio publicados, de cuatro cifras con dígito de control. Para regenerarlos desde los datos oficiales, ejecuta `python demo_data/build.py`. La publicación de origen puede actualizar valores históricos.

| Ejemplo | Selección y análisis | Fuentes oficiales |
| --- | --- | --- |
| Economía y demografía | Municipios en 2024. Renta disponible bruta per cápita y porcentaje de población de 65 años y más. Cruce por código y año, dispersión y Pearson sobre pares completos. | [Renta municipal](https://datos.comunidad.madrid/dataset/irpf_indicador_renta), [Envejecimiento](https://datos.comunidad.madrid/dataset/grado_envejecimiento_por_edad) |
| Mercado laboral | Municipios en 2018–2025. Serie de paro registrado y variación entre los extremos en personas. Una fila por código y año. Los recuentos dependen del tamaño municipal. | [Paro registrado](https://datos.comunidad.madrid/dataset/302038) |
| Salud y territorio | Municipios en 2024. Población de 65 años y más frente a consultorios locales y centros de salud por 10.000 habitantes. Cruce por código y año, dispersión y Pearson. La tasa puede ser elevada en municipios pequeños y no mide accesibilidad. | [Centros sanitarios](https://datos.comunidad.madrid/dataset/centros_sanitarios_por_tipo), [Envejecimiento](https://datos.comunidad.madrid/dataset/grado_envejecimiento_por_edad) |

En los extractos, el cruce de renta obtuvo r = −0,109 y el sanitario r = 0,601, ambos con 179 municipios. Entre 2018 y 2025 se registraron 3.349 personas menos en Alcalá de Henares, 2.768 menos en Alcorcón y 4.323 menos en Móstoles.

Los dos cruces son descriptivos, sin ponderación de población ni ajuste por variables de confusión. Los valores de renta protegidos por secreto estadístico se conservan como faltantes. Las atribuciones y archivos originales figuran en [demo_data/sources.json](demo_data/sources.json).

## IA opcional

Configura `OPENAI_API_KEY` como variable de entorno o en `.streamlit/secrets.toml`. `MDE_AI_MODEL` selecciona el modelo y `MDE_AI_BASE_URL` permite un proveedor compatible con la API Responses y respuestas JSON. [.env.example](.env.example) enumera las variables, que deben exportarse en el entorno para que la aplicación las lea. La aplicación comparte con el proveedor la pregunta y el esquema de hasta 100 columnas. Cada petición ejecuta una operación sobre la tabla activa y respeta los filtros aplicados en la interfaz.

## Pruebas

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest -q
python -m pip check
```

Las pruebas habituales no requieren Internet ni credenciales. Para verificar CKAN y una descarga real ejecuta `MDE_RUN_INTEGRATION=1 python -m pytest -q -m integration`. CI instala las dependencias en Python 3.11 y ejecuta Ruff y pytest. Consulta la [arquitectura y sus límites](docs/ARCHITECTURE.md) para ver responsabilidades y decisiones.

## Desplegar en Streamlit Community Cloud

1. Publica en GitHub una rama que contenga estos archivos. Mantén fuera del repositorio los secretos y el entorno virtual.
2. En [Streamlit Community Cloud](https://share.streamlit.io/), crea una aplicación desde esa rama. Selecciona `app.py` y Python 3.11 en los ajustes avanzados.
3. Configura `OPENAI_API_KEY` en **Secrets** si vas a activar la IA y limita el gasto del proveedor para una app pública. Puedes desplegar sin clave.
4. Verifica en la URL que carguen Inicio, una demostración y una búsqueda oficial.

La capa municipal incorporada usa límites actuales simplificados. Los mapas de otras capas dependen del GeoJSON aportado y de sus códigos. Para comparar fuentes, comprueba definiciones, unidades y denominadores antes de interpretar un resultado. Los recursos alojados fuera de los dominios admitidos pueden incorporarse mediante importación manual.

### Mapas de datasets cargados

En **Mapa → Dataset del mapa**, elige una tabla del catálogo, importada o derivada. También está disponible en **Analizar → Resultados y gráficos → Crear mapa de este dataset**.

Para empezar desde una sesión vacía, pulsa **Mapa → Crear mapa de otro dataset**, busca un conjunto en el catálogo, selecciona un recurso y pulsa **Ver en mapa**. La tabla se carga y su mapa se abre directamente. La selección del dataset y sus filtros se conservan al cambiar de página. Los cinco indicadores verificados siguen disponibles como opción independiente.

- Municipios de Madrid: códigos INE, códigos Almudena, códigos locales de tres dígitos y nombres municipales (incluidas tildes y artículos). Se pueden seleccionar las columnas manualmente.
- Indicadores numéricos o recuentos de registros; filtros por periodo y categoría. Las filas repetidas exigen una agregación explícita para los indicadores; el recuento cuenta registros, no entidades únicas.
- Puntos: latitud y longitud WGS84, con validación de rangos y decimales con coma. Se muestran hasta 10.000 puntos y se exportan todas las ubicaciones válidas.
- Descargas de mapas HTML y datos CSV. Se informa de las ubicaciones excluidas.

Las tablas sin ubicación requieren una unión geográfica. Las direcciones no se geocodifican y las coordenadas UTM no se convierten automáticamente. Para distritos, barrios u otras áreas, utiliza la carga de geometrías propias en Resultados y gráficos. No se asignan límites municipales a esas áreas.

### Catálogo restringido a mapas

La revisión del catálogo del 6 de noviembre de 2026 comprende 2.275 datasets. Se comprobaron muestras oficiales de hasta 100 filas por recurso de los 600 candidatos geográficos el 25 de noviembre de 2026. Se publican **372 datasets**: **364 indicadores municipales, 6 directorios para recuentos municipales y 2 datasets de puntos**. La lista inicial aparece al entrar en Catálogo. Explorar utiliza la misma selección.

La admisión requiere al menos dos municipios o ubicaciones distintas y un 80 % de ubicaciones reconocidas en la muestra. Los indicadores requieren valores numéricos; los identificadores no cuentan como indicadores. Las tablas estadísticas filtran el ámbito municipal, el periodo y cada dimensión antes de mostrar el valor (no el recuento de filas). Los directorios cuentan registros, no necesariamente establecimientos únicos. Los puntos requieren coordenadas geográficas compatibles. Los totales regionales, encuestas sin metodología adicional, geometrías no soportadas y recursos sin evidencia suficiente quedan excluidos; esto no significa que nunca puedan mapearse con preparación adicional.

Solo se ofrecen los recursos comprobados, dentro de los límites conocidos de tamaño, filas y celdas. Al descargar se comprueban otra vez las columnas, valores y ubicaciones. La muestra no garantiza la corrección de cada fila ni que el recurso siga disponible. Los metadatos son una instantánea fechada: los datasets nuevos o modificados requieren reconstruir el índice, no se admiten automáticamente.

- Índice publicado: `catalog_data/map_catalog.json`.
- Decisión y motivo de inclusión/exclusión de cada dataset: `catalog_data/map_catalog_audit.json`.
- Para actualizar: ejecutar `scripts/audit_map_catalog.py SNAPSHOT --cache /tmp/mde-map-audit-nuevo` y después `scripts/build_map_catalog.py SNAPSHOT --cache /tmp/mde-map-audit-nuevo` con el Python del entorno virtual. Usar una carpeta de caché nueva para repetir las comprobaciones de red. El snapshot debe tener la estructura del catálogo de metadatos completo. Las importaciones manuales siguen disponibles.
