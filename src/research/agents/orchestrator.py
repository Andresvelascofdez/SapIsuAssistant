"""Orchestrates Collector, Normalizer, Auditor and Ingestor research agents."""
import json
from datetime import UTC, datetime
from pathlib import Path

from src.assistant.storage.kb_repository import KBItemRepository
from src.assistant.storage.models import KBItemStatus, KBItemType
from src.assistant.retrieval.kb_indexer import index_approved_kb_item
from src.research.agents.workflow import (
    fetch_url_document,
    normalize_candidate,
    search_source_urls,
    seed_documents_for_topic,
)
from src.research.storage.research_repository import KBCandidate, ResearchRepository
from src.shared.client_manager import ClientManager


def run_research_pipeline(
    db_path: Path,
    data_root: Path,
    run_id: str,
    api_key: str | None = None,
    qdrant_url: str = "http://localhost:6333",
) -> None:
    """Run the complete research pipeline for one persisted run."""
    repo = ResearchRepository(db_path)
    cm = ClientManager(data_root)
    run = repo.get_run(run_id)
    if not run:
        return

    discovered_urls: list[tuple[str, str]] = []
    documents = []
    candidates: list[KBCandidate] = []
    promoted = 0
    indexed = 0

    try:
        repo.update_run(run_id, status="RUNNING")
        repo.add_run_event(run_id, agent="Orchestrator", level="INFO", message=f"Run started for topic '{run.topic}'.")

        repo.update_run(run_id, collector_status="RUNNING")
        repo.add_run_event(run_id, agent="Collector", level="INFO", message="Searching configured sources.")
        selected_sources = []
        for source_id in json.loads(run.source_ids_json or "[]"):
            source = repo.get_source(source_id)
            if not source:
                repo.add_run_event(run_id, agent="Collector", level="WARNING", message=f"Unknown source skipped: {source_id}")
                continue
            selected_sources.append(source)
            if source.usage_policy == "REFERENCE_ONLY":
                repo.add_run_event(run_id, agent="Collector", level="WARNING", message=f"Reference-only source skipped: {source.name}")
                continue
            try:
                urls = search_source_urls(run.topic, source, limit=run.max_results_per_source)
            except Exception as e:
                repo.add_run_event(
                    run_id,
                    agent="Collector",
                    level="WARNING",
                    message=f"{source.name}: search unavailable, fallback seeds will be used if possible. {_short_error(e)}",
                )
                continue
            repo.add_run_event(
                run_id,
                agent="Collector",
                level="INFO",
                message=f"{source.name}: {len(urls)} URL(s) discovered.",
                payload={"source_id": source.id, "urls": urls},
            )
            discovered_urls.extend((source.id, url) for url in urls)

        repo.update_run(run_id, discovered_count=len(discovered_urls))
        for source_id, url in discovered_urls:
            source = repo.get_source(source_id)
            try:
                document = fetch_url_document(url)
                documents.append((source, document))
                repo.add_run_event(run_id, agent="Collector", level="SUCCESS", message=f"Fetched {document.title}", payload={"url": url})
            except Exception as e:
                repo.add_run_event(
                    run_id,
                    agent="Collector",
                    level="WARNING",
                    message=f"Fetch unavailable for {url}; continuing with other sources. {_short_error(e)}",
                )

        if not documents:
            seeded_docs = seed_documents_for_topic(run.topic, selected_sources, limit=run.max_results_per_source)
            if seeded_docs:
                documents.extend(seeded_docs)
                repo.add_run_event(
                    run_id,
                    agent="Collector",
                    level="WARNING",
                    message=(
                        f"No web URLs were collected. Used {len(seeded_docs)} safe internal "
                        "SAP object seed(s) so the pipeline can still create reviewable drafts."
                    ),
                )
            else:
                repo.add_run_event(
                    run_id,
                    agent="Collector",
                    level="WARNING",
                    message=(
                        "No URLs were discovered and the topic did not match the internal SAP object seed catalog. "
                        "Try a topic with an object such as EABL, EGERH, ERCH, FKKVKP, UTILMD or paste a direct URL/excerpt."
                    ),
                )
        repo.update_run(run_id, collector_status="COMPLETED", fetched_count=len(documents))

        repo.update_run(run_id, normalizer_status="RUNNING")
        repo.add_run_event(run_id, agent="Normalizer", level="INFO", message="Normalizing fetched documents.")
        for source, document in documents:
            normalized = normalize_candidate(
                source=source,
                title=document.title,
                raw_excerpt=document.text,
                url=document.url,
            )
            candidate, is_new = repo.create_candidate(
                source=source,
                client_scope=run.client_scope,
                client_code=run.client_code,
                url=document.url,
                **normalized,
            )
            candidates.append(candidate)
            repo.add_run_event(
                run_id,
                agent="Normalizer",
                level="SUCCESS" if is_new else "INFO",
                message=("Created" if is_new else "Reused duplicate") + f" candidate: {candidate.title}",
                payload={"candidate_id": candidate.id, "kb_type": candidate.kb_type},
            )
        repo.update_run(run_id, normalizer_status="COMPLETED", candidate_count=len(candidates))

        repo.update_run(run_id, auditor_status="RUNNING")
        passed = sum(1 for c in candidates if c.audit_status == "PASSED")
        review = sum(1 for c in candidates if c.audit_status == "NEEDS_REVIEW")
        rejected = sum(1 for c in candidates if c.audit_status == "REJECTED")
        repo.add_run_event(
            run_id,
            agent="Auditor",
            level="SUCCESS" if rejected == 0 else "WARNING",
            message=f"Audit summary: {passed} passed, {review} need review, {rejected} rejected.",
        )
        repo.update_run(run_id, auditor_status="COMPLETED")

        if run.auto_promote:
            repo.update_run(run_id, ingestor_status="RUNNING")
            promoted_items = []
            for candidate in candidates:
                if candidate.audit_status == "REJECTED" or candidate.copyright_risk == "HIGH":
                    repo.add_run_event(run_id, agent="Ingestor", level="WARNING", message=f"Candidate not promoted: {candidate.title}")
                    continue
                item = promote_candidate_to_kb_draft(candidate, repo, cm)
                promoted_items.append((candidate, item))
                promoted += 1
                repo.add_run_event(
                    run_id,
                    agent="Ingestor",
                    level="SUCCESS",
                    message=f"Promoted to KB DRAFT: {item.title}",
                    payload={"candidate_id": candidate.id, "kb_id": item.kb_id},
                )
            repo.update_run(run_id, ingestor_status="COMPLETED", promoted_count=promoted)

            if run.auto_index:
                repo.update_run(run_id, indexer_status="RUNNING")
                for candidate, item in promoted_items:
                    if candidate.audit_status != "PASSED" or candidate.copyright_risk != "LOW":
                        repo.add_run_event(
                            run_id,
                            agent="Indexer",
                            level="WARNING",
                            message=f"Left as KB DRAFT for review: {candidate.title}",
                            payload={
                                "candidate_id": candidate.id,
                                "kb_id": item.kb_id,
                                "audit_status": candidate.audit_status,
                                "copyright_risk": candidate.copyright_risk,
                            },
                        )
                        continue
                    indexed_item, warning = approve_and_index_kb_item(
                        item.kb_id,
                        candidate,
                        cm,
                        api_key=api_key,
                        qdrant_url=qdrant_url,
                    )
                    if warning:
                        repo.add_run_event(
                            run_id,
                            agent="Indexer",
                            level="WARNING",
                            message=f"Indexing failed; left as KB DRAFT: {candidate.title}. {warning}",
                            payload={"candidate_id": candidate.id, "kb_id": item.kb_id},
                        )
                        continue
                    indexed += 1
                    repo.add_run_event(
                        run_id,
                        agent="Indexer",
                        level="SUCCESS",
                        message=f"Approved and indexed: {indexed_item.title}",
                        payload={"candidate_id": candidate.id, "kb_id": indexed_item.kb_id},
                    )
                repo.update_run(run_id, indexer_status="COMPLETED", indexed_count=indexed)
            else:
                repo.add_run_event(
                    run_id,
                    agent="Indexer",
                    level="INFO",
                    message="Auto-index disabled; KB drafts remain in Ingesta review.",
                )
                repo.update_run(run_id, indexer_status="SKIPPED", indexed_count=indexed)
        else:
            repo.add_run_event(run_id, agent="Ingestor", level="INFO", message="Auto-promote disabled; candidates remain in the research queue.")
            repo.update_run(run_id, ingestor_status="SKIPPED", indexer_status="SKIPPED")
        repo.update_run(
            run_id,
            status="COMPLETED",
            completed_at=datetime.now(UTC).isoformat(),
            promoted_count=promoted,
            indexed_count=indexed,
        )
        repo.add_run_event(run_id, agent="Orchestrator", level="SUCCESS", message="Run completed.")
    except Exception as e:
        repo.add_run_event(run_id, agent="Orchestrator", level="ERROR", message=f"Run failed: {e}")
        repo.update_run(
            run_id,
            status="FAILED",
            error=str(e),
            completed_at=datetime.now(UTC).isoformat(),
        )


def promote_candidate_to_kb_draft(candidate: KBCandidate, repo: ResearchRepository, cm: ClientManager):
    """Promote one audited research candidate into the existing KB draft flow."""
    if candidate.copyright_risk == "HIGH" or candidate.audit_status == "REJECTED":
        raise ValueError("Candidate cannot be promoted")
    if candidate.client_scope == "standard":
        db_path = cm.get_standard_dir() / "assistant_kb.sqlite"
        client_code = None
    else:
        db_path = cm.get_client_dir(candidate.client_code) / "assistant_kb.sqlite"
        client_code = candidate.client_code

    sources = json.loads(candidate.sources_json or "{}")
    sources.update({
        "research_candidate_id": candidate.id,
        "research_status": candidate.status,
        "audit_status": candidate.audit_status,
        "audit_notes": candidate.audit_notes,
    })
    try:
        item_type = KBItemType(candidate.kb_type)
    except ValueError:
        item_type = KBItemType.TECHNICAL_OBJECT

    kb_repo = KBItemRepository(db_path)
    item, _is_new = kb_repo.create_or_update(
        client_scope=candidate.client_scope,
        client_code=client_code,
        item_type=item_type,
        title=candidate.title,
        content_markdown=candidate.content_markdown,
        tags=json.loads(candidate.tags_json or "[]"),
        sap_objects=json.loads(candidate.sap_objects_json or "[]"),
        signals=json.loads(candidate.signals_json or "{}"),
        sources=sources,
        status=KBItemStatus.DRAFT,
    )
    repo.update_candidate_status(candidate.id, status="PROMOTED", promoted_kb_id=item.kb_id)
    return item


def approve_and_index_kb_item(
    kb_id: str,
    candidate: KBCandidate,
    cm: ClientManager,
    *,
    api_key: str | None = None,
    qdrant_url: str = "http://localhost:6333",
):
    """Approve one promoted item and index it. Roll back to DRAFT if indexing fails."""
    if candidate.client_scope == "standard":
        db_path = cm.get_standard_dir() / "assistant_kb.sqlite"
    else:
        db_path = cm.get_client_dir(candidate.client_code) / "assistant_kb.sqlite"

    kb_repo = KBItemRepository(db_path)
    approved = kb_repo.update_status(kb_id, KBItemStatus.APPROVED)
    if not approved:
        return None, "KB item not found."
    try:
        index_approved_kb_item(approved, api_key=api_key, qdrant_url=qdrant_url)
    except Exception as e:
        kb_repo.update_status(kb_id, KBItemStatus.DRAFT)
        return kb_repo.get_by_id(kb_id), _short_error(e)
    return approved, None


def _short_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    if not message:
        message = type(error).__name__
    upper = message.upper()
    if "UNEXPECTED_EOF" in upper and "SSL" in upper:
        return "External search endpoint closed the SSL connection."
    if "TIMED OUT" in upper or "TIMEOUT" in upper:
        return "External search endpoint timed out."
    if "HTTP ERROR 403" in upper or "FORBIDDEN" in upper:
        return "Source blocked automated access."
    if "HTTP ERROR 429" in upper or "TOO MANY REQUESTS" in upper:
        return "Source rate limit reached."
    return message[:220]
