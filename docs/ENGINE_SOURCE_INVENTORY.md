# Recovered engine inventory and M0 integration

## Provenance

Owner-supplied archive: `HarpyFrame_Codex_Engine_v1.3.10_FIXED_PRIVATE.zip`.
Archive SHA-256:
`de9a3e1df6ba2c4a8e792d765cfbc464a347e71afb9f5bb9676711921a6241c2`.
The v1.3.10 candidate is executable; v1.3.11 Scene Integrity is a roadmap only.

The original `integrations/read_only_bridge.py` has SHA-256
`7f0c8e18480c68cbb3fb16947ea313bd99fd376ecdaae452b93cbf72d8e4645e`.
Its read/projection behavior is adapted in
`src/girlframe/_vendor/harpyframe/read_only_bridge.py`. Changes: formatting and
typing, removal of standalone CLI/formatter, bounded binary read with UTF-8
decoding (4 MiB maximum), and explicit projection of validated turn/paused fields.
Its strict rejection of boolean turns and nonboolean pause values is preserved.
No game mechanics or rulebook text were copied into this bridge.

The bridge remains private project code with the original owner's rights intact;
no new third-party licensing grant is asserted. See the root source/rights notice
before any public distribution. Existing official GIRL FRAME rights are unchanged.

## Included in Git and installed distributions

- The reviewed minimal bridge, typed status model, filesystem adapter and service.
- Explicit optional `GIRLFRAME_ENGINE_SANDBOX` configuration and local CLI command.
- Synthetic tests, integration documentation and sanitized acceptance evidence.

This is sufficient to reproduce read-only integration from a fresh checkout using
the existing lockfile. No private package is required by CI or ordinary setup.

## Retained privately outside Git

- Original corrected ZIP and its complete extracted engine/template.
- Canonical campaign snapshot and ledgers, characters, private/GM notes, PDFs,
  source documents and generated disposable runtime.
- Original full verification logs and template hashes.

These assets are available in the current development workspace. They are not
installed by `tools/install.sh` or uploaded as CI artifacts. Future environments
need the private archive or retained workspace snapshot supplied separately. Do
not assume chat attachments automatically transfer to another session. Configure
the runtime path locally; no private workspace path is committed as a default.

## Private baseline verification

Executed at intake: package probe reported PRIVATE with 7/7 required paths; full
verifier ran 60 focused engine tests, 3 bridge tests and 3 package-layout tests,
all passing. Bootstrap created a separate runtime; its validation reported zero
errors and zero warnings. SHA-256 comparison confirmed all 120 original engine
files unchanged. These are separate results from the application's M0 test suite.

This does not certify complete official rules, every inherited test, scene
consistency or safe concurrent writes. The M0 integration neither invokes nor
repairs the legacy finalizer. It does not migrate any campaign into SQLite.
