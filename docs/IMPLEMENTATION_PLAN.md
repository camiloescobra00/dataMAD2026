# Plan de implementación

1. **P0.** Verificar el entorno y el endpoint CKAN, corregir las colisiones de columnas en uniones sucesivas, conservar las claves y limitar el volumen antes de materializar cruces.
2. **P0.** Separar importación, calidad y análisis. Incorporar pruebas locales reproducibles para entradas inválidas, valores faltantes y cruces múltiples.
3. **P1.** Incorporar navegación, filtros, selección múltiple, confirmación de cruces, historial, exportación y planificación analítica opcional con IA.
4. **P1.** Verificar arranque y flujos, fijar dependencias y configurar CI y Community Cloud.
5. **P2.** Validar datos oficiales para demostraciones y geometrías municipales.

La auditoría inicial encontró colisiones por sufijos e indicadores de unión, omisión silenciosa de líneas CSV, soporte XLS anunciado sin motor y respuestas de IA sin ejecución verificable. El entorno virtual inicial carecía de pytest. El repositorio local carece de remoto configurado.
