# Character sheet exchange — implementation contract

Owner authorization: develop the character generator/import integration and
provide a package another Discord application/Campaign UI can use. The separate
Campaign UI chat is not accessible from this session. Implement a file bridge
first; do not invent an already-deployed HTTP/OAuth connection to that UI.

Normal flow: UI generates versioned creation JSON → Discord attachment → private
owner-bound preview → explicit confirmation → atomic saved profile/creation draft
through existing engine operations → existing coordination/review/activation.
Export an importable owner template or a filtered read-only current sheet, plus
printable HTML. No accepted Bonds, permissions, Heat, Status, trusted provenance,
activation, campaign IDs or historical canon may be imported from a file.

Boundaries: keep the frozen live v0.1.3 bot up during development. No private
engine writes, environment publication, model calls, Ancillary, main merge or
external messages. Source/package publication remains authorized. No automatic
activation or consent; active sheets cannot be replaced by draft import.

Ownership/API freeze:

- Format worker: pure portable models/parser/encoder, schema/catalog generator,
  escaped printable rendering, dependency-free browser codec and compact format
  tests. `engine/character_documents.py`, `serialization/character_sheet_html.py`,
  `integrations/character_sheets/`, and its new test module only.
- Discord worker: `discord_adapter/character_transfer.py`, narrow bot registration
  and command help hook, and its new native test module only. No service/model
  edits or pytest/Git. Private files and previews; no public auto-posting.
- Root: `services/character_transfer.py`, small transaction helpers extracted
  from existing profile/creation save operations, all other shared integration,
  tests/static/CI, adapter handoff, package builder and sanitized publication.

Service contract: `CharacterTransferService(store).preview(viewer, raw: bytes)`
returns frozen `ImportPreview` with `.document`, `.digest`, `.profile_revision`,
`.creation_revision`, `.changes`, `.warnings`. `apply(viewer, key, preview)`
revalidates owner/campaign/context/revisions and atomically saves both draft
parts or rolls everything back, returning safe revision/status metadata.
`template(viewer, include_private=False)` returns `CharacterDraftDocument`;
`snapshot(viewer, audience='owner', owner=None, include_private=False)` returns
`CharacterSheetDocument`. Both encode through the portable codec. Public snapshots
must force public projection even when the exporter owns the character.

Portable models: format `harpyengine.character-draft`, schema_version1, profile
(callsign/Girl/Frame, optional notes; omitted notes preserve existing private
notes), creation (only player-owned starting descriptions/choices). Exclude
server tokens, IDs/provenance/accepted coordination and actual gameplay state.
Snapshot format `harpyengine.character-sheet` is read-only and never importable
as a creation document. IDs in the wire format are strings; visible member names
resolve through current Discord nicknames. Native Pilot sheets are the first
bound; actual external actors need their own source-aware adapter, not a
controller's Pilot resources.

Completion evidence: native preview/confirmation/reopen, JSON round trip, strict
format rejection, no public/private leak, stale/unauthorized rejection, atomic
rollback and idempotent retry, no implicit activation/consent. Focused functional
checks only, with retained failures; final exact source CI and a reproducible
ZIP/wheel/handoff containing only sanitized code, schemas and synthetic examples.
List optional direct HTTP/OAuth and PDF/OCR import adapters as future extensions,
not delivered capabilities. Do not restart prior completed gameplay systems.
