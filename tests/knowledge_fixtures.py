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
