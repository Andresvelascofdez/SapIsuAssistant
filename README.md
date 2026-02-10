# SAP IS-U Assistant + Kanban

Aplicacion web para gestion de conocimiento SAP IS-U con IA y seguimiento operativo mediante tablero Kanban.

## Funcionalidades

### Kanban Board
- Tablero drag-and-drop con 8 columnas de estado (No analizado, En progreso, Mas info, Testing, Pendiente de transporte, Analizado - Pendiente respuesta, Analizado, Cerrado)
- Columnas con codigo de colores por estado
- Tickets con ID, titulo, prioridad y notas
- Buscador por ID de ticket
- Toggle para ocultar tickets cerrados (sin borrarlos)
- Columnas personalizables: crear, renombrar, reordenar, eliminar
- Importacion masiva desde CSV
- Datos aislados por cliente

### Assistant (RAG)
- Base de conocimiento con IA (Retrieval Augmented Generation)
- Ingesta de texto, PDF y DOCX
- Sintesis estructurada via OpenAI GPT
- Chat con streaming SSE y trazabilidad de fuentes
- Knowledge base aislada por cliente + base estandar compartida

### Review
- Workflow de aprobacion de items de conocimiento
- Edicion de titulo, contenido, tags y objetos SAP antes de aprobar
- Aprobacion con indexado automatico en Qdrant
- Rechazo con tracking de estado

### Settings
- Registro y gestion de clientes
- Configuracion de Qdrant URL
- Configuracion de API key de OpenAI
- Selector de cliente activo y toggle de KB estandar (barra superior)
- Modo oscuro

## Stack

| Capa | Tecnologia |
|------|-----------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Frontend | Jinja2, Tailwind CSS, Alpine.js, SortableJS |
| Datos | SQLite (metadatos), Qdrant (vectores) |
| IA | OpenAI API (GPT + text-embedding-3-large) |
| Infra | Docker (Qdrant) |

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
   O bien configurarla desde la UI en Settings.

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
      review.py         # API de revision/aprobacion KB
      kanban.py         # API Kanban (tickets, columnas, CSV import)
      settings.py       # API de configuracion (clientes, Qdrant, API key)
    templates/
      base.html         # Layout: sidebar, header, dark mode, selector cliente
      chat.html         # Chat con panel de fuentes
      ingest.html       # Formulario de ingesta (texto/archivo)
      review.html       # Lista + detalle de items KB
      kanban.html       # Board drag-and-drop con colores
      settings.html     # Gestion de clientes y configuracion
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
      models.py         # Modelos de datos (KBItem, Ingestion)
      kb_repository.py  # Repositorio SQLite de items KB
      ingestion_repository.py  # Repositorio de ingestas
  kanban/               # Modulo de seguimiento operativo
    storage/
      kanban_repository.py  # Repositorio SQLite (tickets, columnas, historial)
      csv_import.py         # Importacion masiva desde CSV
  shared/               # Utilidades comunes
    app_state.py        # Estado global de la aplicacion
    client_manager.py   # Registro de clientes + aislamiento de carpetas
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
  standard/
    assistant_kb.sqlite           # Knowledge base estandar
    uploads/
  clients/
    <CLIENT_CODE>/
      assistant_kb.sqlite         # KB del cliente
      kanban.sqlite               # Tickets Kanban del cliente
      uploads/
```

## API Endpoints

### Kanban
| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/kanban` | Pagina del board |
| GET | `/api/kanban/tickets` | Listar tickets |
| POST | `/api/kanban/tickets` | Crear ticket |
| PUT | `/api/kanban/tickets/{id}` | Editar ticket |
| PUT | `/api/kanban/tickets/{id}/move` | Mover ticket (drag-drop) |
| GET | `/api/kanban/tickets/{id}/history` | Historial de cambios |
| GET | `/api/kanban/columns` | Listar columnas |
| POST | `/api/kanban/columns` | Crear columna |
| PUT | `/api/kanban/columns/{id}` | Renombrar columna |
| PUT | `/api/kanban/columns/reorder` | Reordenar columnas |
| DELETE | `/api/kanban/columns/{id}` | Eliminar columna |
| POST | `/api/kanban/import-csv` | Importar tickets desde CSV |

### Assistant
| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/chat` | Pagina de chat |
| POST | `/api/chat/send` | Enviar pregunta (SSE stream) |
| GET | `/ingest` | Pagina de ingesta |
| POST | `/api/ingest/text` | Ingestar texto |
| POST | `/api/ingest/file` | Subir PDF/DOCX |
| GET | `/api/ingest/{id}/status` | Estado de ingesta |
| GET | `/review` | Pagina de revision |
| GET | `/api/review/items` | Listar items KB |
| GET | `/api/review/items/{id}` | Detalle de item |
| POST | `/api/review/items/{id}/approve` | Aprobar + indexar |
| POST | `/api/review/items/{id}/reject` | Rechazar |

### Settings
| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/settings` | Pagina de configuracion |
| GET | `/api/settings/clients` | Listar clientes |
| POST | `/api/settings/client` | Registrar cliente |
| POST | `/api/settings/qdrant` | Configurar Qdrant URL |
| POST | `/api/settings/apikey` | Configurar API key |
| POST | `/api/session/client` | Cambiar cliente activo |
| POST | `/api/session/standard-kb` | Toggle KB estandar |
