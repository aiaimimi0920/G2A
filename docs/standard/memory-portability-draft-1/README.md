# Companion memory portability: candidate contract

Status: **draft candidate, not a released wire profile**. This bounded technical proposal originated under review r34 §§9.7 and 18. The current r71 review entry is [§15.7, Player-initiated companion-memory portability](../G2A_SPECIFICATION.md#157-player-initiated-companion-memory-portability); this directory remains supporting material and does not supersede r71. It adds no core operation and changes no SDK behavior. EN and Chinese files carry the same requirements. Cross-provider identity mapping, transport authentication and permission-policy registries remain candidates requiring review; JSON validation cannot grant authority.

## 1. Scope and artifacts

`schema.json` is JSON Schema 2020-12 for three documents: Export, Selection and Receipt. `build_schema.py` reproducibly generates it. `vectors.json` contains public positive/negative cases; `check_vectors.py` is a design oracle, not a provider. `build_vectors.py` reproduces fixtures. These are not proof of independent provider interoperability or full G2A conformance.

An export contains **all currently retained companion memory**, including conversation, scene, summary and preference records, not merely a provider summary. `retained_record_count` counts included AND explicitly restricted/unavailable record entries at one consistent `snapshot_id`. Each entry has an opaque `record_id` and revision. A provider MUST reconcile this inventory against its actual retained data, including game/run stores and indexes; the oracle detects count inconsistencies, but cannot prove an exporter did not lie about its source inventory. Already-deleted originals need not be reconstructed or restored.

## 2. Record and media model

An `included` record MUST include content and metadata: kind, original timestamps, game/run/save context (null means not applicable/unknown, not permission), provenance, player-edit indication, derivation and associations, hard access/retention constraints, and the separate soft confidentiality style. Identifiers are provider-scoped; their strings MUST NOT be assumed globally identical across providers. `source_provider` plus `subject_id` identifies the source namespace, while `companion_id` is preserved source identity, not a destination login credential.

Hard constraints and extensions MUST be preserved. An importer unable to interpret a hard constraint MUST report unresolved/rejected rather than silently widening access. Soft confidentiality style MUST NOT be reinterpreted as a hard export prohibition. A player-authorized export may carry private-style memories without authorizing their disclosure to a game. Constraints in this candidate are descriptive strings, **not an executable policy language**; a frozen profile still needs registered interoperable policy semantics. Unknown extension data must be retained or truthfully reported as unsupported/transformed.

Restricted/unavailable records MUST appear as explicit stubs with reason and explanation. If even source identifiers would disclose protected information, use scoped opaque inventory identifiers and sanitized reasons. Do not expose restricted content merely to explain a restriction. Completeness cannot be claimed as unrestricted success when such limitations exist.

Binary content uses `blob_ids`. Every referenced blob MUST have exactly one descriptor. Included media has a relative `blobs/<opaque-name>` path, byte length, and SHA-256 of **the exact uncompressed file bytes**. External URLs are not content, are not automatically fetched, and do not establish export completeness. Missing/restricted media MUST have an explicit limitation descriptor. Text-only partial import of a record missing audio is `transformed`, not `imported`. Original media type and source context MUST remain identifiable.

An archive importer MUST reject traversal/absolute paths, duplicate archive entries, symlink escapes, excessive expanded size and unsupported encodings before extraction. It MUST NOT execute content. Limits MUST be disclosed, not implemented by silent truncation. This candidate does not define chunked/resumable archive transfer; such transfer MUST reconstruct and verify the same complete export and blob bytes before declaring success. No per-chunk arrival implies usable memory.

## 3. Selection, authorization and integrity

The player initiates export/migration and explicitly selects destination and record IDs. Selection binds `export_sha256`, the SHA-256 of the **exact UTF-8 export JSON bytes transferred**, not a parse/re-serialization. BOM-free UTF-8, unique JSON member names and finite JSON numbers are required. A regenerated export has a new digest and requires a corresponding selection; no canonical JSON algorithm is assumed. Media hashes inside that export transitively bind media bytes. A digest proves integrity, not authenticity or consent.

Source and destination independently authenticate the player and verify the subject mapping and authorization. `selection_id` or any JSON claim MUST NOT substitute for that verification. A provider switch or session opening MUST NOT auto-import, and a requester MUST NOT select another player's inventory by guessing identifiers. This file format deliberately contains no tokens or credentials. Exact authentication/transport is outside this candidate; implementers MUST NOT expose an unauthenticated import endpoint based on this schema.

Selection IDs are unique within the destination's authenticated player namespace. A retry with the identical selection and digest returns the same accounting and MUST NOT duplicate imported memories. Reuse with different content/destination MUST be rejected. Immediately before applying changes, the importer MUST recheck authorization and relevant completed edits/deletions; stale exports MUST NOT silently restore deleted memory or overwrite player edits. A safe conflict is reported unresolved, not silently resolved by newest timestamp. This draft does not invent a global deletion registry.

## 4. Honest receipt

A Receipt binds selection, exact export digest, destination provider and subject. Exactly one outcome MUST exist for each selected record; no unselected record is imported. Status is `imported`, `transformed`, `rejected` or `unresolved`. Successful entries identify destination record IDs; transformed entries explain the transformation and retained/lost semantics. Rejected/unresolved entries have no successful destination IDs. Unsupported content/constraints require explicit accounting. `imported` means usable memory with required metadata preserved, not mere upload receipt. Partial results MUST not be presented as total success.

Import cannot expand disclosure rights, reconstruct removed originals, transfer model weights or guarantee identical personality/recall. Actual provider tests must inspect stored/retrievable memory, player edits/deletions, index behavior and permission preservation; these are not provable from a receipt alone.

## 5. Run and evidence boundary

From this directory, with repository dependency `jsonschema` installed:

```text
python build_schema.py
python build_vectors.py
python check_vectors.py
```

Fixture encoding in the runner is compact JSON only to generate deterministic test bytes; it is NOT a universal canonicalization rule. Vector `accept` is the expected structural/relational result, not evidence of user consent. Authentication, source inventory truth, safe archive extraction, deletion enforcement and live retrieval are explicitly separate provider conformance tests still required before a release claim.

Candidate timestamp syntax is an ISO calendar date and time with explicit Z or numeric offset; leap-second 60 is not represented by this candidate. The runner checks calendar validity directly because optional JSON Schema format libraries are not guaranteed installed.

