"""Controlled source manifest, explicit draft ingestion and embedding-space activation."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from app.database import create_pool, database_url
from app.embeddings import get_embedding_client
from app.knowledge import reindex
from app.knowledge_models import (
    DraftRequest,
    KnowledgeScope,
    OperationReceipt,
    SourceIdentity,
)
from app.repository.knowledge import KnowledgeRepository
from app.source_extraction import MAX_BYTES, SourceError, extract_source

SOURCE_DIR = Path(__file__).resolve().parents[1] / "knowledge"
INTERNAL_ISSUES = [
    "Confirm the designated onboarding and licensing contact roles.",
    "Resolve the unidentified recipient in “include my name”.",
    "Resolve the six-day PDMP account recreation conflict with official existing-account guidance.",
    "Confirm conditional qualifications and issuing-authority submission steps.",
]


def manifest() -> list[SourceIdentity]:
    official = [
        SourceIdentity.model_validate(s)
        for s in json.loads((SOURCE_DIR / "sources.json").read_text())
    ]
    return [
        SourceIdentity(
            source_key="internal-guide",
            title="Internal licensing guide",
            publisher="Onboarding team",
            url=None,
            media_type="text/plain",
            topic="licensing",
        ),
        *official,
    ]


def source_by_key(key: str) -> SourceIdentity:
    for source in manifest():
        if source.source_key == key:
            return source
    raise SourceError("Unknown configured source.")


async def fetch_source(source: SourceIdentity) -> bytes:
    if source != source_by_key(source.source_key):
        raise SourceError("Source does not match the configured manifest.")
    if source.url is None:
        return (SOURCE_DIR / "internal-guide.md").read_bytes()
    if os.environ.get("DISABLE_SOURCE_FETCH") == "1":
        raise SourceError("Official source requests are disabled.")
    try:
        async with (
            httpx.AsyncClient(timeout=20, follow_redirects=False) as client,
            client.stream("GET", source.url) as response,
        ):
            response.raise_for_status()
            media = (
                response.headers.get("content-type", "").split(";")[0].lower().strip()
            )
            if media != source.media_type:
                raise SourceError(
                    "The configured source returned an unexpected content type."
                )
            data = bytearray()
            async for part in response.aiter_bytes():
                if len(data) + len(part) > MAX_BYTES:
                    raise SourceError("The configured source exceeds the size limit.")
                data.extend(part)
            return bytes(data)
    except httpx.HTTPError:
        raise SourceError(
            "The configured official source could not be retrieved."
        ) from None


async def ingest(repo: KnowledgeRepository, source_key: str) -> OperationReceipt:
    source = source_by_key(source_key)
    raw = await fetch_source(source)
    parsed = extract_source(raw, source.media_type)
    req = DraftRequest(
        operation_id=uuid4(),
        text=parsed.text,
        scopes=[
            KnowledgeScope(
                provider_type="Dentist", jurisdiction="HI", topic=source.topic
            )
        ],
        review_issues=INTERNAL_ISSUES if source.url is None else [],
    )
    digest = hashlib.sha256(
        source_key.encode() + raw + req.model_dump_json().encode()
    ).hexdigest()
    return await repo.create_draft(
        0, req, raw, source.media_type, parsed, digest, source
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("ingest").add_argument(
        "source_id", choices=[s.source_key for s in manifest()]
    )
    commands.add_parser("activate-space")
    args = parser.parse_args()
    if args.command == "list":
        for source in manifest():
            print(source.source_key, source.title, sep="\t")
        return
    load_dotenv(override=False)
    async with create_pool(database_url()) as pool:
        repo = KnowledgeRepository(pool)
        if args.command == "ingest":
            result = await ingest(repo, args.source_id)
            print(f"Saved draft version {result.version_id}.")
        else:
            await reindex(repo, get_embedding_client())
            print("Embedding space active.")


if __name__ == "__main__":
    asyncio.run(main())
