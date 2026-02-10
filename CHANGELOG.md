# Changelog

## v0.2.0 (2026-02-10)

### Visual
- **Columnas adaptativas**: Las columnas Kanban se expanden para llenar el espacio disponible (min 260px, max 400px)
- **Markdown en notas**: Las notas de los tickets se renderizan como Markdown (negritas, italicas, codigo) usando marked.js
- **Sidebar colapsable**: El sidebar se puede colapsar a solo iconos con un boton. El estado se guarda en localStorage
- **Drag-and-drop mejorado**: Las columnas destino se resaltan visualmente al arrastrar un ticket
- **Empty states**: Las columnas vacias muestran "Sin tickets" en lugar de estar completamente vacias
- **Responsive design**: Sidebar se convierte en menu hamburger en movil, paneles se apilan verticalmente
- **Borde de prioridad**: Borde izquierdo de cada card coloreado segun prioridad (rojo=CRITICAL, naranja=HIGH, azul=MEDIUM, gris=LOW)
- **Tailwind compilado**: Se reemplazo el CDN de Tailwind por CSS compilado (carga mas rapida, funciona offline)

### Funcionalidad
- **Eliminar tickets**: Boton "Eliminar" en el modal de detalle con confirmacion
- **Filtrar por prioridad**: Selector de prioridad en la barra superior que filtra server-side
- **Fechas relativas**: Cada card muestra "hace X dias" con la ultima modificacion. El modal muestra fecha de creacion y modificacion
- **Contador de prioridad por columna**: Las cabeceras muestran badges con count de tickets CRITICAL y HIGH
- **Exportar CSV**: Boton "Exportar CSV" descarga todos los tickets en formato CSV
- **Busqueda global**: El buscador ahora busca en ID, titulo y notas (server-side, no en frontend)
- **Tags editables**: El modal de detalle permite ver y editar tags (separados por coma)
- **Links editables**: El modal de detalle permite ver y editar links asociados al ticket (uno por linea)
- **Historial en el modal**: El modal de detalle muestra el historial completo de transiciones de estado
- **Paginacion server-side**: La API soporta parametros `limit` y `offset` para paginacion

### Backend
- **Sesion persistente**: La secret key de sesion se genera una vez y se guarda en `data/.session_key`. Las sesiones sobreviven reinicios del servidor
- **DELETE /api/kanban/tickets/{id}**: Nuevo endpoint para eliminar tickets
- **GET /api/kanban/export-csv**: Nuevo endpoint que genera un CSV descargable
- **Busqueda server-side**: `/api/kanban/tickets?search=X&priority=Y&limit=N&offset=M`
- **Tags y links en PUT**: El endpoint de actualizar ticket ahora acepta `tags` y `links`

### Tests
- 31 tests de integracion cubriendo: delete, search, pagination, priority filter, tags/links, export CSV, columns, history, session persistence

## v0.1.0

- Release inicial con Kanban board, Assistant RAG, Review, Ingest, Settings
- 8 columnas de estado con colores
- Importacion masiva desde CSV
- Chat con streaming SSE
- Modo oscuro
