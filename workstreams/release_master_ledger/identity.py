"""Canonical identity serialization for release-ledger records."""

import hashlib
import json

from .models import CanonicalIdentityFields


def canonical_json(value: object) -> str:
    """Serialize a JSON-compatible value with deterministic object-key order."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_text(value: str) -> str:
    """Return the uppercase SHA-256 digest of UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def build_identity(fields: CanonicalIdentityFields) -> tuple[str, str]:
    """Return the canonical serialized fields and their identity digest."""
    canonical = canonical_json(fields.to_dict())
    return canonical, sha256_text(canonical)
