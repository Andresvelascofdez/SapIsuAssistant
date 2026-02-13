# Changelog

## v0.3.0 (2026-02-13)

### Finance Module (NEW)

- **Settings**: Tasa impositiva por defecto, datos de empresa (nombre, direccion, CIF, email, telefono, datos bancarios)
- **Categorias de gasto**: CRUD completo, reordenar, activar/desactivar, proteccion contra borrado si tiene gastos
- **Gastos**: CRUD con periodo, categoria, importe, comerciante, notas, documento adjunto, flag "documento no requerido"
- **Facturas**: CRUD con lineas de detalle, calculo automatico de subtotal/IVA/total, estados (PENDING/PAID)
- **Generacion de PDF**: Facturas generadas como PDF con datos de empresa, cliente, lineas y totales
- **Resumen financiero**: Vista mensual y anual con ingresos, gastos, beneficio, impuestos y neto
- **Documentos**: Subida, descarga, hash SHA256, vinculacion a gastos (desvinculacion automatica al borrar)
- **OCR**: Extraccion de texto desde PDF e imagenes, deteccion de importes y fechas (formato europeo incluido)
- **Exportacion CSV**: Gastos y facturas exportables en formato CSV
- **Bulk import gastos**: Subida multiple de PDFs/imagenes con deteccion automatica de importes via OCR
- **Bulk import facturas**: Subida multiple de PDFs/imagenes con creacion automatica de facturas
- **Mark All Paid**: Boton para marcar todas las facturas pendientes como pagadas de una vez
- **Net - Personal / Net - Business**: Doble columna en resumen financiero:
  - Net - Personal = ingresos - impuestos (gastos son personales, no se deducen)
  - Net - Business = ingresos - gastos - impuestos (vision empresarial)
- **Navegacion por pestanas**: Tabs consistentes (Summary, Expenses, Invoices, Settings) en todas las paginas finance

### Finance - UI / Dark Mode

- **Alineacion izquierda**: Todas las columnas de tablas (headers y celdas) alineadas a la izquierda
- **Dark mode mejorado**: Texto blanco y colores claros en modo oscuro para legibilidad
- **CSS suplementario**: Utilidades Tailwind faltantes anadidas en base.html (text-left, dark:text-sap-400, dark:text-amber-400, grid responsive, etc.)

### Kanban - Mejoras

- **ticket_id editable**: El identificador verde es editable en creacion y edicion, con validacion de unicidad
- **Campo descripcion**: Los tickets ahora tienen un campo de descripcion ademas de las notas
- **Alertas de tickets stale**: Indicador visual de tickets sin movimiento (dias configurables), filtra solo NO_ANALIZADO y EN_PROGRESO
- **Modales unificados**: Creacion y edicion usan el mismo modal con tags y links
- **Cliente en modal**: Dropdown de cliente visible en modal de detalle/edicion
- **Drag-drop mejorado**: client_code incluido en respuestas API para movimiento fiable entre columnas
- **History/Delete con client_code**: Endpoints aceptan client_code como query param

### Tests - Suite Comprehensiva

- **191 nuevos tests** en `tests/test_comprehensive.py` (410 tests totales en 3 archivos)
- Cobertura: Ingest API, Review API, Settings API, ClientManager, KB Repository, Chat Repository, Kanban Repository, Kanban API, Finance edge cases, E2E workflows, validacion de inputs, error handling
- Tests E2E: ciclo de vida completo de tickets, gastos, facturas, chat, aislamiento multi-cliente

## v0.2.3 (2026-02-11)

### Bugfix - Creacion de tickets Kanban

- **Error handling en frontend**: `createTicket()`, `saveTicket()` y `confirmDeleteTicket()` ahora verifican `resp.ok` y muestran errores al usuario en lugar de fallar silenciosamente
- **Validacion robusta de cliente en backend**: `_get_kanban_repo_for_client` ahora valida el cliente via ClientManager, retorna errores claros y auto-crea directorios si faltan

## v0.2.2 (2026-02-11)

### Kanban - Creacion de tickets

- **Boton "+" por columna**: Cada cabecera de columna muestra un boton "+" (hover) para crear tickets directamente en esa columna
- **Cliente obligatorio**: El modal de creacion exige seleccionar un cliente del dropdown antes de crear
- **client_code en body**: El backend acepta `client_code` explicito en el body del POST, con fallback al cliente de sesion
- **Validacion de cliente**: Si el client_code no existe, retorna 400
- **Status vacio → default**: Si status es cadena vacia, usa la primera columna como default

### Tests

- 82 tests (+5 nuevos): creacion con client_code explicito, fallback a sesion, cliente invalido, status explicito, status vacio

## v0.2.1 (2026-02-11)

### Assistant - Scope & Token Gating

- **Scope-aware retrieval**: 3 opciones explicitas: General (solo kb*standard), Cliente (solo kb*<CLIENT>), Cliente + Standard (ambas colecciones)
- **Token gating**: Si la busqueda no devuelve items validos, NO se llama al modelo OpenAI (ahorro de tokens). Se muestra mensaje con sugerencias
- **Validacion APPROVED**: Solo items con status APPROVED en SQLite son considerados validos tras la busqueda en Qdrant
- **Flag model_called**: Cada respuesta incluye un flag de auditoria (0/1) indicando si se invoco al modelo

### Assistant - Retrieval Enhancements

- **Filtro por tipo KB**: Selector en la UI para filtrar por tipo de item (Incident Pattern, Root Cause, Resolution, Verification Steps, Customizing, ABAP Tech Note, Glossary, Runbook)
- **Ranking boost determinista**: Items cuyos tags o sap_objects coinciden con tokens de la pregunta reciben un boost de score (+0.05 por match)

### Assistant - Chat History

- **Sidebar de historial**: Panel lateral con listado de sesiones de chat, ordenadas por actividad reciente
- **Sesiones persistentes**: Chats guardados en SQLite con mensajes, scope, cliente, timestamps
- **Busqueda de historial**: Buscar sesiones por titulo o contenido de mensajes
- **Pin de sesiones**: Fijar chats importantes para que no se eliminen con la retencion
- **Renombrar sesiones**: Editar titulo de cualquier sesion desde el sidebar
- **Exportar sesiones**: Exportar chat individual como Markdown o JSON
- **Eliminar sesiones**: Borrar sesiones con confirmacion, cascade de mensajes
- **Retencion configurable**: Limpieza automatica de sesiones antiguas no fijadas (7/15/30 dias). Se ejecuta al arrancar el servidor

### API - Nuevos Endpoints

| Metodo | Ruta                               | Descripcion                    |
| ------ | ---------------------------------- | ------------------------------ |
| GET    | `/api/chat/sessions`               | Listar sesiones (con busqueda) |
| POST   | `/api/chat/sessions`               | Crear sesion                   |
| GET    | `/api/chat/sessions/{id}/messages` | Mensajes de sesion             |
| PUT    | `/api/chat/sessions/{id}/rename`   | Renombrar sesion               |
| PUT    | `/api/chat/sessions/{id}/pin`      | Fijar/desfijar sesion          |
| DELETE | `/api/chat/sessions/{id}`          | Eliminar sesion                |
| GET    | `/api/chat/sessions/{id}/export`   | Exportar (md/json)             |
| POST   | `/api/chat/retention`              | Configurar retencion           |

### Tests

- 77 tests de integracion y E2E cubriendo: token gating, scope isolation, Qdrant routing, type filter, ranking boost, chat sessions, retention, search, pin, rename, export, API endpoints

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
