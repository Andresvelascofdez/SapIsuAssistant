"""
OpenAI synthesis pipeline per PLAN.md section 8.3.

Calls Responses API with structured output, validates schema, handles retries.
"""
import json
from typing import Any

from openai import OpenAI

from .schema import SYNTHESIS_SCHEMA
from src.assistant.storage.models import KBItemType


SYNTHESIS_SYSTEM_PROMPT = """You are a SAP IS-U knowledge engineer. Your task is to analyze
the provided content and synthesize it into structured knowledge base items.

Each item must have:
- type: One of INCIDENT_PATTERN, ROOT_CAUSE, RESOLUTION, VERIFICATION_STEPS, CUSTOMIZING, ABAP_TECH_NOTE, GLOSSARY, RUNBOOK
- title: A clear, concise title
- content_markdown: Detailed content in Markdown format
- tags: Relevant tags (e.g., IDEX, UTILMD, MaKo, GPKE)
- sap_objects: SAP transaction codes, programs, tables, or objects mentioned
- signals: Additional metadata object with keys like module, process, country

Extract all relevant knowledge items from the content. Be thorough but precise.
Return valid JSON matching the required schema."""

VALID_TYPES = {t.value for t in KBItemType}


def validate_synthesis_output(data: Any) -> list[str]:
    """
    Validate synthesis output against schema per PLAN.md section 9.

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not isinstance(data, dict):
        return ["Output must be a JSON object"]

    if "kb_items" not in data:
        return ["Missing required field: kb_items"]

    kb_items = data["kb_items"]
    if not isinstance(kb_items, list):
        return ["kb_items must be an array"]

    if len(kb_items) == 0:
        return ["kb_items must be non-empty"]

    for i, item in enumerate(kb_items):
        prefix = f"kb_items[{i}]"

        if not isinstance(item, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Required fields
        for field in ["type", "title", "content_markdown", "tags", "sap_objects", "signals"]:
            if field not in item:
                errors.append(f"{prefix}: missing required field '{field}'")

        # Type enum
        if "type" in item and item["type"] not in VALID_TYPES:
            errors.append(f"{prefix}.type: invalid value '{item['type']}', must be one of {VALID_TYPES}")

        # Non-empty strings
        for field in ["title", "content_markdown"]:
            if field in item and (not isinstance(item[field], str) or not item[field].strip()):
                errors.append(f"{prefix}.{field}: must be a non-empty string")

        # Arrays of strings
        for field in ["tags", "sap_objects"]:
            if field in item:
                if not isinstance(item[field], list):
                    errors.append(f"{prefix}.{field}: must be an array")
                elif not all(isinstance(v, str) for v in item[field]):
                    errors.append(f"{prefix}.{field}: all items must be strings")

        # Signals object
        if "signals" in item and not isinstance(item["signals"], dict):
            errors.append(f"{prefix}.signals: must be an object")

    return errors


class SynthesisPipeline:
    """
    OpenAI synthesis pipeline per PLAN.md section 8.3.

    Model: gpt-5.2, reasoning effort: xhigh
    On schema invalid: 1 controlled retry, then mark FAILED per PLAN.md section 7.
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-5.2"):
        """
        Initialize pipeline.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model name (default gpt-5.2 per PLAN.md)
        """
        self.client = OpenAI(api_key=api_key) if api_key else OpenAI()
        self.model = model

    def synthesize(self, extracted_text: str, max_retries: int = 1) -> dict:
        """
        Synthesize extracted text into structured KB items per PLAN.md section 8.3.

        Args:
            extracted_text: Text extracted from input document
            max_retries: Number of retries on invalid output (default 1 per PLAN.md)

        Returns:
            Validated synthesis result dict with kb_items

        Raises:
            SynthesisError: If output is invalid after all retries
        """
        last_errors = []

        for attempt in range(1 + max_retries):
            try:
                response = self.client.responses.create(
                    model=self.model,
                    instructions=SYNTHESIS_SYSTEM_PROMPT,
                    input=f"Analyze and synthesize the following content:\n\n{extracted_text}",
                    text={"format": {"type": "json_schema", "name": "kb_synthesis", "schema": SYNTHESIS_SCHEMA}},
                    reasoning={"effort": "high"},
                )

                raw_text = response.output_text
                data = json.loads(raw_text)
                errors = validate_synthesis_output(data)

                if not errors:
                    return data

                last_errors = errors

            except json.JSONDecodeError as e:
                last_errors = [f"Invalid JSON: {e}"]
            except Exception as e:
                last_errors = [f"API error: {e}"]

        raise SynthesisError(
            f"Synthesis failed after {1 + max_retries} attempts. Errors: {last_errors}"
        )


class SynthesisError(Exception):
    """Raised when synthesis fails after all retries."""
    pass
