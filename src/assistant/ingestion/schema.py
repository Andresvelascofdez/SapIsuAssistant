"""
JSON schema for synthesis structured output per PLAN.md section 9.
"""

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "kb_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "INCIDENT_PATTERN",
                            "ROOT_CAUSE",
                            "RESOLUTION",
                            "VERIFICATION_STEPS",
                            "CUSTOMIZING",
                            "ABAP_TECH_NOTE",
                            "GLOSSARY",
                            "RUNBOOK",
                        ]
                    },
                    "title": {"type": "string", "minLength": 1},
                    "content_markdown": {"type": "string", "minLength": 1},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "sap_objects": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "signals": {"type": "object"},
                },
                "required": ["type", "title", "content_markdown", "tags", "sap_objects", "signals"],
                "additionalProperties": False,
            },
            "minItems": 1,
        }
    },
    "required": ["kb_items"],
    "additionalProperties": False,
}
