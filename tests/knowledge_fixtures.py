"""Deterministic embeddings for synthetic records only."""

from hashlib import sha256


class SyntheticEmbeddings:
    model = "text-embedding-3-small"
    version = "1"
    dimensions = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for word in text.casefold().split():
                index = (
                    int.from_bytes(sha256(word.encode()).digest()[:4], "big")
                    % self.dimensions
                )
                vec[index] += 1.0
            results.append(vec)
        return results


class BrokenEmbeddings(SyntheticEmbeddings):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


def configure_invalid_embedding_port(monkeypatch, port):
    import httpx

    def unexpected_request(request):
        raise AssertionError("Invalid gateway port reached the transport")

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: client_type(
            transport=httpx.MockTransport(unexpected_request), **kw
        ),
    )
    monkeypatch.setenv("LLM_API_GATEWAY", f"https://example.invalid:{port}/v1")
    monkeypatch.setenv("LLM_API_TOKEN", "synthetic-test-token")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("EMBEDDING_VERSION", "1")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")
    monkeypatch.delenv("DISABLE_EMBEDDING_REQUESTS")
