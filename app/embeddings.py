"""Bounded gateway embedding calls, independent of the generation agent."""

import math
import os
from typing import Protocol
from urllib.parse import urlsplit

import httpx


class EmbeddingUnavailable(RuntimeError):
    pass


class EmbeddingClient(Protocol):
    model: str
    version: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int) -> None:
    if len(vectors) != count or any(not _valid_vector(v, dimensions) for v in vectors):
        raise EmbeddingUnavailable("Invalid embedding batch from embedding service.")


def _valid_vector(vector: list[float], dimensions: int) -> bool:
    return (
        len(vector) == dimensions
        and all(
            type(x) in (float, int) and math.isfinite(x) and abs(x) <= 3.4028234e38
            for x in vector
        )
        and any(abs(x) >= 1.4013e-45 for x in vector)
    )


class GatewayEmbeddings:
    def __init__(self) -> None:
        self.model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self.version = os.environ.get("EMBEDDING_VERSION", "1")
        try:
            self.dimensions = int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))
            if not 1 <= self.dimensions <= 16000:
                raise ValueError
        except ValueError:
            raise EmbeddingUnavailable("Invalid embedding configuration.") from None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if os.environ.get("DISABLE_EMBEDDING_REQUESTS") == "1":
            raise EmbeddingUnavailable("Embedding requests are disabled.")
        base = os.environ.get("LLM_API_GATEWAY", "").rstrip("/")
        token = os.environ.get("LLM_API_TOKEN", "")
        try:
            url = urlsplit(base)
            if (
                not token
                or url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError
        except ValueError:
            raise EmbeddingUnavailable("Embedding gateway is not configured.") from None
        vectors = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                for pos in range(0, len(texts), 16):
                    batch = texts[pos : pos + 16]
                    response = await client.post(
                        base + "/embeddings",
                        headers={"Authorization": "Bearer " + token},
                        json={
                            "model": self.model,
                            "dimensions": self.dimensions,
                            "input": batch,
                        },
                    )
                    response.raise_for_status()
                    data = sorted(
                        response.json()["data"], key=lambda item: item["index"]
                    )
                    if [item["index"] for item in data] != list(range(len(batch))):
                        raise ValueError
                    part = [item["embedding"] for item in data]
                    validate_vectors(part, len(batch), self.dimensions)
                    vectors.extend(part)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError):
            raise EmbeddingUnavailable("Embedding service unavailable.") from None
        return vectors


def get_embedding_client() -> EmbeddingClient:
    return GatewayEmbeddings()
