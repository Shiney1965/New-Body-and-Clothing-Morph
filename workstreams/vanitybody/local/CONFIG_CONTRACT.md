# Local integration contract

Portable tests and public modules use only the synthetic NumPy fixtures and
declared public anchor metadata. They neither discover nor read `evidence/`,
`staging/`, generated ledgers, or external asset trees.

To run an integration-only check, create only the ignored canonical
`local/config.json`; alternate or external configuration paths are rejected
before their contents are read. It has these string fields: `anchor_evidence`,
`route_evidence`, `glb_manifest`, and `ledger_input`. Each names an existing
local file. `output_dir`, when present, must be exactly `generated`; all
generated output is constrained to
`local/generated/`. Do not commit the configuration, generated output, source
extracts, screenshots, GLBs, GR2s, PAKs, hashes, or workstation paths.

Integration results are local diagnostic evidence only. They do not establish
a corrected mesh, a package, route validity, coverage, protected-control
acceptance, or gameplay acceptance.
