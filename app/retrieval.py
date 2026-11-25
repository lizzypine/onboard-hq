"""Reciprocal rank fusion and bounded adjacent passage context."""

from collections import defaultdict, deque
from fractions import Fraction
from itertools import pairwise

from app.knowledge_models import KnowledgeChunk
from app.qa_models import RankedPassage

PATH_LIMIT = 20
FUSION_CONSTANT = 60
CONTEXT_LIMIT = 12
CONTEXT_CHARACTERS = 24_000
ANCHOR_LIMIT = 8


def _score(rank: int | None) -> Fraction:
    return Fraction(1, FUSION_CONSTANT + rank) if rank else Fraction(0)


def _fuse(
    chunks: dict[int, KnowledgeChunk], keywords: list[int], vectors: list[int]
) -> dict[int, RankedPassage]:
    keyword_ranks = {cid: rank for rank, cid in enumerate(keywords, 1)}
    vector_ranks = {cid: rank for rank, cid in enumerate(vectors, 1)}
    order = sorted(
        keyword_ranks.keys() | vector_ranks.keys(),
        key=lambda cid: (
            -(_score(keyword_ranks.get(cid)) + _score(vector_ranks.get(cid))),
            cid,
        ),
    )
    return {
        cid: RankedPassage(
            chunk=chunks[cid],
            keyword_rank=keyword_ranks.get(cid),
            vector_rank=vector_ranks.get(cid),
            fused_rank=rank,
        )
        for rank, cid in enumerate(order, 1)
    }


def _neighbors(chunks: list[KnowledgeChunk]) -> dict[int, list[int]]:
    neighbors: dict[int, list[int]] = defaultdict(list)
    sections = sorted(chunks, key=lambda c: (c.version_id, c.char_start))
    for first, second in pairwise(sections):
        if (first.version_id, first.section) == (second.version_id, second.section):
            neighbors[first.id].append(second.id)
            neighbors[second.id].append(first.id)
    return neighbors


class _Context:
    def __init__(
        self, chunks: dict[int, KnowledgeChunk], ranked: dict[int, RankedPassage]
    ):
        self.chunks = chunks
        self.ranked = ranked
        self.selected: dict[int, KnowledgeChunk] = {}
        self.remaining = CONTEXT_CHARACTERS

    def add(self, cid: int) -> bool:
        chunk = self.chunks[cid]
        if (
            cid in self.selected
            or len(self.selected) >= CONTEXT_LIMIT
            or len(chunk.text) > self.remaining
            or any(
                c.version_id == chunk.version_id
                and c.char_start < chunk.char_end
                and chunk.char_start < c.char_end
                for c in self.selected.values()
            )
        ):
            return False
        self.selected[cid] = chunk
        self.remaining -= len(chunk.text)
        self.ranked.setdefault(cid, RankedPassage(chunk=chunk)).context_order = len(
            self.selected
        )
        return True


def merge_paths(
    chunks: list[KnowledgeChunk], keywords: list[int], vectors: list[int]
) -> list[RankedPassage]:
    by_id = {c.id: c for c in chunks}
    ranked = _fuse(by_id, keywords, vectors)
    context = _Context(by_id, ranked)
    # Reserve some context for exceptions and continuations. Expand only
    # through adjacent chunks, so a repeated heading elsewhere cannot pull in
    # an entire chapter or table of contents.
    candidates = list(ranked)
    for cid in candidates[:ANCHOR_LIMIT]:
        context.add(cid)
    neighbors = _neighbors(chunks)
    visited = set(context.selected)
    adjacent = deque(
        neighbor for cid in context.selected for neighbor in neighbors[cid]
    )
    while adjacent and len(context.selected) < CONTEXT_LIMIT:
        cid = adjacent.popleft()
        if cid not in visited:
            visited.add(cid)
            if context.add(cid):
                adjacent.extend(neighbors[cid])
    for cid in candidates[ANCHOR_LIMIT:]:
        context.add(cid)
    return list(ranked.values())
