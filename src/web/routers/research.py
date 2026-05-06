"""Research router for SAP IS-U source candidates."""
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from src.research.agents.crawler import DEFAULT_CRAWL_QUERIES, run_autonomous_crawl
from src.research.agents.orchestrator import promote_candidate_to_kb_draft, run_research_pipeline
from src.research.agents.topic_catalog import TopicDefinition, list_topic_catalog
from src.research.agents.workflow import fetch_url_document, normalize_candidate
from src.research.storage.research_repository import (
    CrawlRun,
    CrawlRunEvent,
    KBCandidate,
    DiscoveredTopic,
    ResearchRepository,
    ResearchRun,
    ResearchRunEvent,
    ResearchSource,
)
from src.web import dependencies as deps

log = logging.getLogger(__name__)
router = APIRouter()


def _repo() -> ResearchRepository:
    return ResearchRepository(deps.DATA_ROOT / "research" / "source_registry.sqlite")


def _source_to_dict(source: ResearchSource) -> dict:
    return {
        "id": source.id,
        "priority": source.priority,
        "name": source.name,
        "kind": source.kind,
        "tier": source.tier,
        "base_url": source.base_url,
        "usage_policy": source.usage_policy,
        "enabled": bool(source.enabled),
        "notes": source.notes,
    }


def _candidate_to_dict(candidate: KBCandidate) -> dict:
    return {
        "id": candidate.id,
        "source_id": candidate.source_id,
        "source_name": candidate.source_name,
        "client_scope": candidate.client_scope,
        "client_code": candidate.client_code,
        "url": candidate.url,
        "title": candidate.title,
        "raw_excerpt": candidate.raw_excerpt,
        "kb_type": candidate.kb_type,
        "content_markdown": candidate.content_markdown,
        "tags": json.loads(candidate.tags_json or "[]"),
        "sap_objects": json.loads(candidate.sap_objects_json or "[]"),
        "signals": json.loads(candidate.signals_json or "{}"),
        "sources": json.loads(candidate.sources_json or "{}"),
        "confidence_score": candidate.confidence_score,
        "copyright_risk": candidate.copyright_risk,
        "audit_status": candidate.audit_status,
        "audit_notes": candidate.audit_notes,
        "status": candidate.status,
        "promoted_kb_id": candidate.promoted_kb_id,
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _run_to_dict(run: ResearchRun) -> dict:
    return {
        "id": run.id,
        "topic": run.topic,
        "client_scope": run.client_scope,
        "client_code": run.client_code,
        "source_ids": json.loads(run.source_ids_json or "[]"),
        "max_results_per_source": run.max_results_per_source,
        "auto_promote": bool(run.auto_promote),
        "auto_index": bool(run.auto_index),
        "status": run.status,
        "agents": {
            "Collector": run.collector_status,
            "Normalizer": run.normalizer_status,
            "Auditor": run.auditor_status,
            "Ingestor": run.ingestor_status,
            "Indexer": run.indexer_status,
        },
        "discovered_count": run.discovered_count,
        "fetched_count": run.fetched_count,
        "candidate_count": run.candidate_count,
        "promoted_count": run.promoted_count,
        "indexed_count": run.indexed_count,
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "completed_at": run.completed_at,
    }


def _event_to_dict(event: ResearchRunEvent) -> dict:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "agent": event.agent,
        "level": event.level,
        "message": event.message,
        "payload": json.loads(event.payload_json or "{}"),
        "created_at": event.created_at,
    }


def _crawl_to_dict(crawl: CrawlRun) -> dict:
    return {
        "id": crawl.id,
        "client_scope": crawl.client_scope,
        "client_code": crawl.client_code,
        "source_ids": json.loads(crawl.source_ids_json or "[]"),
        "seed_queries": json.loads(crawl.seed_queries_json or "[]"),
        "max_pages_per_source": crawl.max_pages_per_source,
        "max_topics": crawl.max_topics,
        "auto_queue_runs": bool(crawl.auto_queue_runs),
        "auto_promote": bool(crawl.auto_promote),
        "auto_index": bool(crawl.auto_index),
        "status": crawl.status,
        "agents": {
            "Topic Scout": crawl.scout_status,
            "Source Crawler": crawl.crawler_status,
            "Topic Extractor": crawl.topic_status,
            "Run Queuer": crawl.queue_status,
        },
        "discovered_url_count": crawl.discovered_url_count,
        "fetched_page_count": crawl.fetched_page_count,
        "discovered_topic_count": crawl.discovered_topic_count,
        "queued_run_count": crawl.queued_run_count,
        "error": crawl.error,
        "created_at": crawl.created_at,
        "updated_at": crawl.updated_at,
        "completed_at": crawl.completed_at,
    }


def _crawl_event_to_dict(event: CrawlRunEvent) -> dict:
    return {
        "id": event.id,
        "crawl_id": event.crawl_id,
        "agent": event.agent,
        "level": event.level,
        "message": event.message,
        "payload": json.loads(event.payload_json or "{}"),
        "created_at": event.created_at,
    }


def _discovered_topic_to_dict(topic: DiscoveredTopic) -> dict:
    return {
        "id": topic.id,
        "source_id": topic.source_id,
        "source_name": topic.source_name,
        "url": topic.url,
        "title": topic.title,
        "topic": topic.topic,
        "category": topic.category,
        "objects": json.loads(topic.objects_json or "[]"),
        "tags": json.loads(topic.tags_json or "[]"),
        "confidence_score": topic.confidence_score,
        "status": topic.status,
        "queued_run_id": topic.queued_run_id,
        "first_seen_at": topic.first_seen_at,
        "updated_at": topic.updated_at,
    }


def _topic_to_dict(topic: TopicDefinition) -> dict:
    origin = "expertise_pack" if topic.id.startswith("expert-") else "topic_scout" if topic.id.startswith("scout-") else "curated"
    return {
        "id": topic.id,
        "category": topic.category,
        "label": topic.label,
        "topic": topic.topic,
        "source_ids": list(topic.source_ids),
        "objects": list(topic.objects),
        "origin": origin,
    }


def _scope_from_body(request: Request, body: dict) -> tuple[str, str | None, JSONResponse | None]:
    scope = body.get("scope", "standard")
    if scope not in {"standard", "client"}:
        return scope, None, JSONResponse({"error": "scope must be standard or client."}, status_code=400)
    state = deps.get_state(request)
    client_code = state.active_client_code if scope == "client" else None
    if scope == "client" and not client_code:
        return scope, None, JSONResponse({"error": "No client selected."}, status_code=400)
    return scope, client_code, None


def _standard_scope() -> tuple[str, None]:
    return "standard", None


@router.get("/api/research/sources")
async def list_sources():
    repo = _repo()
    sources = repo.list_sources(enabled_only=False)
    return [_source_to_dict(source) for source in sources]


@router.post("/api/research/sources/seed")
async def seed_sources():
    repo = _repo()
    inserted = repo.seed_default_sources()
    return {"inserted": inserted, "sources": [_source_to_dict(s) for s in repo.list_sources()]}


@router.get("/api/research/topic-catalog")
async def get_topic_catalog(category: str | None = None):
    return [_topic_to_dict(topic) for topic in list_topic_catalog(category)]


@router.get("/api/research/candidates")
async def list_candidates(
    request: Request,
    scope: str | None = None,
    status: str | None = None,
    audit_status: str | None = None,
    limit: int = 100,
):
    state = deps.get_state(request)
    client_code = state.active_client_code if scope == "client" else None
    candidates = _repo().list_candidates(
        client_scope=scope,
        client_code=client_code,
        status=status,
        audit_status=audit_status,
        limit=limit,
    )
    return [_candidate_to_dict(candidate) for candidate in candidates]


@router.get("/api/research/runs")
async def list_runs(limit: int = 20):
    return [_run_to_dict(run) for run in _repo().list_runs(limit=limit)]


@router.get("/api/research/crawl-default-queries")
async def crawl_default_queries():
    return {"queries": DEFAULT_CRAWL_QUERIES}


@router.get("/api/research/crawls")
async def list_crawls(limit: int = 20):
    return [_crawl_to_dict(crawl) for crawl in _repo().list_crawl_runs(limit=limit)]


@router.post("/api/research/crawls")
async def start_crawl(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    scope, client_code = _standard_scope()

    repo = _repo()
    requested_sources = body.get("source_ids") or []
    if not requested_sources:
        requested_sources = [
            source.id
            for source in repo.list_sources(enabled_only=True)
            if source.usage_policy != "REFERENCE_ONLY" and source.base_url
        ][:8]
    seed_queries = body.get("seed_queries") or DEFAULT_CRAWL_QUERIES
    try:
        crawl = repo.create_crawl_run(
            client_scope=scope,
            client_code=client_code,
            source_ids=requested_sources,
            seed_queries=seed_queries,
            max_pages_per_source=body.get("max_pages_per_source", 2),
            max_topics=body.get("max_topics", 40),
            auto_queue_runs=body.get("auto_queue_runs", True),
            auto_promote=body.get("auto_promote", True),
            auto_index=body.get("auto_index", False),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    repo.add_crawl_event(crawl.id, agent="Orchestrator", level="INFO", message="Autonomous crawl queued.")
    state = deps.get_state(request)
    background_tasks.add_task(
        run_autonomous_crawl,
        repo.db_path,
        deps.DATA_ROOT,
        crawl.id,
        deps.get_openai_api_key(request),
        state.qdrant_url,
    )
    return JSONResponse(_crawl_to_dict(crawl), status_code=202)


@router.get("/api/research/crawls/{crawl_id}")
async def get_crawl(crawl_id: str):
    crawl = _repo().get_crawl_run(crawl_id)
    if not crawl:
        return JSONResponse({"error": "Crawl not found."}, status_code=404)
    return _crawl_to_dict(crawl)


@router.get("/api/research/crawls/{crawl_id}/events")
async def list_crawl_events(crawl_id: str, limit: int = 300):
    repo = _repo()
    if not repo.get_crawl_run(crawl_id):
        return JSONResponse({"error": "Crawl not found."}, status_code=404)
    return [_crawl_event_to_dict(event) for event in repo.list_crawl_events(crawl_id, limit=limit)]


@router.get("/api/research/discovered-topics")
async def list_discovered_topics(status: str | None = None, limit: int = 100):
    topics = _repo().list_discovered_topics(status=status, limit=limit)
    return [_discovered_topic_to_dict(topic) for topic in topics]


@router.post("/api/research/discovered-topics/{topic_id}/queue")
async def queue_discovered_topic(topic_id: str, request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    repo = _repo()
    topic = repo.get_discovered_topic(topic_id)
    if not topic:
        return JSONResponse({"error": "Discovered topic not found."}, status_code=404)
    scope, client_code = _standard_scope()
    state = deps.get_state(request)

    source_ids = [topic.source_id] if topic.source_id else body.get("source_ids", [])
    run = repo.create_run(
        topic=topic.topic,
        client_scope=scope,
        client_code=client_code,
        source_ids=source_ids,
        max_results_per_source=body.get("max_results_per_source", 1),
        auto_promote=body.get("auto_promote", True),
        auto_index=body.get("auto_index", False),
    )
    repo.update_discovered_topic(topic.id, status="QUEUED", queued_run_id=run.id)
    repo.add_run_event(
        run.id,
        agent="Topic Scout",
        level="INFO",
        message=f"Queued from discovered topic {topic.id}.",
    )
    background_tasks.add_task(
        run_research_pipeline,
        repo.db_path,
        deps.DATA_ROOT,
        run.id,
        deps.get_openai_api_key(request),
        state.qdrant_url,
    )
    return JSONResponse({"topic": _discovered_topic_to_dict(repo.get_discovered_topic(topic.id)), "run": _run_to_dict(run)}, status_code=202)


@router.post("/api/research/runs")
async def start_run(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    scope, client_code = _standard_scope()

    repo = _repo()
    requested_sources = body.get("source_ids") or []
    if not requested_sources:
        requested_sources = [
            source.id
            for source in repo.list_sources(enabled_only=True)
            if source.usage_policy != "REFERENCE_ONLY" and source.base_url
        ][:6]
    try:
        run = repo.create_run(
            topic=body.get("topic", ""),
            client_scope=scope,
            client_code=client_code,
            source_ids=requested_sources,
            max_results_per_source=body.get("max_results_per_source", 2),
            auto_promote=body.get("auto_promote", True),
            auto_index=body.get("auto_index", False),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    repo.add_run_event(run.id, agent="Orchestrator", level="INFO", message="Run queued.")
    background_tasks.add_task(
        run_research_pipeline,
        repo.db_path,
        deps.DATA_ROOT,
        run.id,
        deps.get_openai_api_key(request),
        deps.get_state(request).qdrant_url,
    )
    return JSONResponse(_run_to_dict(run), status_code=202)


@router.post("/api/research/runs/catalog")
async def start_catalog_runs(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    scope, client_code = _standard_scope()

    category = body.get("category")
    topics = list_topic_catalog(category)
    limit = body.get("limit")
    if limit:
        topics = topics[: max(1, min(int(limit), len(topics)))]
    if not topics:
        return JSONResponse({"error": "No topics found for the requested catalog filter."}, status_code=400)

    repo = _repo()
    runs = []
    state = deps.get_state(request)
    for topic in topics:
        requested_sources = body.get("source_ids") or list(topic.source_ids)
        try:
            run = repo.create_run(
                topic=topic.topic,
                client_scope=scope,
                client_code=client_code,
                source_ids=requested_sources,
                max_results_per_source=body.get("max_results_per_source", 1),
                auto_promote=body.get("auto_promote", True),
                auto_index=body.get("auto_index", False),
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        repo.add_run_event(
            run.id,
            agent="Orchestrator",
            level="INFO",
            message=f"Catalog run queued from topic '{topic.label}'.",
        )
        repo.add_run_event(
            run.id,
            agent="Topic Scout",
            level="INFO",
            message=f"Selected topic objects: {', '.join(topic.objects) or 'process topic'}.",
            payload={"topic_id": topic.id, "category": topic.category},
        )
        background_tasks.add_task(
            run_research_pipeline,
            repo.db_path,
            deps.DATA_ROOT,
            run.id,
            deps.get_openai_api_key(request),
            state.qdrant_url,
        )
        runs.append(run)

    return JSONResponse(
        {
            "queued": len(runs),
            "runs": [_run_to_dict(run) for run in runs],
        },
        status_code=202,
    )


@router.get("/api/research/runs/{run_id}")
async def get_run(run_id: str):
    run = _repo().get_run(run_id)
    if not run:
        return JSONResponse({"error": "Run not found."}, status_code=404)
    return _run_to_dict(run)


@router.get("/api/research/runs/{run_id}/events")
async def list_run_events(run_id: str, limit: int = 200):
    repo = _repo()
    if not repo.get_run(run_id):
        return JSONResponse({"error": "Run not found."}, status_code=404)
    return [_event_to_dict(event) for event in repo.list_run_events(run_id, limit=limit)]


@router.post("/api/research/candidates")
async def create_candidate(request: Request):
    body = await request.json()
    scope, client_code, error = _scope_from_body(request, body)
    if error:
        return error

    repo = _repo()
    source = repo.get_source(body.get("source_id", "sap-help"))
    if not source:
        return JSONResponse({"error": "Unknown source_id."}, status_code=400)

    normalized = normalize_candidate(
        source=source,
        title=body.get("title", ""),
        raw_excerpt=body.get("raw_excerpt", ""),
        url=body.get("url"),
    )
    try:
        candidate, is_new = repo.create_candidate(
            source=source,
            client_scope=scope,
            client_code=client_code,
            url=body.get("url"),
            **normalized,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    data = _candidate_to_dict(candidate)
    data["is_new"] = is_new
    return data


@router.post("/api/research/collect-url")
async def collect_url(request: Request):
    body = await request.json()
    scope, client_code, error = _scope_from_body(request, body)
    if error:
        return error
    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "url is required."}, status_code=400)

    repo = _repo()
    source = repo.get_source(body.get("source_id", "sap-help"))
    if not source:
        return JSONResponse({"error": "Unknown source_id."}, status_code=400)
    if source.usage_policy == "REFERENCE_ONLY":
        return JSONResponse({"error": "This source is reference-only and cannot be collected automatically."}, status_code=400)

    try:
        document = fetch_url_document(url)
        normalized = normalize_candidate(
            source=source,
            title=body.get("title") or document.title,
            raw_excerpt=document.text,
            url=url,
        )
        candidate, is_new = repo.create_candidate(
            source=source,
            client_scope=scope,
            client_code=client_code,
            url=url,
            **normalized,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        log.exception("URL collection failed")
        return JSONResponse({"error": f"URL collection failed: {e}"}, status_code=400)
    data = _candidate_to_dict(candidate)
    data["is_new"] = is_new
    return data


@router.post("/api/research/candidates/{candidate_id}/promote-to-kb-draft")
async def promote_candidate(candidate_id: str, request: Request):
    body = await request.json()
    repo = _repo()
    candidate = repo.get_candidate(candidate_id)
    if not candidate:
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    if candidate.copyright_risk == "HIGH":
        return JSONResponse({"error": "High copyright risk candidates cannot be promoted."}, status_code=400)
    if candidate.audit_status == "REJECTED":
        return JSONResponse({"error": "Rejected candidates cannot be promoted."}, status_code=400)

    scope = body.get("scope") or candidate.client_scope
    state = deps.get_state(request)
    client_code = state.active_client_code if scope == "client" else None
    if scope == "client" and not client_code:
        return JSONResponse({"error": "No client selected."}, status_code=400)
    if scope != candidate.client_scope or client_code != candidate.client_code:
        return JSONResponse({"error": "Candidate scope does not match the requested scope."}, status_code=400)

    item = promote_candidate_to_kb_draft(candidate, repo, deps.get_client_manager())
    updated = repo.get_candidate(candidate_id)
    return {
        "candidate": _candidate_to_dict(updated),
        "kb_item": {
            "kb_id": item.kb_id,
            "title": item.title,
            "type": item.type,
            "status": item.status,
        },
    }


@router.post("/api/research/candidates/{candidate_id}/reject")
async def reject_candidate(candidate_id: str):
    repo = _repo()
    if not repo.get_candidate(candidate_id):
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    updated = repo.update_candidate_status(
        candidate_id,
        status="REJECTED",
        audit_status="REJECTED",
        audit_notes="Rejected from research queue.",
    )
    return _candidate_to_dict(updated)
