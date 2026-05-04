"""Environment loading and OpenAI synthesis schema tests."""
import os

from src.assistant.ingestion.schema import SYNTHESIS_SCHEMA
from src.shared.env_loader import load_env_file, read_env_file, set_env_value


def test_env_loader_reads_bom_file_and_loads_key(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("\ufeffOPENAI_API_KEY=test-key\nOTHER=value\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    values = load_env_file(env_path)

    assert values["OPENAI_API_KEY"] == "test-key"
    assert os.environ["OPENAI_API_KEY"] == "test-key"


def test_set_env_value_updates_without_dropping_other_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER=value\nOPENAI_API_KEY=old\n", encoding="utf-8")

    set_env_value("OPENAI_API_KEY", "new", env_path)
    values = read_env_file(env_path)

    assert values["OPENAI_API_KEY"] == "new"
    assert values["OTHER"] == "value"


def test_synthesis_schema_has_strict_signals_object():
    signals_schema = SYNTHESIS_SCHEMA["properties"]["kb_items"]["items"]["properties"]["signals"]

    assert signals_schema["additionalProperties"] is False
    assert signals_schema["required"] == ["module", "process", "country", "sap_area"]
    assert set(signals_schema["properties"]) == {"module", "process", "country", "sap_area"}
