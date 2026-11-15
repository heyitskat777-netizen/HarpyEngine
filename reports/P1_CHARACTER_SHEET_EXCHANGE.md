# P1 character-sheet exchange — bounded release

Owner request: provide an import/generator package for another Discord application
or the separate Campaign UI task. That chat is not accessible here. The delivered
connection is versioned JSON file exchange, not an HTTP/OAuth integration.

## Delivered behavior

- Browser codec, TypeScript declarations, generated JSON Schemas and creation
  catalog, synthetic JSON/HTML examples and an explicit adapter handoff.
- `/character import` privately previews an uploaded creation document and saves
  profile plus creation choices in one existing engine transaction after explicit
  owner confirmation. Metadata-only audit, normal profile snapshots/cosmetic sync,
  current membership, revision/context checks and stable retry keys are preserved.
- `/character export` downloads an importable owner template or filtered owner/
  public read-only snapshot and scriptless printable HTML. Personal notes require
  an explicit owner request; public projection is forced even for the owner.
- Draft labels and unmet requirements are explicit. Actual native current Bond
  depths stay distinct from clearly labelled starting NPC/playbook context.
- No file grants accepted Bonds, someone else's choices, live resources, exemption
  or activation. Activated sheets cannot be replaced by draft import.
- Small existing save-body extractions support atomicity; no schema migration.

## Verification before source freeze

Synthetic only; no real player action or consent was generated.

- Changed Python: Ruff check/format (16 files), mypy (10 source files): pass.
- New codec/service/native adapter modules: **10 passed in 1.66s**;
  `var/character-transfer-integrated.xml`. Earlier 10-case smoke passed in1.94s.
- Affected original profile and creation save/restart/retry paths: **2 passed in
  1.23s**; `var/character-transfer-existing-consumers.xml`.
- Coverage includes strict authority/format rejection, omitted-note preservation,
  private/public output, escaping, atomic rollback after staging, same-key retry,
  stale/foreign/revoked access, active-sheet rejection and private native controls.
- Browser-to-Python codec smoke: pass. Generated contracts regenerated; installer
  shell syntax, CLI help and planning contracts checked separately.
- Offline current-policy registration:19guild groups,16character subcommands,
  import/export present; no login or command sync. Policy unchanged, existing
  frozen live v0.1.3 process remains present.
- Repository check:2,055publishable files,40original manifest entries,0findings.
  Registry remains RULES_SUBSET (479entries); no rules certification changed.
- Focused CI selection adds these10checks and the2existing save checks to the
  prior73-case packet. Exact source/CI/package results will be appended after build.

## Packaging and remaining boundaries

`tools/build_character_sheet_package.py` packages only an explicit committed-source
allowlist into a source-pinned wheel/ZIP. Sorted manifests record file hashes;
optional CI evidence must match the exact source commit and be successful.
Install script uses Python3.12, pinned uv0.12.23 and the included runtime lockfile;
network access is needed for bootstrap/dependencies. It starts no database or bot.

No private PDFs/engine archives, real database, credentials, campaign settings or
approval records are packaged. No direct HTTP/OAuth server, PDF/OCR import,
active-state migration or source-aware external-actor sheets are claimed.
The wheel is an engine library; it does not provision a Discord application.

This is focused patch evidence, **not a new full regression**. The3,328-case
5412ee8 full regression remains historical baseline evidence. Human file upload,
review and cross-application UI integration remain untested. The running v0.1.3
bot is preserved; new commands are packaged source, not live command registration.

## Final exact source and package

Source: `fe47d7ef0b558a1106f5dc48b25c277aff5f875b`, package **v0.1.4**.
[Focused CI43710860896](https://github.com/heyitskat777-netizen/HarpyEngine/actions/runs/43710860896)
passes **85tests, zero failures/errors/skips**,105.704s. Changed-source static,
CLI, registry, planning and sanitized-repository checks pass. Full-suite mode was
not run. The12new/affected checks and prior73-case packet were retained.

Artifact: `var/releases/character-sheets-v0.1.4/HarpyEngine_Character_Sheets_v0.1.4.zip`
(6,920,854bytes,986entries). SHA256:
`e6ee723b54ba9179909907bb746055209fdf108cd6fc61d357b03ea06574b96a`. Sidecar checksum, successful exact-source CI metadata and per-file
manifest hashes are included/retained. Build command:

```sh
.venv/bin/python tools/build_character_sheet_package.py \
  --source-ref fe47d7ef0b558a1106f5dc48b25c277aff5f875b \
  --output-dir var/releases/character-sheets-v0.1.4 \
  --ci-evidence var/character-sheets/ci-evidence.json
```

Fresh ZIP extraction: the supplied locked installer exited0; its Python3.12
environment parsed the synthetic example. Installing the bundled wheel into that
disposable environment then importing from actual site-packages verified v0.1.4,
document parsing and identical printable output. No database or bot was created.
ZIP CRC and every manifest file hash passed after build and again for delivery.
Browser/Python round trip and both generated Schema/example pairs validate.

Sanitized source is published on `codex/r285-integration-20261114`; no main merge,
live restart, command sync, campaign change or environment publication occurred.
The source-pinned live v0.1.3 process remains separate. To integrate the other
application, upload this ZIP to that task and read its root INTEGRATION_HANDOFF.md.
Human import/confirmation and the separate UI's actual integration remain pending.

## Owner-authorized live rollout

After package delivery, the owner approved the recommended v0.1.4 rollout with
“proceed.” Runtime now uses exact frozen source
`fe47d7ef0b558a1106f5dc48b25c277aff5f875b`. Its85-case focused CI evidence above was reused;
no source change or new full regression was needed.

Authentication/application/guild preflight and offline policy validation passed
before stopping the old process. A fresh0600backup passed integrity/foreign-key
checks and matched all45tables' rows after the previous
process stopped. Schema0020and the private policy remain unchanged.

Gateway readiness and Running v0.1.4presence are verified. There is one pinned
process; all946frozen source/rules/migration files match the tested Git source.
Discord REST readback verifies19guild groups,16character subcommands including
import(document attachment) and export(template/sheet/html;owner/public;notes/member).
The existing global launch command is byte-for-byte unchanged in readback.
Backup hashes remain intact; operational authority is the private
`var/discord-dev/p1-deployment.json`. No migration, fabricated player action,
AI call, main merge or environment publication occurred.

Human checks remain pending: export a sheet privately, then perform the
UI→JSON→preview→confirmation→reopen flow with an inactive test draft. Active-sheet
imports must remain blocked. See docs/P1_PLAYER_TEST_PLAN.md for live checks.
