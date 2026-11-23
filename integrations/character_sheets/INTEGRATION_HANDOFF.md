# Campaign UI / Discord character-sheet integration

This is the handoff for the separate **Update GIRLFRAME Campaign UI** task.
That chat was not accessible here. The implemented connection is versioned JSON
file exchange; no HTTP server, OAuth connection or browser database access is
implicitly installed by this package.

## Delivered adapters

| Adapter | Implementation / interface | Authority boundary |
|---|---|---|
| Browser document codec | `harpyengine-sheets.mjs`, `.d.ts`: `createDraft`, `parseDraftJSON`, `serializeDraft` | Structural frontend feedback only; upload original bytes for authoritative validation |
| Creation catalog | `creation-catalog-v1.json`, generated from engine catalogs | Dropdowns, starting sections and labels; no granted campaign resources or player decisions |
| Document/schema codec | `engine.character_documents`: `parse_draft`, `encode_document`, two typed document models | UTF-8 JSON, <=256 KiB, explicit format/version, duplicate/nonfinite/unknown authority fields rejected |
| Interaction identity | Existing `viewer_from_interaction` → `GuildViewer`; `resolve_member_names` | Principal comes from verified Discord membership, not uploaded owner IDs; display current nicknames |
| Campaign/ownership binding | `CharacterTransferService.authorize` plus existing store policy | Existing campaign membership and binding; every retry rechecks membership; Handler role is not blanket private-sheet access |
| Import preview/application | `CharacterTransferService.preview` / `apply` | Owner/campaign/revisions/context/digest bound; explicit confirm; one existing engine transaction |
| Persistence bridge | Narrow connection helpers in existing profile/creation services | Preserve ordinary save events, snapshots, sync and idempotency; roll back both draft parts together |
| Live coordination/review | Existing Bond/Pair/shared/coordination services and `/character review` | File cannot accept a Bond, choose another person's Assets/standards, grant a test bypass or activate |
| Sheet projection | `CharacterTransferService.snapshot` | Force public projection even for owner-requested public exports; owner-only starting context/private notes |
| Print renderer | `serialization.character_sheet_html.render_sheet` | Escaped, scriptless HTML; explicit inactive draft label; known sections, no raw engine-history dump |
| Native file transport | `discord_adapter.character_transfer.register_character_transfer` | Private attachment preview and downloads; stable import key; no public auto-posting |

All engine imports below use the Python namespace `girlframe`.

## Wire contract

`harpyengine.character-draft`, schema_version1, contains:

- `profile`: callsign, Girl, Frame, optional personal notes.
- `creation`: the explicitly listed player-owned fields in the generated schema.

Omitted/null notes preserve existing notes; an empty string explicitly clears
them. Imported creation choices replace the editable fields shown in the preview.
Use the printed Frame name in the profile and catalog. The importer can
reopen older JANUS drafts under the printed name.

Never add account/campaign ownership, revisions, source fingerprints/tokens,
starting-Bond IDs, accepted agreements, permissions, Heat, Status, damage or
activation to an import. Those fields are rejected. Names/descriptions are data,
never instructions or code. Incomplete creation documents are allowed as drafts.

Pair Asset descriptions require the actual live accepted Pair selection. A
profile-changing import can stale those agreements, so import the base profile,
finish Pair setup, then import those descriptions against the unchanged profile.
The engine reports this requirement rather than inventing consent or dropping
the description text. Prior-mission discussion and other people's choices stay
in the live workflows.

`harpyengine.character-sheet` is a **read-only display snapshot**. Draft snapshots
contain planned traits/starting context and unmet requirements, without granted
Heat/Permissions. Active snapshots contain ordinary native Pilot resources,
current native peer/Handler Bond depths and clearly labelled starting references.
This is not a complete campaign backup or all specialized M3 work panels.
External actors/Harpy/copy sheets need their actual source-aware role adapter;
a controller's Pilot sheet is never a substitute.

IDs are strings in wire metadata. Resolve visible names through authorized
Discord member lookup. A snapshot's `revision` is display metadata, not an edit
token; import preview supplies the actual profile/creation/context versions.
Public snapshots contain only the existing explicit public projection. Personal
notes require both owner audience and an explicit include-private request.

## Campaign UI implementation

1. Load the generated catalog and JSON Schema.
2. Render Girl/Frame dropdowns and their sourced sections. Generate static
   starting structure; the human selects Assets/desires and writes descriptions.
3. Keep the UI's working draft local until the player chooses a save/export action.
4. Use `createDraft(profile, choices)` then offer `serializeDraft(document)` as
   a UTF-8 `.json` download.
5. The player uploads that file with `/character import`, reviews changes, and
   confirms. Follow existing requests/review/activation for remaining requirements.
6. Use `/character export format:sheet` or `format:html` for a display snapshot.
   Browser Print → Save as PDF produces a printable PDF from the HTML.

The browser codec does not certify printed-rule completeness. It intentionally
does not recreate the rules engine. Browser JSON.parse has normal duplicate-key
behavior; authoritative engine validation must receive the original uploaded
file, not a silently normalized rewrite of a problematic input file.

## Engine / another Discord application

Initialize an existing engine store using its actual policy/database. A user must
explicitly join the campaign before import. Do not infer engine membership merely
from an uploaded file or automatically join somebody during preview.

```python
from girlframe.services.character_transfer import CharacterTransferService

transfer = CharacterTransferService(store)
transfer.authorize(verified_viewer)
preview = transfer.preview(verified_viewer, uploaded_bytes)
# Present preview.changes / preview.warnings privately; await actual confirmation.
result = transfer.apply(verified_viewer, stable_command_key, preview)
```

The preview is a server-held immutable object; do not trust a client-posted plan
as authorization. Re-preview changed documents or stale revisions. Retry a known
confirmation with the same key; do not make a new key after an uncertain result.
No apply call activates the character. Active-sheet replacement is rejected.

For the bundled discord.py controls, provide a guild-scoped `character` group
(create it first if your app has none), then:

```python
from girlframe.discord_adapter.character_transfer import register_character_transfer

register_character_transfer(tree, guild_id, transfer)
# Synchronize using your application's normal guild-command startup path.
```

The principal must be built from verified Discord guild membership/roles by your
server. Keep the Bot Token on the server. Add your explicit campaign-join path;
HarpyEngine already supplies one through `/start` and existing onboarding.
Private file delivery needs the application's appropriate Discord permissions.

One authoritative engine must own the campaign. A UI/second bot on another host
uses file exchange through that engine, or a separately implemented authenticated
API. Do not fork live campaign state or share SQLite over an untrusted network.

## Optional adapters — defined, not implemented here

- **Direct HTTP transport:** map read catalog/template/snapshot, preview import
  and confirm import to the same services. Preserve idempotency, expected versions,
  explicit audience and no authority from files. Do not expose private helper SQL.
- **Web identity/session:** Discord OAuth authorization-code login with state/PKCE
  as appropriate, server-managed sessions, CSRF protection and current guild/role
  verification. A browser supplies no `is_administrator`/owner claims.
- **Durable web preview store:** server-side owner/campaign/digest/context-bound
  plans, expiration and retry outcomes. Do not turn arbitrary client JSON into
  `ImportPreview` authority.
- **PDF/fillable-sheet/OCR input:** extract into an untrusted creation candidate,
  show extraction/mapping errors, then use exactly the same engine preview path.
  No direct live-state import, automatic consent or silent truncation.
- **Active-character migration:** separately authorized audited game operations
  for resources/history. Current-sheet JSON is never a restore command.

The package contains sanitized source, a wheel, schemas, browser helpers and
synthetic examples. Credentials, personal settings, real campaign databases,
private engine archives, official PDFs and genuine approval records are excluded.
Rule coverage remains RULES_SUBSET; file compatibility is not rules certification.

Use Python3.12 and `bash install-engine.sh` in the extracted package for a local
environment with the included lockfile. The installer downloads pinned uv and
runtime dependencies; it creates no database and starts no bot. The bundled
wheel is also available for applications that manage their own Python environment.
