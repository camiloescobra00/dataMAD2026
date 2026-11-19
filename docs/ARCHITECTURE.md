# Arquitectura

- **Interfaz.** `app.py` navega por Explorar, Mapa, Analizar y Catálogo. Cada sesión conserva sus tablas, pregunta, selección municipal y preferencias de mapa en memoria. Una unión o limpieza añade una tabla derivada y una entrada de historial. Deshacer retira la última derivación.
- **Catálogo.** `catalog.py` consulta CKAN y restringe descargas a HTTPS de los dominios admitidos. Valida el destino de cada redirección. La caché de diez minutos almacena únicamente resultados públicos de búsqueda y permite 48 entradas. Los ficheros privados quedan en la sesión.
- **Datos.** `data_tables.py` importa recursos, conserva códigos textuales y separa limpieza, validación y exportación. Las exportaciones previenen la interpretación de celdas como fórmulas, anteponiendo un apóstrofo a texto potencialmente activo. En Excel, un cero que solo existe en el formato visual puede perderse durante la importación. Para esos códigos usa una celda de texto o un CSV.
- **Uniones.** `joins.py` estima el volumen antes de materializar el resultado. Conserva las claves del mismo nombre, asigna nombres únicos a otras colisiones y usa claves temporales que excluyen coincidencias de valores faltantes. La confirmación de compatibilidad territorial, temporal y semántica corresponde al usuario.
- **Análisis.** `analytics.py` valida planes, calcula en pandas y genera figuras Plotly. `assistant.py` pide únicamente un plan al proveedor opcional. Le envía la pregunta, nombres de variables e indicadores de tipo numérico. Los identificadores permitidos y operaciones se validan localmente. El resultado, método, filtros y fuentes se construyen en la aplicación.
- **Descubrimiento.** `discovery.py` combina expansiones temáticas y consultas CKAN, puntúa metadatos y diversifica comparaciones. `territories.py` restringe el análisis automático a indicadores validados y `explore_view.py` presenta resultados y fuentes candidatas.
- **Cartografía.** `map_view.py` usa Folium y su componente Streamlit para recibir los clics sobre la capa IGN de 179 municipios. Plotly se utiliza para los gráficos analíticos y su exportación HTML. `maps.py` cruza los códigos textuales con geometrías GeoJSON incorporadas por el usuario. Requiere una observación por código y no transforma el sistema de coordenadas.
- **Demostraciones.** `demo_data/build.py` reconstruye los extractos versionados. El archivo de fuentes registra los CSV y sus licencias. `demos.py` ejecuta los cruces y gráficos desde los extractos.

## Límites operativos

Los ficheros están limitados a 15 MB, 150.000 filas, 300 columnas y 1,5 millones de celdas. Los libros XLSX tienen un tope descomprimido de 50 MB. Una unión acepta hasta 250.000 filas y 3 millones de celdas estimadas. Cada sesión admite ocho tablas y cuatro millones de celdas en total. Estos son límites de volumen, no garantías de memoria para texto de gran tamaño. La sesión es temporal.

Cada petición a CKAN usa timeouts de 4 segundos de conexión y 12 segundos de lectura, y un reintento para errores transitorios seleccionados. La capa de carga informa de recursos inaccesibles e importaciones fallidas.

El [estudio 3.0](MDE_3.md) amplía el análisis con perfiles, limpieza versionada, contrastes y modelos deterministas.
