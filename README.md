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
- Research workflow para SAP IS-U: Topic Scout -> Collector -> Normalizer -> Auditor -> Ingestor -> Indexer
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

### IP Box Evidence Pack

- Documentacion profesional para asesores bajo `docs/ip_box/`
- Position paper, asset identification, architecture, R&D/development report, source inventory, third-party boundary, KB provenance, operating procedure, usage logging spec, ticket evidence templates, monthly report template, economic attribution methodology, revenue mapping, TP/valuation input, QA evidence, data protection, guides, roadmap and advisor pack checklist
- Enfoque factual: no inventa commits, fechas, screenshots, logs, horas ni evidencias; usa `TBC` o plantillas cuando falta soporte real
- Backend modular para usage logging en `src/ipbox/usage_logging.py`
- Generacion de reportes mensuales y CSV de usage events en `src/ipbox/reporting.py`
- Template de revenue mapping en `reports/templates/revenue_mapping_template.csv`
- La UI de captura de usage logging queda marcada como paso futuro; el modulo backend ya puede usarse desde scripts o integracion posterior

### Ingesta y revision KB

- Workflow de aprobacion de items de conocimiento integrado en la pantalla Ingesta
- Edicion de titulo, contenido, tags y objetos SAP antes de aprobar
- Aprobacion con indexado automatico en Qdrant
- Boton `Approve & Index All` para aprobar e indexar todos los borradores del scope seleccionado
- Acciones de aprobacion visibles solo para items `DRAFT`; los `APPROVED` se pueden rechazar para excluirlos de recuperacion
- Paneles plegables y filtros en listados largos de crawls, runs, candidatos, topicos descubiertos e items KB
- Rechazo con tracking de estado
- Ruta `/review` mantenida por compatibilidad, pero la navegacion principal usa Ingesta

### Research SAP IS-U

- Registro de fuentes priorizadas: SAP Help, SAP Learning, SAP Community, SAP Business Accelerator Hub, SAP Datasheet, LeanX, TCodeSearch, SE80, Michael Management, BDEW/EDI@Energy, SAP PRESS/Rheinwerk y blogs especializados
- Fuentes regulatorias oficiales para country packs: CNMC Espana, Utility Regulator Northern Ireland, Ireland Retail Market Design Service y CRE Francia
- Normalizacion de candidatos con tipo KB, tags, objetos SAP, senales, fuente, confianza y riesgo de copyright
- Deteccion inicial de tablas, transacciones, customizing/SPRO, mensajes de error, programas/ABAP, BAdIs/exits, APIs, procesos SAP IS-U y procesos MaKo/EDIFACT
- Promocion controlada a KB `DRAFT` y opcion de auto-aprobar/indexar candidatos de bajo riesgo (`PASSED` + copyright `LOW`)
- Recoleccion puntual de URL publicas, sin crawler masivo ni fuentes reference-only
- Dashboard grafico de agentes en Ingesta: Topic Scout, Collector, Normalizer, Auditor, Ingestor e Indexer con timeline y contadores
- Starter topics en la UI para arrancar con objetos como `FKKVKP`, `EABL`, `EGERH`, `ERCH` y `UTILMD`
- Catalogo automatico ampliado por dominios: Master Data, Device Management, Meter Reading, Billing, FI-CA, Move-In/Out, IDoc/IDE, MaKo/EDIFACT, BPEM, transacciones/navegacion, customizing/SPRO, mensajes/errores, ABAP/enhancements, runbooks de troubleshooting, APIs, S/4HANA Utilities/Fiori y reglas por pais
- Topic Scout genera topicos adicionales desde objetos SAP, transacciones, tablas, procesos EDIFACT y las fuentes configuradas
- Crawler autonomo controlado: descubre URLs/topicos desde fuentes permitidas, respeta fuentes `REFERENCE_ONLY`, deduplica y puede lanzar runs automaticamente
- Adaptadores directos por fuente/topic para SAP Help, FI-CA, meter reading, device management, move-in/out, BAdIs, S/4HANA roles, CNMC, Utility Regulator NI, RMD Ireland y CRE France; reducen dependencia de busqueda general y homepages bloqueadas
- Las URLs directas tienen prioridad sobre busquedas genericas; si una busqueda externa falla, el pipeline conserva las URLs directas ya encontradas
- SAP Help usa resumenes estaticos propios para paginas publicas conocidas cuando el portal no expone HTML legible al crawler
- Los documentos regulatorios pueden generar topicos de reglas pais aunque no contengan objetos SAP tecnicos como tablas o transacciones
- Extraccion de PDFs publicos con `pypdf` para guias regulatorias/market-message cuando la fuente publica documentos PDF
- Todo conocimiento descubierto por agentes/crawler se guarda siempre en `Standard KB`; el conocimiento especifico de cliente queda para ingesta manual
- El auditor permite auto-indexar resumenes oficiales/regulatorios de bajo riesgo con senal clara de proceso aunque no detecte un objeto SAP concreto
- Fallback seguro con catalogo interno de 145 topicos SAP IS-U cuando la busqueda web no devuelve URLs, con seleccion diversa por categoria para no sesgarse solo a tablas base

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
      research.py       # API Research sources/candidates
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
  research/              # Pipeline controlado de fuentes externas a KB draft
    agents/
      workflow.py        # Recolector puntual, normalizador y auditor
      topic_catalog.py   # Catalogo curado + Topic Scout
      crawler.py         # Crawler autonomo controlado y cola de topicos
      orchestrator.py    # Orquestacion e indexado automatico opcional
    storage/
      research_repository.py # Source registry y KB candidates
  ipbox/                # Usage logging y reporting IP Box
    usage_logging.py    # JSONL/CSV usage evidence
    reporting.py        # Monthly report + revenue template helpers
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
  research/
    source_registry.sqlite        # Fuentes y candidatos previos a KB
  ip_box/
    usage_logs/                   # JSONL de uso por mes
  ipbox/
    dossiers/                     # PDFs anuales generados desde incidencias
reports/
  templates/
    revenue_mapping_template.csv
  ip_box/
    YYYY-MM/                      # Reportes mensuales generados
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
| POST   | `/api/review/items/bulk-approve`   | Aprobar + indexar drafts       |
| POST   | `/api/review/items/{id}/reject`    | Rechazar                       |

### Research

| Metodo | Ruta                                                 | Descripcion                         |
| ------ | ---------------------------------------------------- | ----------------------------------- |
| GET    | `/api/research/sources`                              | Listar fuentes priorizadas          |
| POST   | `/api/research/sources/seed`                         | Inicializar fuentes por defecto     |
| GET    | `/api/research/topic-catalog`                        | Catalogo ampliado de topicos SAP IS-U |
| GET    | `/api/research/crawl-default-queries`                | Seed queries por defecto del crawler  |
| GET    | `/api/research/crawls`                               | Listar ejecuciones del crawler        |
| POST   | `/api/research/crawls`                               | Lanzar crawler autonomo controlado    |
| GET    | `/api/research/crawls/{id}`                          | Estado de una ejecucion crawler       |
| GET    | `/api/research/crawls/{id}/events`                   | Timeline del crawler                  |
| GET    | `/api/research/discovered-topics`                    | Topicos descubiertos/deduplicados     |
| POST   | `/api/research/discovered-topics/{id}/queue`         | Encolar un topico descubierto         |
| GET    | `/api/research/runs`                                 | Listar ejecuciones de agentes       |
| POST   | `/api/research/runs`                                 | Lanzar agentes por tema; acepta `auto_index` |
| POST   | `/api/research/runs/catalog`                         | Lanzar automaticamente el catalogo ampliado |
| GET    | `/api/research/runs/{id}`                            | Estado de una ejecucion             |
| GET    | `/api/research/runs/{id}/events`                     | Timeline de agentes                 |
| GET    | `/api/research/candidates`                           | Listar candidatos de research       |
| POST   | `/api/research/candidates`                           | Crear candidato desde extracto      |
| POST   | `/api/research/collect-url`                          | Recolectar una URL publica puntual  |
| POST   | `/api/research/candidates/{id}/promote-to-kb-draft`  | Promocionar candidato a KB `DRAFT`  |
| POST   | `/api/research/candidates/{id}/reject`               | Rechazar candidato                  |

## Ejecutar Research Agents

1. Abre `http://localhost:8000/ingest`.
2. Para crawler autonomo, usa `Autonomous Source Crawler`.
3. Selecciona fuentes, deja las `Seed queries` por defecto o aÃ±ade mas separadas por `;`.
4. Ajusta `Pages/source` y `Max topics`.
5. Activa `Queue research runs`, `Promote drafts` y `Auto-index low-risk` si quieres el flujo completo.
6. Pulsa `Start Crawler`.
7. Observa `Topic Scout`, `Source Crawler`, `Topic Extractor` y `Run Queuer`.
8. Los topicos descubiertos aparecen en `Discovered Topics`; los runs derivados aparecen en `Research Agent Runs`.

Para ejecutar el catalogo ampliado sin crawler:

1. Abre `http://localhost:8000/ingest`.
2. Para modo automatico, usa `Run Full Catalog`.
3. Puedes filtrar por categoria o dejar `All categories`.
4. Pon `Topic limit` si quieres probar con pocos temas primero; dejalo vacio para lanzar todo el catalogo.
5. Activa `Promote audited candidates to KB Draft` para que el agente Ingestor cree borradores KB automaticamente.
6. Activa `Auto-approve & index low-risk drafts` si quieres que el agente Indexer apruebe e indexe automaticamente solo candidatos `PASSED` y copyright `LOW`.
7. Pulsa `Run Full Catalog`.
8. Observa los estados `Collector`, `Normalizer`, `Auditor`, `Ingestor` e `Indexer`, los contadores y el timeline.
9. Si `Discovered = 0` pero `Fetched > 0`, significa que no se encontraron URLs web y se uso el catalogo interno seguro de objetos SAP.
10. Revisa los candidatos en `SAP IS-U Research Candidates`.
11. Los items no aptos para auto-indexado quedan en `Borradores KB pendientes`.

Para un tema individual, introduce un topic manual o pulsa un `Starter topic` y despues usa `Start Agents`.

El auto-indexado necesita API key de OpenAI y Qdrant disponible. Si falla, el item vuelve a `DRAFT` y queda pendiente en Ingesta para revision manual.

No hace falta reiniciar la base de conocimiento para usar el nuevo enfoque: los items existentes se conservan, los candidatos de research se deduplican por hash y los KB items siguen versionandose por titulo/tipo/contenido. Si mas adelante la KB queda ruidosa, la opcion recomendable es reconstruir el indice Qdrant desde SQLite o limpiar drafts/candidatos, no borrar la base completa.

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

### IP Box Evidence Docs and Reports

La documentacion principal esta en `docs/ip_box/25_advisor_pack/ADVISOR_PACK_INDEX.md`. Ese indice enlaza el paquete completo para asesores y separa lo implementado de lo pendiente de evidencia real.

El usage logging backend guarda eventos en JSONL:

```python
from pathlib import Path
from src.ipbox.usage_logging import create_usage_record, save_usage_event

record = create_usage_record(
    user="consultant",
    active_client="CLIENT_A",
    ticket_reference="TCK000001",
    task_type="incident_analysis",
    sap_module="IS-U",
    sap_isu_process="meter-reading",
    search_mode="COMBINED",
    sources_used="BOTH",
    output_used="YES",
    used_for_client_delivery="YES",
    actual_time_minutes=45,
    estimated_time_without_tool_minutes=90,
    estimated_time_saved_minutes=45,
    software_contribution_factor=0.7,
)
save_usage_event(Path("data"), record)
```

Para generar un reporte mensual:

```python
from pathlib import Path
from src.ipbox.reporting import generate_monthly_ip_report

generate_monthly_ip_report(
    Path("data"),
    Path("reports"),
    "2026-05",
    total_relevant_sap_isu_service_revenue=10000,
    total_productive_sap_isu_hours=80,
    qualifying_service_factor=0.98,
)
```

Estos reportes son evidencia interna para revision de asesores. No calculan elegibilidad final, nexus fraction, qualifying profit ni tratamiento fiscal.

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
