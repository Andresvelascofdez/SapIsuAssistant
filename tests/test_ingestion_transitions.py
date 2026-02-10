"""
Tests for ingestion status transitions per PLAN.md section 7.

Validates the ingestion lifecycle: DRAFT -> SYNTHESIZED -> APPROVED/REJECTED
and DRAFT -> FAILED.
"""
import pytest

from src.assistant.storage.ingestion_repository import IngestionRepository
from src.assistant.storage.models import IngestionStatus


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "test_kb.sqlite"
    return IngestionRepository(db)


def _make_ingestion(repo, status=IngestionStatus.DRAFT):
    return repo.create(
        client_scope="standard",
        client_code=None,
        input_kind="text",
        input_hash="abc123",
        input_name="test.txt",
        model_used="gpt-5.2",
        reasoning_effort="xhigh",
        status=status,
    )


def test_ingestion_created_as_draft(repo):
    ing = _make_ingestion(repo)
    assert ing.status == IngestionStatus.DRAFT.value


def test_draft_to_synthesized(repo):
    ing = _make_ingestion(repo)
    updated = repo.update_status(ing.ingestion_id, IngestionStatus.SYNTHESIZED)
    assert updated.status == IngestionStatus.SYNTHESIZED.value


def test_draft_to_failed(repo):
    ing = _make_ingestion(repo)
    updated = repo.update_status(ing.ingestion_id, IngestionStatus.FAILED)
    assert updated.status == IngestionStatus.FAILED.value


def test_synthesized_to_approved(repo):
    ing = _make_ingestion(repo)
    repo.update_status(ing.ingestion_id, IngestionStatus.SYNTHESIZED)
    updated = repo.update_status(ing.ingestion_id, IngestionStatus.APPROVED)
    assert updated.status == IngestionStatus.APPROVED.value


def test_synthesized_to_rejected(repo):
    ing = _make_ingestion(repo)
    repo.update_status(ing.ingestion_id, IngestionStatus.SYNTHESIZED)
    updated = repo.update_status(ing.ingestion_id, IngestionStatus.REJECTED)
    assert updated.status == IngestionStatus.REJECTED.value


def test_update_status_updates_timestamp(repo):
    ing = _make_ingestion(repo)
    original_updated = ing.updated_at
    updated = repo.update_status(ing.ingestion_id, IngestionStatus.SYNTHESIZED)
    assert updated.updated_at >= original_updated


def test_list_by_scope_filters_status(repo):
    ing1 = _make_ingestion(repo)
    ing2 = _make_ingestion(repo)
    repo.update_status(ing1.ingestion_id, IngestionStatus.SYNTHESIZED)

    synthesized = repo.list_by_scope("standard", status=IngestionStatus.SYNTHESIZED)
    drafts = repo.list_by_scope("standard", status=IngestionStatus.DRAFT)

    assert len(synthesized) == 1
    assert synthesized[0].ingestion_id == ing1.ingestion_id
    assert len(drafts) == 1
    assert drafts[0].ingestion_id == ing2.ingestion_id


def test_update_nonexistent_returns_none(repo):
    result = repo.update_status("nonexistent-id", IngestionStatus.SYNTHESIZED)
    assert result is None


def test_full_lifecycle_draft_to_approved(repo):
    """Full lifecycle: DRAFT -> SYNTHESIZED -> APPROVED."""
    ing = _make_ingestion(repo)
    assert ing.status == IngestionStatus.DRAFT.value

    ing = repo.update_status(ing.ingestion_id, IngestionStatus.SYNTHESIZED)
    assert ing.status == IngestionStatus.SYNTHESIZED.value

    ing = repo.update_status(ing.ingestion_id, IngestionStatus.APPROVED)
    assert ing.status == IngestionStatus.APPROVED.value


def test_full_lifecycle_draft_to_rejected(repo):
    """Full lifecycle: DRAFT -> SYNTHESIZED -> REJECTED."""
    ing = _make_ingestion(repo)
    ing = repo.update_status(ing.ingestion_id, IngestionStatus.SYNTHESIZED)
    ing = repo.update_status(ing.ingestion_id, IngestionStatus.REJECTED)
    assert ing.status == IngestionStatus.REJECTED.value
