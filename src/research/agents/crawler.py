"""Controlled autonomous crawler for SAP IS-U topic discovery."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen

from src.research.agents.orchestrator import run_research_pipeline
from src.research.agents.topic_catalog import pick_catalog_topics
from src.research.agents.workflow import (
    CollectedDocument,
    detect_sap_objects,
    direct_source_urls_for_topic,
    fetch_url_document,
    infer_tags,
    search_source_urls,
)
from src.research.storage.research_repository import (
    CrawlRun,
    DiscoveredTopic,
    ResearchRepository,
    ResearchSource,
)


DEFAULT_CRAWL_QUERIES = [
    "SAP IS-U utilities",
    "SAP IS-U master data contract account",
    "SAP IS-U meter reading billing device management",
    "SAP FI-CA contract account open items",
    "SAP IS-U UTILMD MSCONS APERAK EDIFACT",
    "SAP IS-U transactions navigation SPRO customizing",
    "SAP IS-U error messages message class IDoc status",
    "SAP IS-U function modules BAdI exits ABAP classes",
    "SAP IS-U end-to-end troubleshooting meter-to-cash move-in billing",
    "SAP IS-U country market rules outside Germany",
    "SAP IS-U Spain CNMC data exchange autolecturas switching billing",
    "SAP IS-U Northern Ireland Utility Regulator market message meter registration",
    "SAP IS-U Ireland RMD market messages change of supplier meter works DUOS",
    "SAP IS-U France CRE GTE GTG supplier switching meter reading",
    "SAP S/4HANA Utilities meter to cash",
]

USER_AGENT = "SapIsuAssistantResearchBot/0.2 (+controlled-topic-discovery)"
DIRECT_REFERENCE_SOURCE_IDS = {"sap-help"}
MAX_WEB_SEARCH_QUERIES_PER_SOURCE = 3
WEB_SEARCH_TIMEOUT_SECONDS = 5
GENERIC_SEARCH_SKIP_KINDS = {"TECH_DICTIONARY"}


@dataclass(frozen=True)
class TopicHit:
    source: ResearchSource
    url: str | None
    title: str
    topic: str
    category: str
    objects: tuple[str, ...]
    tags: tuple[str, ...]
    confidence_score: float


def run_autonomous_crawl(
    db_path: Path,
    data_root: Path,
    crawl_id: str,
    api_key: str | None = None,
    qdrant_url: str = "http://localhost:6333",
) -> None:
    """Discover topics from configured sources and optionally queue research runs."""
    repo = ResearchRepository(db_path)
    crawl = repo.get_crawl_run(crawl_id)
    if not crawl:
        return

    discovered_urls: list[tuple[ResearchSource, str]] = []
    fetched_docs: list[tuple[ResearchSource, CollectedDocument]] = []
    discovered_topics: list[DiscoveredTopic] = []
    queued = 0

    try:
        repo.update_crawl_run(crawl.id, status="RUNNING")
        repo.add_crawl_event(crawl.id, agent="Orchestrator", level="INFO", message="Autonomous crawl started.")

        source_ids = json.loads(crawl.source_ids_json or "[]")
        seed_queries = json.loads(crawl.seed_queries_json or "[]")
        sources = [source for source_id in source_ids if (source := repo.get_source(source_id))]
        repo.update_crawl_run(crawl.id, scout_status="RUNNING")
        repo.add_crawl_event(
            crawl.id,
            agent="Topic Scout",
            level="INFO",
            message=f"Loaded {len(seed_queries)} seed query/queries and {len(sources)} source(s).",
        )
        repo.update_crawl_run(crawl.id, scout_status="COMPLETED")

        repo.update_crawl_run(crawl.id, crawler_status="RUNNING")
        for source in sources:
            per_query_limit = max(1, min(crawl.max_pages_per_source, 5))
            source_urls = []
            if source.usage_policy == "REFERENCE_ONLY":
                repo.add_crawl_event(
                    crawl.id,
                    agent="Source Crawler",
                    level="WARNING",
                    message=f"Skipped reference-only source: {source.name}",
                )
                continue
            if not source.base_url:
                repo.add_crawl_event(
                    crawl.id,
                    agent="Source Crawler",
                    level="WARNING",
                    message=f"Skipped source without base URL: {source.name}",
                )
                continue
            if not robots_allows(source.base_url):
                if source.id in DIRECT_REFERENCE_SOURCE_IDS:
                    for query in seed_queries:
                        if len(source_urls) >= crawl.max_pages_per_source:
                            break
                        for url in direct_source_urls_for_topic(query, source, per_query_limit):
                            if len(source_urls) >= crawl.max_pages_per_source:
                                break
                            if url not in source_urls:
                                source_urls.append(url)
                    if source_urls:
                        repo.add_crawl_event(
                            crawl.id,
                            agent="Source Crawler",
                            level="WARNING",
                            message=(
                                f"robots.txt does not allow crawling source homepage: {source.name}. "
                                "Using configured static reference summaries only."
                            ),
                        )
                        repo.add_crawl_event(
                            crawl.id,
                            agent="Source Crawler",
                            level="INFO",
                            message=f"{source.name}: {len(source_urls)} URL(s) selected.",
                            payload={"source_id": source.id, "urls": source_urls},
                        )
                        discovered_urls.extend((source, url) for url in source_urls)
                        continue
                repo.add_crawl_event(
                    crawl.id,
                    agent="Source Crawler",
                    level="WARNING",
                    message=f"robots.txt does not allow crawling source homepage: {source.name}",
                )
                continue
            for query in seed_queries:
                if len(source_urls) >= crawl.max_pages_per_source:
                    break
                for url in direct_source_urls_for_topic(query, source, per_query_limit):
                    if len(source_urls) >= crawl.max_pages_per_source:
                        break
                    if url not in source_urls and robots_allows(url):
                        source_urls.append(url)
            if source_urls:
                repo.add_crawl_event(
                    crawl.id,
                    agent="Source Crawler",
                    level="INFO",
                    message=(
                        f"{source.name}: generic web search skipped; "
                        "configured direct source adapters supplied URLs."
                    ),
                )
            elif source.kind in GENERIC_SEARCH_SKIP_KINDS:
                repo.add_crawl_event(
                    crawl.id,
                    agent="Source Crawler",
                    level="INFO",
                    message=(
                        f"{source.name}: generic web search skipped; "
                        "topic-level dictionary adapters will be used by queued runs."
                    ),
                )
            search_failures = 0
            last_search_error = None
            web_queries = [] if source_urls or source.kind in GENERIC_SEARCH_SKIP_KINDS else seed_queries[:MAX_WEB_SEARCH_QUERIES_PER_SOURCE]
            for query in web_queries:
                if len(source_urls) >= crawl.max_pages_per_source:
                    break
                try:
                    urls = search_source_urls(query, source, limit=per_query_limit, timeout=WEB_SEARCH_TIMEOUT_SECONDS)
                except Exception as e:
                    search_failures += 1
                    last_search_error = _short_error(e)
                    continue
                for url in urls:
                    if len(source_urls) >= crawl.max_pages_per_source:
                        break
                    if url not in source_urls and robots_allows(url):
                        source_urls.append(url)
            if search_failures:
                repo.add_crawl_event(
                    crawl.id,
                    agent="Source Crawler",
                    level="WARNING",
                    message=(
                        f"{source.name}: {search_failures} search attempt(s) unavailable. "
                        f"{last_search_error or 'External endpoint unavailable.'}"
                    ),
                )
            repo.add_crawl_event(
                crawl.id,
                agent="Source Crawler",
                level="INFO",
                message=f"{source.name}: {len(source_urls)} URL(s) selected.",
                payload={"source_id": source.id, "urls": source_urls},
            )
            discovered_urls.extend((source, url) for url in source_urls)

        repo.update_crawl_run(crawl.id, discovered_url_count=len(discovered_urls))

        for source, url in discovered_urls:
            if len(fetched_docs) >= crawl.max_topics:
                break
            try:
                document = fetch_url_document(url, timeout=12)
            except Exception as e:
                repo.add_crawl_event(
                    crawl.id,
                    agent="Source Crawler",
                    level="WARNING",
                    message=f"Could not fetch {url}. {_short_error(e)}",
                )
                continue
            fetched_docs.append((source, document))
            repo.add_crawl_event(
                crawl.id,
                agent="Source Crawler",
                level="SUCCESS",
                message=f"Fetched page: {document.title[:120]}",
                payload={"url": url},
            )
        repo.update_crawl_run(crawl.id, crawler_status="COMPLETED", fetched_page_count=len(fetched_docs))

        repo.update_crawl_run(crawl.id, topic_status="RUNNING")
        for source, document in fetched_docs:
            for hit in extract_topic_hits(source, document):
                if len(discovered_topics) >= crawl.max_topics:
                    break
                topic, is_new = repo.create_discovered_topic(
                    source=hit.source,
                    url=hit.url,
                    title=hit.title,
                    topic=hit.topic,
                    category=hit.category,
                    objects=list(hit.objects),
                    tags=list(hit.tags),
                    confidence_score=hit.confidence_score,
                )
                discovered_topics.append(topic)
                repo.add_crawl_event(
                    crawl.id,
                    agent="Topic Extractor",
                    level="SUCCESS" if is_new else "INFO",
                    message=("Discovered" if is_new else "Reused") + f" topic: {topic.topic}",
                    payload={"topic_id": topic.id, "objects": list(hit.objects), "url": hit.url},
                )

        if len(discovered_topics) < crawl.max_topics:
            fallback_topics = seed_catalog_topics(repo, crawl, sources, crawl.max_topics - len(discovered_topics))
            discovered_topics.extend(fallback_topics)
            if fallback_topics:
                repo.add_crawl_event(
                    crawl.id,
                    agent="Topic Extractor",
                    level="INFO",
                    message=f"Added {len(fallback_topics)} catalog topic(s) to fill the autonomous queue.",
                )
        repo.update_crawl_run(
            crawl.id,
            topic_status="COMPLETED",
            discovered_topic_count=len(discovered_topics),
        )

        if crawl.auto_queue_runs:
            repo.update_crawl_run(crawl.id, queue_status="RUNNING")
            for topic in discovered_topics[: crawl.max_topics]:
                source_ids = [topic.source_id] if topic.source_id else json.loads(crawl.source_ids_json or "[]")
                if topic.source_id == "topic-catalog":
                    source_ids = json.loads(crawl.source_ids_json or "[]")
                run = repo.create_run(
                    topic=topic.topic,
                    client_scope=crawl.client_scope,
                    client_code=crawl.client_code,
                    source_ids=source_ids,
                    max_results_per_source=max(1, min(crawl.max_pages_per_source, 3)),
                    auto_promote=bool(crawl.auto_promote),
                    auto_index=bool(crawl.auto_index),
                )
                repo.update_discovered_topic(topic.id, status="QUEUED", queued_run_id=run.id)
                repo.add_run_event(
                    run.id,
                    agent="Topic Scout",
                    level="INFO",
                    message=f"Queued by autonomous crawl {crawl.id}.",
                    payload={"crawl_id": crawl.id, "discovered_topic_id": topic.id},
                )
                repo.add_crawl_event(
                    crawl.id,
                    agent="Run Queuer",
                    level="SUCCESS",
                    message=f"Queued research run: {topic.topic}",
                    payload={"run_id": run.id, "topic_id": topic.id},
                )
                run_research_pipeline(repo.db_path, data_root, run.id, api_key, qdrant_url)
                completed = repo.get_run(run.id)
                if completed and completed.status == "COMPLETED":
                    repo.update_discovered_topic(topic.id, status="INGESTED", queued_run_id=run.id)
                queued += 1
            repo.update_crawl_run(crawl.id, queue_status="COMPLETED", queued_run_count=queued)
        else:
            repo.add_crawl_event(
                crawl.id,
                agent="Run Queuer",
                level="INFO",
                message="Auto-queue disabled; discovered topics remain in the queue.",
            )
            repo.update_crawl_run(crawl.id, queue_status="SKIPPED")

        repo.update_crawl_run(
            crawl.id,
            status="COMPLETED",
            completed_at=datetime.now(UTC).isoformat(),
            queued_run_count=queued,
        )
        repo.add_crawl_event(crawl.id, agent="Orchestrator", level="SUCCESS", message="Autonomous crawl completed.")
    except Exception as e:
        repo.add_crawl_event(crawl.id, agent="Orchestrator", level="ERROR", message=f"Autonomous crawl failed: {_short_error(e)}")
        repo.update_crawl_run(
            crawl.id,
            status="FAILED",
            error=str(e),
            completed_at=datetime.now(UTC).isoformat(),
        )


def extract_topic_hits(source: ResearchSource, document: CollectedDocument) -> list[TopicHit]:
    """Extract candidate topics from one fetched document."""
    text = f"{document.title}\n{document.text}"
    objects = detect_sap_objects(text)
    tags = infer_tags(text, source)
    if not objects and not looks_relevant(text):
        return []

    compact_title = clean_title(document.title)
    category = classify_topic(tags, objects, text)
    confidence = source_confidence(source, objects)
    hits = []
    if objects:
        topic = f"SAP IS-U {compact_title} {' '.join(objects[:6])}"
    else:
        topic = f"SAP IS-U {compact_title}"
    hits.append(
        TopicHit(
            source=source,
            url=document.url,
            title=compact_title,
            topic=topic[:220],
            category=category,
            objects=tuple(objects[:12]),
            tags=tuple(tags),
            confidence_score=confidence,
        )
    )
    return hits


def seed_catalog_topics(
    repo: ResearchRepository,
    crawl: CrawlRun,
    sources: list[ResearchSource],
    limit: int,
) -> list[DiscoveredTopic]:
    """Use the internal Topic Scout catalog when live source discovery is sparse."""
    if limit <= 0:
        return []
    default_source = sources[0] if sources else repo.get_source("sap-help")
    if not default_source:
        return []
    topics = []
    seed_queries = json.loads(crawl.seed_queries_json or "[]")
    for definition in pick_catalog_topics(seed_queries=seed_queries, limit=limit):
        source = _pick_definition_source(repo, definition.source_ids, sources) or default_source
        topic, _is_new = repo.create_discovered_topic(
            source=source,
            url=None,
            title=definition.label,
            topic=definition.topic,
            category=definition.category,
            objects=list(definition.objects),
            tags=["sap-isu", definition.category.lower().replace(" ", "-")],
            confidence_score=0.7,
        )
        topics.append(topic)
    return topics


def robots_allows(url: str) -> bool:
    """Best-effort robots.txt check. Network errors default to allowed."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        req = Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=5) as resp:
            lines = resp.read(80_000).decode("utf-8", errors="replace").splitlines()
        parser.parse(lines)
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def _pick_definition_source(
    repo: ResearchRepository,
    source_ids: tuple[str, ...],
    selected_sources: list[ResearchSource],
) -> ResearchSource | None:
    selected_by_id = {source.id: source for source in selected_sources}
    for source_id in source_ids:
        if source_id in selected_by_id:
            return selected_by_id[source_id]
    for source_id in source_ids:
        source = repo.get_source(source_id)
        if source and source.usage_policy != "REFERENCE_ONLY":
            return source
    return None


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    title = re.sub(r"(\|.*$| - SAP.*$)", "", title).strip()
    return title[:140] or "SAP IS-U discovered topic"


def looks_relevant(text: str) -> bool:
    lower = (text or "").lower()
    return any(
        marker in lower
        for marker in [
            "sap is-u",
            "sap utilities",
            "s/4hana utilities",
            "fi-ca",
            "contract account",
            "meter reading",
            "billing",
            "edifact",
            "utilmd",
            "mscons",
            "aperak",
            "retail market",
            "market message",
            "market messages",
            "market procedure",
            "market procedures",
            "supplier switching",
            "change of supplier",
            "meter registration",
            "data exchange",
            "distribuidores",
            "comercializadores",
            "intercambio de informacion",
            "intercambio de informaci",
            "marche de detail",
            "marchÃƒÂ© de dÃƒÂ©tail",
            "changement de fournisseur",
        ]
    )


def classify_topic(tags: list[str], objects: list[str], text: str) -> str:
    tag_set = set(tags)
    obj_set = set(objects)
    lower = (text or "").lower()
    if tag_set & {"customizing"} or obj_set & {"SPRO", "SM30"}:
        return "Customizing / SPRO"
    if tag_set & {"messages"} or any(marker in lower for marker in ["message class", "error message", "idoc status"]):
        return "Messages / Errors"
    if tag_set & {"abap"} or obj_set & {"SE37", "SE80", "SE18", "SE19", "SE24", "BADI", "FQEVENTS"}:
        return "ABAP / Enhancements"
    if tag_set & {"troubleshooting"} or any(marker in lower for marker in ["runbook", "troubleshooting", "end-to-end"]):
        return "Runbooks / Troubleshooting"
    if tag_set & {"country-rules"} or any(marker in lower for marker in ["country-specific", "local regulator", "localization"]):
        return "Country Market Rules"
    if tag_set & {"fiori", "s4hana", "api"} or obj_set & {"S4HANA", "FIORI", "API"}:
        return "S/4HANA Utilities / Fiori / API"
    if tag_set & {"mako", "edifact", "utilmd", "mscons", "aperak", "gpke"}:
        return "MaKo / EDIFACT"
    if tag_set & {"billing", "invoicing"} or obj_set & {"ERCH", "ERDK", "EA00", "EA19", "ETRG"}:
        return "Billing"
    if tag_set & {"meter-reading"} or obj_set & {"EABL", "EABLG", "EL31", "EL28"}:
        return "Meter Reading"
    if tag_set & {"device-management"} or obj_set & {"EQUI", "EGERH", "ETDZ", "EASTL"}:
        return "Device Management"
    if tag_set & {"fi-ca"} or obj_set & {"FKKVKP", "DFKKOP", "DFKKKO", "FPL9", "FP03"}:
        return "FI-CA"
    if "api" in lower:
        return "APIs / Integration"
    return "Master Data"


def source_confidence(source: ResearchSource, objects: list[str]) -> float:
    base = {"A": 0.85, "B": 0.72, "C": 0.55, "D": 0.25}.get(source.tier, 0.45)
    if objects:
        base += 0.05
    if source.usage_policy == "CONTEXT_ONLY":
        base -= 0.1
    return max(0.05, min(base, 0.95))


def _short_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    if not message:
        return type(error).__name__
    upper = message.upper()
    if "UNEXPECTED_EOF" in upper and "SSL" in upper:
        return "External endpoint closed the SSL connection."
    if "TIMED OUT" in upper or "TIMEOUT" in upper:
        return "External endpoint timed out."
    if "HTTP ERROR 403" in upper or "FORBIDDEN" in upper:
        return "Source blocked automated access."
    if "HTTP ERROR 429" in upper or "TOO MANY REQUESTS" in upper:
        return "Source rate limit reached."
    return message[:220]
