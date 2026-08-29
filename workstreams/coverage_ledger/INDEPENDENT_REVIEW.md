# Independent Review Scope — Public Copy

This public copy is intentionally limited to reviewable, portable code and synthetic tests. Its configuration boundary requires the canonical local configuration at `local/local_configuration.json` before any local configured ledger scan, artifact generation, or card rendering can occur. Generated outputs are rejected unless they remain inside the ignored `local/` directory.

The reviewable public behavior is fail-closed: incomplete contracts cannot become ready merely because they share a root annotation, and terminal protected outcomes remain outside card selection. Those assertions are tested with synthetic identities only.

Local audit details, evidence references, generated outputs, source identifiers, paths, counts, and historical review findings are excluded because they depend on ignored machine-local inputs. This document does not certify coverage, a PAK, a mesh correction, source completeness, or gameplay.
