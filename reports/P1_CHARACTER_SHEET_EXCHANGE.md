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
