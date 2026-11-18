# Character file bridge

See [INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md) for the adapter map and
instructions for an existing Discord application or the Campaign UI task.

The Campaign UI can generate `harpyengine.character-draft` JSON and offer it as
a download. A Discord adapter uploads that file to the engine's private preview
and confirmation workflow. This package does not establish an HTTP connection or
grant authority to a file. JSON is the first supported import format; PDF/OCR,
live-state migration and external-actor sheets are separate extensions.

```js
import { createDraft, serializeDraft } from "./harpyengine-sheets.mjs";
const document = createDraft({
  callsign: "SYNTHETIC_DEMO", girl_playbook: "MOCKINGBIRD", frame_playbook: "JANUS"
}, { girl_appearance: "Player-authored appearance" });
const file = new Blob([serializeDraft(document)], { type: "application/json" });
// Download `file`; import it using the Discord application's character importer.
```

Use `creation-catalog-v1.json` for the dropdown labels, ordinary Asset options,
NPC roles and special starting-choice sections. Campaign rulings/defaults must come from the
engine; the catalog grants no starting Heat, Permissions, Status or accepted
relationships. Incomplete drafts are valid exchange documents and remain drafts.
Girl/Frame static legality, live ownership and coordination are engine-validated.

`character-draft-v1.schema.json` is the structural JSON Schema. The dependency-free
browser codec checks the envelope, excluded keys, finite numbers and size; it is
not a duplicate rules engine or the authoritative parser. Use the schema for
frontend field feedback and engine preview before saving. Browser `JSON.parse`
uses its usual duplicate-key behavior; the engine rejects duplicate keys in the
actual uploaded bytes. Upload the original file for engine validation.

Portable fields are only owner-authored starting choices. Do not add owner,
campaign, revisions, source tokens, starting-Bond IDs, accepted coordination,
prior-mission consent, Heat, damage, Permissions, Status or activation flags.
`profile.notes` omitted or null preserves existing private notes; an explicit
empty string requests clearing them. Pair Asset descriptions still need their
real accepted live Pair context; a file cannot supply it. The engine importer
must rebind all actual context and reject stale changes atomically.

`harpyengine.character-sheet` is a **read-only display snapshot**, with a declared
owner/public audience. It is not accepted as a creation import or restoration
command. The engine must produce the correct projection before serialization,
including when an owner requests a public export. Use string IDs internally and
current authorized Discord nicknames for display. The printable Python renderer
escapes all data, renders known sections and never substitutes IDs for names.

Python APIs live in `girlframe.engine.character_documents` and
`girlframe.serialization.character_sheet_html`. `parse_draft` enforces UTF-8,
256 KiB maximum, no duplicate keys/non-finite numbers, strict schema and static
creation legality. Its safe error does not echo uploaded private text.
`CharacterDraftDocument.to_creation(**trusted_source_fields)` is server-only
rebinding; callers must still use the engine service's preview/atomic confirmation.

Regenerate schemas, catalog and synthetic example from the repository root:

```sh
.venv/bin/python integrations/character_sheets/generate_contracts.py
```

The synthetic example demonstrates structure. It does not satisfy live Bonds,
Handler confirmation, campaign rulings, rules-release gates or activation consent.
Open `example-printable-sheet.html` for the scriptless printable layout; its paired
`example-read-only-sheet.json` demonstrates a display snapshot, not an import.
