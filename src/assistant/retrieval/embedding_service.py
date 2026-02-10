"""
Embedding service using OpenAI text-embedding-3-large per PLAN.md section 4.2.
"""
from openai import OpenAI


class EmbeddingService:
    """Generates embeddings using text-embedding-3-large (3072 dimensions)."""

    MODEL = "text-embedding-3-large"
    DIMENSIONS = 3072

    def __init__(self, api_key: str | None = None):
        self.client = OpenAI(api_key=api_key) if api_key else OpenAI()

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector (3072 dimensions)
        """
        response = self.client.embeddings.create(
            model=self.MODEL,
            input=text,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        response = self.client.embeddings.create(
            model=self.MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]
