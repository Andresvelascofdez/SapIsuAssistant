# SAP IS-U Assistant + Incidencias + Kanban

Aplicacion web para conocimiento SAP IS-U con IA, registro tecnico de incidencias, evidencia IP Box, finanzas personales y seguimiento operativo mediante tablero Kanban.

## Funcionalidades

### Kanban Board

- Tablero drag-and-drop con 8 columnas de estado (No analizado, En progreso, Mas info, Testing, Pendiente de transporte, Analizado - Pendiente respuesta, Analizado, Cerrado)
- Columnas con codigo de colores por estado
- Tickets con ID, titulo, prioridad y notas
- Buscador por ID de ticket
- Toggle para ocultar tickets cerrados (sin borrarlos)
- Columnas personalizables: crear, renombrar, reordenar, eliminar
- Creacion de tickets por columna (boton "+" en cada cabecera)
- Acciones masivas: cerrar todos los tickets y borrar todos los cerrados
- Limpieza automatica de tickets cerrados antiguos (14 dias laborables)
- Cliente obligatorio en creacion (dropdown de clientes registrados)
- Importacion masiva desde CSV
- Datos aislados por cliente

### Assistant (RAG)

- Base de conocimiento con IA (Retrieval Augmented Generation)
- Ingesta de texto, PDF y DOCX con cola integrada de borradores KB
- Sintesis estructurada via OpenAI GPT
- Chat con streaming SSE y trazabilidad de fuentes
- Borrado visible de chats desde el sidebar
- Knowledge base aislada por cliente + base estandar compartida
- **Scope-aware retrieval**: General / Cliente / Cliente + Standard
- **Token gating**: No llama al modelo si no hay resultados (ahorro de tokens)
- **Filtro por tipo KB**: Filtrar por Incident Pattern, Root Cause, Resolution, etc.
- **Ranking boost**: Boost determinista por coincidencia de tags/sap_objects
- **Historial de chat**: Sidebar con sesiones persistentes, busqueda, pin, renombrar, exportar (MD/JSON)
- **Retencion configurable**: Limpieza automatica de sesiones antiguas (7/15/30 dias)

### Incidencias SAP IS-U + IP Box

- Registro de incidencias tecnicas por cliente en `data/clients/<CLIENT_CODE>/incidents.sqlite`
- Campos SAP IS-U: modulo, proceso, objetos SAP, POD/MaLo/equipo/documentos afectados, investigacion, solucion, verificacion y conocimiento reutilizable
- Clasificacion IP Box: `UNCLEAR`, `QUALIFYING_CANDIDATE`, `NOT_QUALIFYING`
- Evidencias como archivos, links o notas, con SHA256 para ficheros
- Generacion de borradores KB desde incidencias; quedan en `DRAFT` hasta aprobacion
- Dossier anual PDF en ingles para soporte documental IP Box de Chipre, sin calculo fiscal/nexus

### Ingesta y revision KB

- Workflow de aprobacion de items de conocimiento integrado en la pantalla Ingesta
- Edicion de titulo, contenido, tags y objetos SAP antes de aprobar
- Aprobacion con indexado automatico en Qdrant
- Rechazo con tracking de estado
- Ruta `/review` mantenida por compatibilidad, pero la navegacion principal usa Ingesta

### Finance (Personal)

- Gestion de gastos con categorias personalizables y documentos adjuntos
- Facturacion con lineas de detalle, calculo automatico de IVA y generacion de PDF
- Resumen financiero mensual/anual con doble vista:
  - **Net - Personal**: ingresos - impuestos (gastos personales no deducidos)
  - **Net - Business**: ingresos - gastos - impuestos (vision empresarial)
- OCR para extraccion automatica de importes y fechas desde PDFs e imagenes
- **Bulk import**: Subida multiple de PDFs/imagenes para crear gastos o facturas automaticamente via OCR
- **Mark All Paid**: Marcar todas las facturas pendientes como pagadas de una vez
- Documentos: subida, descarga, hash SHA256
- Exportacion CSV de gastos y facturas
- Navegacion por pestanas: Summary, Expenses, Invoices, Settings
- Dark mode completo con colores legibles

### Settings

- Registro y gestion de clientes
- Configuracion de Qdrant URL
- Configuracion de API key de OpenAI desde entorno, `.env` o Settings
- Selector de cliente activo y toggle de KB estandar (barra superior)
- Modo oscuro

## Stack

| Capa     | Tecnologia                                  |
| -------- | ------------------------------------------- |
| Backend  | Python 3.11+, FastAPI, Uvicorn              |
| Frontend | Jinja2, Tailwind CSS, Alpine.js, SortableJS |
| Datos    | SQLite (metadatos), Qdrant (vectores)       |
| IA       | OpenAI API (GPT + text-embedding-3-large)   |
| Infra    | Docker (Qdrant)                             |

## Quick Start

```bash
python run.py
```

El launcher verifica dependencias, arranca Qdrant via Docker, lanza el servidor web y abre `http://localhost:8000` en el navegador.

## Instalacion

### Requisitos

- Python 3.11+
- Docker Desktop (para Qdrant)
- OpenAI API key

### Pasos

1. Clonar el repositorio

2. Instalar dependencias:

   ```bash
   pip install -e .
   ```

3. Arrancar Qdrant:

   ```bash
   docker compose up -d
   ```

4. Configurar API key (opcion A: variable de entorno):

   ```bash
   set OPENAI_API_KEY=sk-...
   ```

   Tambien se puede guardar en `.env`:

   ```bash
   OPENAI_API_KEY=sk-...
   ```

   O bien configurarla desde la UI en Settings, que actualiza `.env` localmente.

5. Ejecutar:
   ```bash
   python run.py
   ```

## Estructura del proyecto

```
src/
  web/                  # Aplicacion FastAPI
    app.py              # Entry point, middlewares, routers
    dependencies.py     # Inyeccion de dependencias (estado, sesion)
    routers/
      chat.py           # API de chat SSE
      ingest.py         # API de ingesta (texto + archivos)
      review.py         # API de revision/aprobacion KB (usada desde Ingesta)
      kanban.py         # API Kanban (tickets, columnas, CSV import)
      incidents.py      # API Incidencias e IP Box dossier
      finance.py        # API Finance (gastos, facturas, resumen, OCR)
      settings.py       # API de configuracion (clientes, Qdrant, API key)
    templates/
      base.html         # Layout: sidebar, header, dark mode, selector cliente, CSS suplementario
      chat.html         # Chat con panel de fuentes
      ingest.html       # Formulario de ingesta + revision de borradores KB
      review.html       # Vista legacy de items KB
      kanban.html       # Board drag-and-drop con colores
      incidents.html    # Lista y creacion de incidencias
      incident_detail.html # Detalle, edicion, evidencias y KB draft
      ipbox_dossier.html # Generacion de dossier anual IP Box
      settings.html     # Gestion de clientes y configuracion
      finance_summary.html     # Resumen financiero mensual/anual
      finance_expenses.html    # Gastos con bulk import
      finance_invoices.html    # Facturas con bulk import y mark all paid
      finance_invoice_edit.html # Editor de factura con OCR import
      finance_settings.html    # Config financiera y categorias
    static/
      style.css         # Estilos adicionales
  assistant/            # Modulo de conocimiento IA
    ingestion/
      extractors.py     # Extraction de texto, PDF, DOCX
      schema.py         # Schema de sintesis estructurada
      synthesis.py      # Pipeline OpenAI (sintesis + validacion)
    retrieval/
      embedding_service.py  # Generacion de embeddings
      qdrant_service.py     # Operaciones Qdrant (upsert, search)
    chat/
      chat_service.py   # Servicio RAG (embedding, retrieval, respuesta)
    storage/
      models.py         # Modelos de datos (KBItem, Ingestion, ChatSession, ChatMessage)
      kb_repository.py  # Repositorio SQLite de items KB
      ingestion_repository.py  # Repositorio de ingestas
      chat_repository.py  # Repositorio de sesiones y mensajes de chat
  kanban/               # Modulo de seguimiento operativo
    storage/
      kanban_repository.py  # Repositorio SQLite (tickets, columnas, historial)
      csv_import.py         # Importacion masiva desde CSV
  incidents/            # Modulo de incidencias e IP Box evidence
    storage/
      incident_repository.py # Repositorio SQLite cliente-aislado
    pdf/
      ipbox_dossier.py      # PDF anual en ingles
  finance/              # Modulo de finanzas personales
    storage/
      finance_repository.py # Repositorio SQLite (gastos, facturas, categorias, documentos)
    pdf/
      invoice_pdf.py        # Generacion de PDF de facturas
    ocr/
      ocr_service.py        # Extraccion OCR de importes y fechas
  shared/               # Utilidades comunes
    app_state.py        # Estado global de la aplicacion
    client_manager.py   # Registro de clientes + aislamiento de carpetas
    env_loader.py       # Carga/actualizacion segura de .env
    errors.py           # Excepciones personalizadas
    tokens.py           # Utilidades de tokenizacion
    logging_config.py   # Configuracion de logging
run.py                  # Launcher (deps check, Docker, Qdrant, servidor)
docker-compose.yml      # Qdrant container
pyproject.toml          # Configuracion del proyecto
```

## Aislamiento de datos

Toda la informacion esta fisicamente separada por cliente:

```
data/
  app.sqlite                      # Config global (clientes registrados)
  kanban_global.sqlite            # Columnas Kanban (compartidas)
  chat_history.sqlite             # Historial de chat (sesiones y mensajes)
  finance.sqlite                  # Finanzas (gastos, facturas, categorias, documentos)
  standard/
    assistant_kb.sqlite           # Knowledge base estandar
    uploads/
  clients/
    <CLIENT_CODE>/
      assistant_kb.sqlite         # KB del cliente
      kanban.sqlite               # Tickets Kanban del cliente
      incidents.sqlite            # Incidencias SAP IS-U del cliente
      incident_evidence/          # Evidencias subidas por incidencia
      uploads/
  finance/
    uploads/                      # Documentos financieros subidos
    invoices/                     # PDFs de facturas generadas
  ipbox/
    dossiers/                     # PDFs anuales generados
```

## API Endpoints

### Kanban

| Metodo | Ruta                               | Descripcion                |
| ------ | ---------------------------------- | -------------------------- |
| GET    | `/kanban`                          | Pagina del board           |
| GET    | `/api/kanban/tickets`              | Listar tickets             |
| POST   | `/api/kanban/tickets`              | Crear ticket               |
| PUT    | `/api/kanban/tickets/{id}`         | Editar ticket              |
| PUT    | `/api/kanban/tickets/{id}/move`    | Mover ticket (drag-drop)   |
| DELETE | `/api/kanban/tickets/{id}`         | Eliminar ticket            |
| POST   | `/api/kanban/tickets/bulk-close`   | Cerrar todos los tickets   |
| DELETE | `/api/kanban/tickets/closed`       | Borrar tickets cerrados    |
| GET    | `/api/kanban/tickets/{id}/history` | Historial de cambios       |
| GET    | `/api/kanban/columns`              | Listar columnas            |
| POST   | `/api/kanban/columns`              | Crear columna              |
| PUT    | `/api/kanban/columns/{id}`         | Renombrar columna          |
| PUT    | `/api/kanban/columns/reorder`      | Reordenar columnas         |
| DELETE | `/api/kanban/columns/{id}`         | Eliminar columna           |
| POST   | `/api/kanban/import-csv`           | Importar tickets desde CSV |
| GET    | `/api/kanban/export-csv`           | Exportar tickets CSV       |

### Assistant

| Metodo | Ruta                               | Descripcion                    |
| ------ | ---------------------------------- | ------------------------------ |
| GET    | `/chat`                            | Pagina de chat                 |
| POST   | `/api/chat/send`                   | Enviar pregunta (SSE stream)   |
| GET    | `/api/chat/sessions`               | Listar sesiones (con busqueda) |
| POST   | `/api/chat/sessions`               | Crear sesion                   |
| GET    | `/api/chat/sessions/{id}/messages` | Mensajes de sesion             |
| PUT    | `/api/chat/sessions/{id}/rename`   | Renombrar sesion               |
| PUT    | `/api/chat/sessions/{id}/pin`      | Fijar/desfijar sesion          |
| DELETE | `/api/chat/sessions/{id}`          | Eliminar sesion                |
| GET    | `/api/chat/sessions/{id}/export`   | Exportar (md/json)             |
| POST   | `/api/chat/retention`              | Configurar retencion           |
| GET    | `/ingest`                          | Ingesta + revision KB          |
| POST   | `/api/ingest/text`                 | Ingestar texto                 |
| POST   | `/api/ingest/file`                 | Subir PDF/DOCX                 |
| GET    | `/api/ingest/{id}/status`          | Estado de ingesta              |
| GET    | `/review`                          | Pagina legacy de revision      |
| GET    | `/api/review/items`                | Listar items KB                |
| GET    | `/api/review/items/{id}`           | Detalle de item                |
| POST   | `/api/review/items/{id}/approve`   | Aprobar + indexar              |
| POST   | `/api/review/items/{id}/reject`    | Rechazar                       |

### Incidencias / IP Box

| Metodo | Ruta                                             | Descripcion                    |
| ------ | ------------------------------------------------ | ------------------------------ |
| GET    | `/incidents`                                     | Lista/filtros de incidencias   |
| GET    | `/incidents/{id}`                                | Detalle y edicion              |
| GET    | `/ipbox/dossier`                                 | Pagina de dossier anual        |
| GET    | `/api/incidents`                                 | Listar incidencias             |
| POST   | `/api/incidents`                                 | Crear incidencia               |
| GET    | `/api/incidents/{id}`                            | Obtener incidencia             |
| PUT    | `/api/incidents/{id}`                            | Actualizar incidencia          |
| DELETE | `/api/incidents/{id}`                            | Eliminar incidencia            |
| POST   | `/api/incidents/{id}/evidence`                   | Subir/linkar evidencia         |
| DELETE | `/api/incidents/{id}/evidence/{evidence_id}`     | Eliminar evidencia             |
| POST   | `/api/incidents/{id}/generate-kb-draft`          | Crear borrador KB              |
| GET    | `/api/ipbox/dossier?year=YYYY`                   | Descargar PDF anual en ingles  |

### Settings

| Metodo | Ruta                       | Descripcion             |
| ------ | -------------------------- | ----------------------- |
| GET    | `/settings`                | Pagina de configuracion |
| GET    | `/api/settings/clients`    | Listar clientes         |
| POST   | `/api/settings/client`     | Registrar cliente       |
| POST   | `/api/settings/qdrant`     | Configurar Qdrant URL   |
| POST   | `/api/settings/apikey`     | Configurar API key      |
| POST   | `/api/session/client`      | Cambiar cliente activo  |
| POST   | `/api/session/standard-kb` | Toggle KB estandar      |

### Finance

| Metodo | Ruta                                      | Descripcion                  |
| ------ | ----------------------------------------- | ---------------------------- |
| GET    | `/finance/summary`                        | Pagina de resumen            |
| GET    | `/finance/expenses`                       | Pagina de gastos             |
| GET    | `/finance/invoices`                       | Pagina de facturas           |
| GET    | `/finance/invoices/new`                   | Crear factura                |
| GET    | `/finance/invoices/{id}/edit`             | Editar factura               |
| GET    | `/finance/settings`                       | Config. financiera           |
| GET    | `/api/finance/settings`                   | Obtener config               |
| PUT    | `/api/finance/settings`                   | Actualizar config            |
| GET    | `/api/finance/categories`                 | Listar categorias            |
| POST   | `/api/finance/categories`                 | Crear categoria              |
| PUT    | `/api/finance/categories/reorder`         | Reordenar categorias         |
| PUT    | `/api/finance/categories/{id}`            | Renombrar categoria          |
| PUT    | `/api/finance/categories/{id}/toggle`     | Activar/desactivar categoria |
| DELETE | `/api/finance/categories/{id}`            | Eliminar categoria           |
| POST   | `/api/finance/upload`                     | Subir documento              |
| GET    | `/api/finance/documents/{id}/download`    | Descargar documento          |
| DELETE | `/api/finance/documents/{id}`             | Eliminar documento           |
| GET    | `/api/finance/expenses`                   | Listar gastos                |
| POST   | `/api/finance/expenses`                   | Crear gasto                  |
| PUT    | `/api/finance/expenses/{id}`              | Editar gasto                 |
| DELETE | `/api/finance/expenses/{id}`              | Eliminar gasto               |
| GET    | `/api/finance/expenses/export-csv`        | Exportar gastos CSV          |
| POST   | `/api/finance/expenses/bulk-import`       | Bulk import gastos (OCR)     |
| GET    | `/api/finance/invoices`                   | Listar facturas              |
| POST   | `/api/finance/invoices`                   | Crear factura                |
| GET    | `/api/finance/invoices/{id}`              | Detalle factura              |
| PUT    | `/api/finance/invoices/{id}`              | Editar factura               |
| DELETE | `/api/finance/invoices/{id}`              | Eliminar factura             |
| POST   | `/api/finance/invoices/{id}/generate-pdf` | Generar PDF                  |
| GET    | `/api/finance/invoices/export-csv`        | Exportar facturas CSV        |
| POST   | `/api/finance/invoices/bulk-import`       | Bulk import facturas (OCR)   |
| POST   | `/api/finance/invoices/bulk-mark-paid`    | Marcar todas como pagadas    |
| GET    | `/api/finance/summary`                    | Resumen mensual/anual        |
| POST   | `/api/finance/ocr/{doc_id}`               | Ejecutar OCR                 |
