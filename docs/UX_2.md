# Madrid Data Explorer 2.0

La versión anterior enviaba el texto literal a CKAN y exigía elegir recursos, importarlos, validar uniones y configurar operaciones antes de obtener resultados. Las tablas, la importación y las validaciones existentes se mantienen en las herramientas de análisis. El mapa anterior necesitaba un GeoJSON aportado por el usuario.

1. Interpretar preguntas en español mediante vocabulario temático, territorio y periodo. Combinar recuperación CKAN y ranking explicable.
2. Incorporar cartografía municipal oficial y un mapa que comparta selección y filtros con los gráficos.
3. Organizar el flujo en Explorar, Mapa, Analizar y Catálogo, con ejemplos directos y contexto persistente.
4. Habilitar análisis reproducibles para indicadores verificados y presentar candidatos para preguntas sin un plan seguro.

Streamlit permite conservar el despliegue y el estado por sesión. Un componente de mapa transmite eventos del navegador; las operaciones tabulares y la lógica de búsqueda quedan en Python.

## Cartografía y códigos

La capa contiene los 179 municipios de Madrid. Deriva de las Unidades Administrativas del [WFS INSPIRE del Instituto Geográfico Nacional](https://www.ign.es/wfs-inspire/unidades-administrativas?service=WFS&request=GetCapabilities), obtenidas el 18 de noviembre de 2026. Atribución **Obra derivada de BDLJE CC-BY 4.0 ign.es**. El [CNIG documenta las condiciones CC BY 4.0](https://centrodedescargas.cnig.es/CentroDescargas/catalogo.do?Serie=LILIM).

Se solicitó GeoJSON en EPSG:4326 y se comprobó el orden longitud y latitud. El script de preparación conserva solo las unidades municipales de Madrid y simplifica con tolerancia de 0,00025°, manteniendo la topología de cada polígono. Los límites son actuales y sirven para visualización, no para consultas catastrales ni mediciones precisas.

Para reproducir la descarga, solicita `GetFeature`, versión `2.0.0`, `typeNames=au:AdministrativeUnit`, `outputFormat=application/geo+json`, `srsName=EPSG:4326` y `count=450`. Descarga los cuadrantes con cajas `bbox` en orden oeste,sur,este,norte y sufijo `,EPSG:4326`, definidos por longitudes −4,64, −3,80 y −3,04 y latitudes 40,00, 40,58 y 41,17. Pasa los cuatro archivos devueltos a `python demo_data/build_geometry.py`. La preparación valida geometrías y exige exactamente 179 identificadores distintos.

Los códigos del Instituto de Estadística de Madrid incluyen tres cifras municipales y un dígito de control. El cruce valida esos cuatro caracteres contra el padrón oficial y usa el prefijo provincial 28 más las tres cifras municipales. Las geometrías y los extractos coinciden en los 179 códigos INE. Folium entrega el código de la entidad pulsada al estado de Streamlit mediante streamlit-folium. Esa selección se comparte entre mapa, comparaciones y gráficos temporales.

## Búsqueda y análisis

`discovery.py` interpreta indicadores, ámbitos y referencias temporales. Consulta CKAN en paralelo con términos literales y expansiones temáticas. Deduplica y puntúa coincidencias en títulos, etiquetas, descripciones, cobertura y año cuando el metadato está disponible. `territories.py` solo resuelve automáticamente indicadores con un extracto, fecha y unidad verificados. Para preguntas sin un plan compatible muestra candidatos. En el caso renta–envejecimiento, el cruce reutiliza la validación de municipio y año de la demostración anterior; el análisis estadístico sigue en pandas.

`explore_view.py` presenta los informes y las fichas de búsqueda. `map_view.py` construye el mapa y los gráficos vinculados. El catálogo técnico, la limpieza, las uniones y la IA opcional siguen accesibles desde Catálogo y Analizar. Streamlit guarda las tablas, la pregunta y la selección municipal por sesión.

## Elección del componente

Se mantuvo Plotly para series, rankings y dispersiones. Para el mapa se eligió Folium con streamlit-folium porque devuelve al servidor el evento del polígono pulsado y su tooltip, además de conservar las interacciones de Leaflet para zoom y desplazamiento. PyDeck admite selección en capas seleccionables, pero habría requerido construir en la aplicación la leyenda y el ajuste de vista. El mapa actual clasifica en cuantiles, intervalos iguales o Jenks sin dividir valores idénticos. Las clases y unidades se exportan en el HTML.
