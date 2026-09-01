"""Public contracts for the evidence-bound release master ledger."""

from .identity import build_identity, canonical_json, sha256_text
from .models import CanonicalIdentityFields, LedgerRecord, Observation
from .configuration import (
    ConfigurationError,
    EvidenceInput,
    EvidenceIntegrityError,
    LocalConfiguration,
    VerifiedInput,
    load_local_configuration,
    validate_output_path,
    verify_evidence_inputs,
)
from .validation import validate_generated_ledger, validate_record
from .adapters import (
    adapt_bcbscantily,
    adapt_coverage,
    adapt_hash_manifest,
    adapt_named_target,
    adapt_one_protected,
    adapt_package_evidence,
    adapt_permission_manifest,
    adapt_protected_manifest,
    adapt_protected_registry,
    adapt_true_underwear,
    adapt_vanitybody,
    read_observations,
)
from .reconcile import ReconciliationResult, reconcile_observations
from .audit import InventorySets, build_completeness_audit
from .inventory import (
    BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
    IndependentInventories,
    InventoryIntegrityError,
    ProtectedManifestRelation,
    extract_independent_inventories,
)
from .exclusions import (
    ExclusionSelection,
    canonical_exclusion_payload,
    exclusion_event_id,
    select_current_exclusion,
    validate_exclusion_event,
)

__all__ = [
    "CanonicalIdentityFields",
    "ConfigurationError",
    "EvidenceInput",
    "EvidenceIntegrityError",
    "LedgerRecord",
    "LocalConfiguration",
    "Observation",
    "VerifiedInput",
    "BASE_GAME_SOURCE_PROFILE_UNRESOLVED",
    "IndependentInventories",
    "InventoryIntegrityError",
    "ProtectedManifestRelation",
    "build_identity",
    "canonical_json",
    "load_local_configuration",
    "sha256_text",
    "validate_output_path",
    "validate_generated_ledger",
    "validate_record",
    "verify_evidence_inputs",
    "adapt_bcbscantily",
    "adapt_coverage",
    "adapt_hash_manifest",
    "adapt_named_target",
    "adapt_one_protected",
    "adapt_package_evidence",
    "adapt_permission_manifest",
    "adapt_protected_manifest",
    "adapt_protected_registry",
    "adapt_true_underwear",
    "adapt_vanitybody",
    "read_observations",
    "InventorySets",
    "ReconciliationResult",
    "build_completeness_audit",
    "reconcile_observations",
    "extract_independent_inventories",
    "ExclusionSelection",
    "canonical_exclusion_payload",
    "exclusion_event_id",
    "select_current_exclusion",
    "validate_exclusion_event",
]
