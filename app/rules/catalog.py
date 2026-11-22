"""Pure catalog name comparison and reviewed-checklist fingerprints."""

import hashlib
import json
from collections.abc import Sequence


def normalize_name(value: str) -> str:
    return value.strip(" ").lower()


def template_fingerprint(
    type_id: int, template_id: int, version: int, names: Sequence[str]
) -> str:
    content = [type_id, template_id, version, sorted(normalize_name(n) for n in names)]
    return hashlib.sha256(
        json.dumps(content, separators=(",", ":")).encode()
    ).hexdigest()
