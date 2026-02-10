"""
M5 Acceptance Tests: OpenAI Synthesis Pipeline (Structured Outputs)

Tests cover schema validation and end-to-end with OpenAI mocked per PLAN.md section 13.
"""
import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.assistant.ingestion.schema import SYNTHESIS_SCHEMA
from src.assistant.ingestion.synthesis import (
    SynthesisError,
    SynthesisPipeline,
    validate_synthesis_output,
)


# --- Schema validation tests ---

def test_validate_valid_output():
    """Test valid synthesis output passes validation."""
    data = {
        "kb_items": [
            {
                "type": "RUNBOOK",
                "title": "Test Title",
                "content_markdown": "# Content",
                "tags": ["tag1", "tag2"],
                "sap_objects": ["OBJ1"],
                "signals": {"module": "IDEX"},
            }
        ]
    }

    errors = validate_synthesis_output(data)
    assert errors == []


def test_validate_multiple_items():
    """Test valid output with multiple items."""
    data = {
        "kb_items": [
            {
                "type": "RUNBOOK",
                "title": "Title 1",
                "content_markdown": "# Content 1",
                "tags": [],
                "sap_objects": [],
                "signals": {},
            },
            {
                "type": "GLOSSARY",
                "title": "Title 2",
                "content_markdown": "# Content 2",
                "tags": ["tag"],
                "sap_objects": [],
                "signals": {},
            },
        ]
    }

    errors = validate_synthesis_output(data)
    assert errors == []


def test_validate_missing_kb_items():
    """Test missing kb_items field."""
    errors = validate_synthesis_output({})
    assert len(errors) == 1
    assert "kb_items" in errors[0]


def test_validate_empty_kb_items():
    """Test empty kb_items array."""
    errors = validate_synthesis_output({"kb_items": []})
    assert len(errors) == 1
    assert "non-empty" in errors[0]


def test_validate_invalid_type():
    """Test invalid type enum value."""
    data = {
        "kb_items": [
            {
                "type": "INVALID_TYPE",
                "title": "Title",
                "content_markdown": "# Content",
                "tags": [],
                "sap_objects": [],
                "signals": {},
            }
        ]
    }

    errors = validate_synthesis_output(data)
    assert len(errors) == 1
    assert "INVALID_TYPE" in errors[0]


def test_validate_all_valid_types():
    """Test all valid KB item types are accepted."""
    valid_types = [
        "INCIDENT_PATTERN", "ROOT_CAUSE", "RESOLUTION",
        "VERIFICATION_STEPS", "CUSTOMIZING", "ABAP_TECH_NOTE",
        "GLOSSARY", "RUNBOOK",
    ]

    for item_type in valid_types:
        data = {
            "kb_items": [
                {
                    "type": item_type,
                    "title": f"Title for {item_type}",
                    "content_markdown": "# Content",
                    "tags": [],
                    "sap_objects": [],
                    "signals": {},
                }
            ]
        }
        errors = validate_synthesis_output(data)
        assert errors == [], f"Type {item_type} should be valid, got errors: {errors}"


def test_validate_empty_title():
    """Test empty title is rejected."""
    data = {
        "kb_items": [
            {
                "type": "RUNBOOK",
                "title": "",
                "content_markdown": "# Content",
                "tags": [],
                "sap_objects": [],
                "signals": {},
            }
        ]
    }

    errors = validate_synthesis_output(data)
    assert any("title" in e for e in errors)


def test_validate_missing_required_fields():
    """Test missing required fields are reported."""
    data = {
        "kb_items": [
            {"type": "RUNBOOK"}
        ]
    }

    errors = validate_synthesis_output(data)
    # Missing: title, content_markdown, tags, sap_objects, signals
    assert len(errors) == 5


def test_validate_tags_must_be_string_array():
    """Test tags must be array of strings."""
    data = {
        "kb_items": [
            {
                "type": "RUNBOOK",
                "title": "Title",
                "content_markdown": "# Content",
                "tags": [1, 2, 3],
                "sap_objects": [],
                "signals": {},
            }
        ]
    }

    errors = validate_synthesis_output(data)
    assert any("tags" in e for e in errors)


def test_validate_signals_must_be_object():
    """Test signals must be an object."""
    data = {
        "kb_items": [
            {
                "type": "RUNBOOK",
                "title": "Title",
                "content_markdown": "# Content",
                "tags": [],
                "sap_objects": [],
                "signals": "not an object",
            }
        ]
    }

    errors = validate_synthesis_output(data)
    assert any("signals" in e for e in errors)


def test_validate_not_a_dict():
    """Test non-dict input."""
    errors = validate_synthesis_output("not a dict")
    assert len(errors) == 1
    assert "JSON object" in errors[0]


# --- SynthesisPipeline tests (mocked OpenAI) ---

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    with patch("src.assistant.ingestion.synthesis.OpenAI") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client


def _make_response(output_text: str):
    """Helper to create mock response."""
    response = Mock()
    response.output_text = output_text
    return response


def test_synthesis_pipeline_success(mock_openai_client):
    """Test successful synthesis end-to-end with mocked OpenAI."""
    valid_output = {
        "kb_items": [
            {
                "type": "RUNBOOK",
                "title": "IDEX Monitoring Procedure",
                "content_markdown": "# Steps\n\n1. Check EDATEXMON01\n2. Verify processing",
                "tags": ["IDEX", "UTILMD"],
                "sap_objects": ["EDATEXMON01"],
                "signals": {"module": "IDEX", "process": "GPKE"},
            }
        ]
    }

    mock_openai_client.responses.create.return_value = _make_response(
        json.dumps(valid_output)
    )

    pipeline = SynthesisPipeline(api_key="test-key")
    result = pipeline.synthesize("Some SAP IS-U knowledge content")

    assert result == valid_output
    assert len(result["kb_items"]) == 1
    assert result["kb_items"][0]["type"] == "RUNBOOK"

    # Verify API was called
    mock_openai_client.responses.create.assert_called_once()


def test_synthesis_pipeline_retry_on_invalid(mock_openai_client):
    """Test controlled retry on invalid output per PLAN.md section 8.3."""
    invalid_output = {"kb_items": []}
    valid_output = {
        "kb_items": [
            {
                "type": "GLOSSARY",
                "title": "Valid Item",
                "content_markdown": "# Valid",
                "tags": [],
                "sap_objects": [],
                "signals": {},
            }
        ]
    }

    # First call returns invalid, second returns valid
    mock_openai_client.responses.create.side_effect = [
        _make_response(json.dumps(invalid_output)),
        _make_response(json.dumps(valid_output)),
    ]

    pipeline = SynthesisPipeline(api_key="test-key")
    result = pipeline.synthesize("Content to synthesize")

    assert result == valid_output
    assert mock_openai_client.responses.create.call_count == 2


def test_synthesis_pipeline_fails_after_retries(mock_openai_client):
    """Test synthesis marked FAILED after all retries per PLAN.md section 8.3."""
    invalid_output = {"kb_items": []}

    mock_openai_client.responses.create.return_value = _make_response(
        json.dumps(invalid_output)
    )

    pipeline = SynthesisPipeline(api_key="test-key")

    with pytest.raises(SynthesisError, match="failed after"):
        pipeline.synthesize("Content to synthesize")

    # 1 initial + 1 retry = 2 calls
    assert mock_openai_client.responses.create.call_count == 2


def test_synthesis_pipeline_handles_invalid_json(mock_openai_client):
    """Test synthesis handles invalid JSON response."""
    mock_openai_client.responses.create.return_value = _make_response(
        "not valid json {{"
    )

    pipeline = SynthesisPipeline(api_key="test-key")

    with pytest.raises(SynthesisError, match="failed after"):
        pipeline.synthesize("Content")


def test_synthesis_pipeline_handles_api_error(mock_openai_client):
    """Test synthesis handles API errors."""
    mock_openai_client.responses.create.side_effect = Exception("API timeout")

    pipeline = SynthesisPipeline(api_key="test-key")

    with pytest.raises(SynthesisError, match="failed after"):
        pipeline.synthesize("Content")
