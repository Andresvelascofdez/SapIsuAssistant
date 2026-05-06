"""Tests for the controlled SAP IS-U research candidate workflow."""
import json

from src.assistant.storage.kb_repository import KBItemRepository
from src.assistant.storage.models import KBItemStatus, KBItemType
from src.research.agents.topic_catalog import pick_catalog_topics
from src.research.agents.workflow import CollectedDocument
from src.research.agents.workflow import fetch_url_document, normalize_candidate, search_source_urls
from src.research.storage.research_repository import ResearchRepository
from src.shared.client_manager import ClientManager


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps

    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
    ClientManager(tmp_path).register_client("TST", "Test Client")

    from src.web.app import app
    from starlette.testclient import TestClient

    c = TestClient(app)
    c.post("/api/session/client", json={"code": "TST"})
    return c


def test_default_sources_are_seeded(tmp_path):
    repo = ResearchRepository(tmp_path / "research.sqlite")

    sources = repo.list_sources()

    assert len(sources) >= 12
    assert sources[0].id == "sap-help"
    assert any(source.id == "bdew-edi-energy" for source in sources)
    assert any(source.id == "cnmc-spain" and source.kind == "REGULATOR" for source in sources)
    assert any(source.id == "uregni-retail" and source.kind == "REGULATOR" for source in sources)
    assert any(source.usage_policy == "REFERENCE_ONLY" for source in sources)


def test_normalizer_detects_sap_objects_and_mako_context(tmp_path):
    repo = ResearchRepository(tmp_path / "research.sqlite")
    source = repo.get_source("bdew-edi-energy")

    result = normalize_candidate(
        source=source,
        title="UTILMD APERAK process with EABL meter reading IDoc",
        url="https://www.edi-energy.de/example",
        raw_excerpt=(
            "UTILMD and APERAK are EDIFACT messages used in GPKE market communication. "
            "SAP IS-U processing may involve IDOC status checks in EDIDS and meter reading "
            "references such as EABL for validation context."
        ),
    )

    assert result["kb_type"] == KBItemType.EDIFACT_SPEC.value
    assert "UTILMD" in result["sap_objects"]
    assert "APERAK" in result["sap_objects"]
    assert "EABL" in result["sap_objects"]
    assert "mako" in result["tags"]
    assert result["signals"]["country"] == "DE"
    assert result["audit_status"] in {"PASSED", "NEEDS_REVIEW"}


def test_normalizer_classifies_expertise_layers(tmp_path):
    repo = ResearchRepository(tmp_path / "research.sqlite")
    source = repo.get_source("sap-help")

    customizing = normalize_candidate(
        source=source,
        title="SAP IS-U SPRO billing schema customizing",
        raw_excerpt="SPRO customizing for billing schema TE420 and rate operands TE422 controls billing behavior.",
    )
    message = normalize_candidate(
        source=source,
        title="IDoc status 51 application error",
        raw_excerpt="IDoc status 51 in EDIDS requires checking the error message and reprocessing with BD87.",
    )
    abap = normalize_candidate(
        source=source,
        title="SAP IS-U BAdI and function module enhancement",
        raw_excerpt="A BAdI or function module in SE37 may explain custom behavior during meter reading.",
    )

    assert customizing["kb_type"] == KBItemType.CUSTOMIZING.value
    assert customizing["signals"]["sap_area"] == "IS-U Customizing"
    assert message["kb_type"] == KBItemType.SAP_MESSAGE.value
    assert message["signals"]["sap_area"] == "SAP Messages / Errors"
    assert abap["kb_type"] == KBItemType.ABAP_TECH_NOTE.value
    assert abap["signals"]["sap_area"] == "ABAP / Enhancements"


def test_direct_source_adapters_return_official_urls(tmp_path):
    repo = ResearchRepository(tmp_path / "research.sqlite")

    sap_help = repo.get_source("sap-help")
    cnmc = repo.get_source("cnmc-spain")
    uregni = repo.get_source("uregni-retail")

    meter_urls = search_source_urls("SAP IS-U meter reading validation EABL", sap_help, limit=3)
    spain_urls = search_source_urls("SAP IS-U Spain utilities market communication switching", cnmc, limit=1)
    ni_urls = search_source_urls("SAP IS-U Northern Ireland market registration meter configuration", uregni, limit=3)

    assert any("help.sap.com/docs" in url for url in meter_urls)
    assert any("cnmc.es" in url for url in spain_urls)
    assert any("uregni.gov.uk" in url and url.endswith(".pdf") for url in ni_urls)


def test_sap_help_js_shell_uses_static_summary(monkeypatch):
    class FakeResponse:
        headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return b"<html><head><title>SAP Help Portal | SAP Online Help</title></head><body><script></script></body></html>"

    monkeypatch.setattr("src.research.agents.workflow.urlopen", lambda *args, **kwargs: FakeResponse())

    doc = fetch_url_document(
        "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/2ac7fe29a0c94cdd88fb80c2cb9f7758/bc90d0533f8e4308e10000000a174cb4.html"
    )

    assert doc.title == "Reading Meters"
    assert "meter reading order creation" in doc.text


def test_repository_deduplicates_candidates(tmp_path):
    repo = ResearchRepository(tmp_path / "research.sqlite")
    source = repo.get_source("sap-datasheet")
    normalized = normalize_candidate(
        source=source,
        title="EABL table",
        raw_excerpt="EABL is a meter reading result table with fields for meter reading documents.",
        url="https://example.test/eabl",
    )

    first, first_is_new = repo.create_candidate(
        source=source,
        client_scope="standard",
        client_code=None,
        url="https://example.test/eabl",
        **normalized,
    )
    second, second_is_new = repo.create_candidate(
        source=source,
        client_scope="standard",
        client_code=None,
        url="https://example.test/eabl",
        **normalized,
    )

    assert first_is_new is True
    assert second_is_new is False
    assert first.id == second.id
    assert len(repo.list_candidates()) == 1


def test_repository_tracks_agent_runs_and_events(tmp_path):
    repo = ResearchRepository(tmp_path / "research.sqlite")

    run = repo.create_run(
        topic="meter reading",
        client_scope="standard",
        client_code=None,
        source_ids=["sap-help", "sap-datasheet"],
        max_results_per_source=2,
        auto_promote=True,
    )
    repo.add_run_event(run.id, agent="Collector", level="INFO", message="Searching")
    repo.update_run(run.id, status="RUNNING", collector_status="RUNNING", discovered_count=3)

    updated = repo.get_run(run.id)
    events = repo.list_run_events(run.id)

    assert updated.status == "RUNNING"
    assert updated.collector_status == "RUNNING"
    assert updated.discovered_count == 3
    assert events[0].agent == "Collector"
    assert events[0].message == "Searching"


def test_repository_tracks_autonomous_crawls_and_discovered_topics(tmp_path):
    repo = ResearchRepository(tmp_path / "research.sqlite")
    source = repo.get_source("sap-datasheet")

    crawl = repo.create_crawl_run(
        client_scope="standard",
        client_code=None,
        source_ids=["sap-datasheet"],
        seed_queries=["SAP IS-U EABL"],
        max_pages_per_source=1,
        max_topics=3,
        auto_queue_runs=True,
        auto_promote=True,
        auto_index=False,
    )
    repo.add_crawl_event(crawl.id, agent="Topic Scout", level="INFO", message="Loaded seeds")
    topic, is_new = repo.create_discovered_topic(
        source=source,
        url="https://example.test/eabl",
        title="EABL meter reading",
        topic="SAP IS-U EABL meter reading results",
        category="Meter Reading",
        objects=["EABL"],
        tags=["sap-isu", "meter-reading"],
        confidence_score=0.8,
    )
    repo.update_crawl_run(
        crawl.id,
        status="RUNNING",
        scout_status="COMPLETED",
        discovered_topic_count=1,
    )

    updated = repo.get_crawl_run(crawl.id)
    events = repo.list_crawl_events(crawl.id)
    topics = repo.list_discovered_topics()

    assert updated.status == "RUNNING"
    assert updated.scout_status == "COMPLETED"
    assert events[0].agent == "Topic Scout"
    assert is_new is True
    assert topics[0].id == topic.id
    assert topics[0].status == "DISCOVERED"


def test_research_api_creates_and_promotes_standard_candidate(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    create_resp = client.post(
        "/api/research/candidates",
        json={
            "scope": "standard",
            "source_id": "sap-datasheet",
            "url": "https://example.test/eabl",
            "title": "EABL meter reading result table",
            "raw_excerpt": "SAP table EABL stores meter reading result context for meter reading validation.",
        },
    )
    assert create_resp.status_code == 200
    candidate = create_resp.json()
    assert candidate["status"] == "AUDITED"
    assert candidate["kb_type"] == KBItemType.SAP_TABLE.value
    assert "EABL" in candidate["sap_objects"]

    promote_resp = client.post(
        f"/api/research/candidates/{candidate['id']}/promote-to-kb-draft",
        json={"scope": "standard"},
    )
    assert promote_resp.status_code == 200
    payload = promote_resp.json()
    assert payload["candidate"]["status"] == "PROMOTED"
    assert payload["kb_item"]["status"] == KBItemStatus.DRAFT.value

    (tmp_path / "standard").mkdir(parents=True, exist_ok=True)
    repo = KBItemRepository(tmp_path / "standard" / "assistant_kb.sqlite")
    item = repo.get_by_id(payload["kb_item"]["kb_id"])
    assert item is not None
    assert item.status == KBItemStatus.DRAFT.value
    sources = json.loads(item.sources_json)
    assert sources["research_candidate_id"] == candidate["id"]
    assert sources["source_id"] == "sap-datasheet"


def test_review_bulk_approve_indexes_all_drafts(tmp_path, monkeypatch):
    import src.assistant.retrieval.kb_indexer as kb_indexer

    indexed = []

    def fake_index(item, *, api_key=None, qdrant_url="http://localhost:6333"):
        indexed.append((item.kb_id, item.status))

    monkeypatch.setattr(kb_indexer, "index_approved_kb_item", fake_index)
    client = _client(tmp_path, monkeypatch)

    (tmp_path / "standard").mkdir(parents=True, exist_ok=True)
    repo = KBItemRepository(tmp_path / "standard" / "assistant_kb.sqlite")
    first, _ = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.SAP_TABLE,
        title="EABL meter reading table",
        content_markdown="EABL stores SAP IS-U meter reading result context.",
        tags=["sap-isu"],
        sap_objects=["EABL"],
        signals={},
        sources={},
        status=KBItemStatus.DRAFT,
    )
    second, _ = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.SAP_TABLE,
        title="ERCH billing document table",
        content_markdown="ERCH stores SAP IS-U billing document context.",
        tags=["sap-isu"],
        sap_objects=["ERCH"],
        signals={},
        sources={},
        status=KBItemStatus.DRAFT,
    )

    resp = client.post("/api/review/items/bulk-approve", json={"scope": "standard"})
    payload = resp.json()

    assert resp.status_code == 200
    assert payload["requested_count"] == 2
    assert payload["indexed_count"] == 2
    assert payload["failed_count"] == 0
    assert repo.get_by_id(first.kb_id).status == KBItemStatus.APPROVED.value
    assert repo.get_by_id(second.kb_id).status == KBItemStatus.APPROVED.value
    assert {item[0] for item in indexed} == {first.kb_id, second.kb_id}


def test_research_api_runs_agents_and_creates_kb_drafts(tmp_path, monkeypatch):
    import src.research.agents.orchestrator as orchestrator

    def fake_search(topic, source, limit=3, timeout=15):
        assert "EABL" in topic
        return ["https://example.test/eabl"]

    def fake_fetch(url, timeout=15):
        return CollectedDocument(
            url=url,
            title="EABL meter reading result table",
            text=(
                "SAP table EABL stores meter reading results. "
                "Meter reading validation can involve EL31 and EABLG for result context."
            ),
        )

    monkeypatch.setattr(orchestrator, "search_source_urls", fake_search)
    monkeypatch.setattr(orchestrator, "fetch_url_document", fake_fetch)
    client = _client(tmp_path, monkeypatch)

    resp = client.post(
        "/api/research/runs",
        json={
            "scope": "standard",
            "topic": "EABL meter reading validation",
            "source_ids": ["sap-datasheet"],
            "max_results_per_source": 1,
            "auto_promote": True,
        },
    )

    assert resp.status_code == 202
    run_id = resp.json()["id"]

    run_resp = client.get(f"/api/research/runs/{run_id}")
    run = run_resp.json()
    assert run["status"] == "COMPLETED"
    assert run["agents"]["Collector"] == "COMPLETED"
    assert run["agents"]["Normalizer"] == "COMPLETED"
    assert run["agents"]["Auditor"] == "COMPLETED"
    assert run["agents"]["Ingestor"] == "COMPLETED"
    assert run["discovered_count"] == 1
    assert run["fetched_count"] == 1
    assert run["candidate_count"] == 1
    assert run["promoted_count"] == 1

    events = client.get(f"/api/research/runs/{run_id}/events").json()
    assert any(event["agent"] == "Collector" for event in events)
    assert any(event["agent"] == "Ingestor" and event["level"] == "SUCCESS" for event in events)

    items = client.get("/api/review/items?scope=standard&status=DRAFT").json()
    assert any(item["type"] == KBItemType.SAP_TABLE.value and "EABL" in item["sap_objects"] for item in items)


def test_autonomous_crawler_discovers_topics_and_queues_runs(tmp_path, monkeypatch):
    import src.research.agents.crawler as crawler

    def fake_search(query, source, limit=3, timeout=15):
        assert "EABL" in query
        return ["https://example.test/eabl"]

    def fake_fetch(url, timeout=15):
        return CollectedDocument(
            url=url,
            title="EABL meter reading result table",
            text="SAP IS-U table EABL stores meter reading result data for validation and billing.",
        )

    def fake_run(db_path, data_root, run_id, api_key=None, qdrant_url="http://localhost:6333"):
        repo = ResearchRepository(db_path)
        repo.update_run(
            run_id,
            status="COMPLETED",
            collector_status="COMPLETED",
            normalizer_status="COMPLETED",
            auditor_status="COMPLETED",
            ingestor_status="SKIPPED",
            indexer_status="SKIPPED",
        )

    monkeypatch.setattr(crawler, "robots_allows", lambda url: True)
    monkeypatch.setattr(crawler, "search_source_urls", fake_search)
    monkeypatch.setattr(crawler, "fetch_url_document", fake_fetch)
    monkeypatch.setattr(crawler, "run_research_pipeline", fake_run)
    client = _client(tmp_path, monkeypatch)

    resp = client.post(
        "/api/research/crawls",
        json={
            "scope": "standard",
            "source_ids": ["sap-datasheet"],
            "seed_queries": ["SAP IS-U EABL"],
            "max_pages_per_source": 1,
            "max_topics": 1,
            "auto_queue_runs": True,
            "auto_promote": True,
            "auto_index": False,
        },
    )

    assert resp.status_code == 202
    crawl_id = resp.json()["id"]
    crawl = client.get(f"/api/research/crawls/{crawl_id}").json()
    assert crawl["status"] == "COMPLETED"
    assert crawl["agents"]["Source Crawler"] == "COMPLETED"
    assert crawl["agents"]["Topic Extractor"] == "COMPLETED"
    assert crawl["agents"]["Run Queuer"] == "COMPLETED"
    assert crawl["discovered_url_count"] == 1
    assert crawl["fetched_page_count"] == 1
    assert crawl["discovered_topic_count"] == 1
    assert crawl["queued_run_count"] == 1

    topics = client.get("/api/research/discovered-topics").json()
    assert any("EABL" in topic["objects"] and topic["status"] == "INGESTED" for topic in topics)
    runs = client.get("/api/research/runs").json()
    assert any("EABL" in run["topic"] for run in runs)


def test_topic_catalog_endpoint_lists_curated_topics(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/api/research/topic-catalog")
    topics = resp.json()

    assert resp.status_code == 200
    assert len(topics) >= 140
    assert any(topic["id"] == "md-business-partner-contract-account" for topic in topics)
    assert any(topic["origin"] == "topic_scout" for topic in topics)
    assert any(topic["origin"] == "expertise_pack" for topic in topics)
    assert any(topic["category"] == "MaKo / EDIFACT" for topic in topics)
    assert any(topic["category"] == "Customizing / SPRO" for topic in topics)
    assert any(topic["category"] == "ABAP / Enhancements" for topic in topics)
    assert any(topic["category"] == "Country Market Rules" for topic in topics)


def test_topic_picker_broadens_default_autonomous_crawl_coverage():
    topics = pick_catalog_topics(
        [
            "SAP IS-U transactions navigation SPRO customizing",
            "SAP IS-U error messages function modules country rules",
        ],
        limit=20,
    )
    categories = {topic.category for topic in topics}

    assert "Customizing / SPRO" in categories
    assert "Messages / Errors" in categories
    assert "ABAP / Enhancements" in categories
    assert "Country Market Rules" in categories


def test_catalog_run_queues_many_topics_and_ingests_drafts(tmp_path, monkeypatch):
    import src.research.agents.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "search_source_urls", lambda *args, **kwargs: [])
    client = _client(tmp_path, monkeypatch)

    resp = client.post(
        "/api/research/runs/catalog",
        json={
            "scope": "standard",
            "category": "Master Data",
            "limit": 3,
            "max_results_per_source": 1,
            "auto_promote": True,
        },
    )

    assert resp.status_code == 202
    payload = resp.json()
    assert payload["queued"] == 3

    runs = client.get("/api/research/runs").json()
    completed = [run for run in runs if run["status"] == "COMPLETED"]
    assert len(completed) >= 3
    assert sum(run["promoted_count"] for run in completed[:3]) >= 3

    items = client.get("/api/review/items?scope=standard&status=DRAFT").json()
    assert len(items) >= 3


def test_research_run_can_auto_approve_and_index_low_risk_candidates(tmp_path, monkeypatch):
    import src.research.agents.orchestrator as orchestrator

    indexed = []

    monkeypatch.setattr(orchestrator, "search_source_urls", lambda *args, **kwargs: [])

    def fake_index(item, *, api_key=None, qdrant_url="http://localhost:6333"):
        indexed.append((item.kb_id, item.status, qdrant_url))

    monkeypatch.setattr(orchestrator, "index_approved_kb_item", fake_index)
    client = _client(tmp_path, monkeypatch)

    resp = client.post(
        "/api/research/runs",
        json={
            "scope": "standard",
            "topic": "SAP IS-U business partner contract account FKKVKP",
            "source_ids": ["sap-datasheet", "leanx"],
            "max_results_per_source": 1,
            "auto_promote": True,
            "auto_index": True,
        },
    )

    assert resp.status_code == 202
    run_id = resp.json()["id"]
    run = client.get(f"/api/research/runs/{run_id}").json()
    assert run["agents"]["Indexer"] == "COMPLETED"
    assert run["promoted_count"] == 1
    assert run["indexed_count"] == 1

    approved = client.get("/api/review/items?scope=standard&status=APPROVED").json()
    assert any("FKKVKP" in item["sap_objects"] for item in approved)
    assert indexed and indexed[0][1] == KBItemStatus.APPROVED.value


def test_research_run_uses_seed_catalog_when_search_finds_no_urls(tmp_path, monkeypatch):
    import src.research.agents.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "search_source_urls", lambda *args, **kwargs: [])
    client = _client(tmp_path, monkeypatch)

    resp = client.post(
        "/api/research/runs",
        json={
            "scope": "standard",
            "topic": "SAP IS-U business partner contract account FKKVKP",
            "source_ids": ["sap-datasheet", "leanx"],
            "max_results_per_source": 1,
            "auto_promote": True,
        },
    )

    assert resp.status_code == 202
    run_id = resp.json()["id"]
    run = client.get(f"/api/research/runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    assert run["discovered_count"] == 0
    assert run["fetched_count"] == 1
    assert run["candidate_count"] == 1
    assert run["promoted_count"] == 1

    events = client.get(f"/api/research/runs/{run_id}/events").json()
    assert any("safe internal SAP object seed" in event["message"] for event in events)
    items = client.get("/api/review/items?scope=standard&status=DRAFT").json()
    assert any(item["type"] == KBItemType.SAP_TABLE.value and "FKKVKP" in item["sap_objects"] for item in items)


def test_research_api_requires_client_for_client_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps

    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
    from src.web.app import app
    from starlette.testclient import TestClient

    client = TestClient(app)

    resp = client.post(
        "/api/research/candidates",
        json={
            "scope": "client",
            "source_id": "sap-help",
            "title": "Move-in process",
            "raw_excerpt": "Move-in creates contracts and links business partner data.",
        },
    )

    assert resp.status_code == 400
    assert "No client selected" in resp.json()["error"]


def test_reference_only_source_cannot_be_promoted(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    create_resp = client.post(
        "/api/research/candidates",
        json={
            "scope": "standard",
            "source_id": "sap-press-rheinwerk",
            "title": "Book note",
            "raw_excerpt": "Manual reference about SAP IS-U billing.",
        },
    )
    assert create_resp.status_code == 200
    candidate = create_resp.json()
    assert candidate["copyright_risk"] == "HIGH"

    promote_resp = client.post(
        f"/api/research/candidates/{candidate['id']}/promote-to-kb-draft",
        json={"scope": "standard"},
    )

    assert promote_resp.status_code == 400
    assert "High copyright risk" in promote_resp.json()["error"]


def test_ingest_page_exposes_research_workflow(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/ingest")

    assert resp.status_code == 200
    assert "SAP IS-U Research Candidates" in resp.text
    assert "Research Agent Runs" in resp.text
    assert "Autonomous Source Crawler" in resp.text
    assert "startAutonomousCrawl()" in resp.text
    assert "Approve & Index All" in resp.text
    assert "startResearchRun()" in resp.text
    assert "Run Full Catalog" in resp.text
    assert "Auto-approve & index low-risk drafts" in resp.text
    assert "Indexer" in resp.text
    assert "Starter topics" in resp.text
    assert "FI-CA FKKVKP" in resp.text
    assert "createResearchCandidate()" in resp.text
    assert "promoteResearchCandidate()" in resp.text
