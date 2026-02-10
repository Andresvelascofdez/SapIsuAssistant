"""
Token counting utilities using tiktoken per PLAN.md section 2.
"""
import tiktoken

# Cache encoding at module level for performance
_encoding = None


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.encoding_for_model("gpt-4o")
    return _encoding


def count_tokens(text: str) -> int:
    """Count tokens in text."""
    return len(_get_encoding().encode(text))


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """Truncate text to fit within max_tokens."""
    enc = _get_encoding()
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return enc.decode(tokens[:max_tokens])
