# Two starting Bonds and versioned presence

Owner-authorized change: configurable two-Bond campaign house rule and explicit
per-character setup test exemption; bump the next runtime release to0.1.1.

The original primary Bond retains its printed depth and Mentor/Pair ownership.
The second is accepted Personal with a different character. Existing proposals,
private review confirmation, revision checks and activation project actual
agreements; no consent is inferred. Ordinary playbooks may have two outgoing
proposals under this policy. Newgirl/Bonded retain one outgoing Mentor/Pair and
receive the extra Personal proposal from another Girl.

`/campaign bond_test member:<player> enabled:true|false` requires actual
Handler/configured administrator authority and explicit confirmation. The grant
is stored in existing append-only setup revisions, bound to the current profile
revision, visible in the private review, and copied into canonical activation
review. It waives starting Bonds only. Revocation stales prior reviews; activated
characters cannot be reset or granted a new setup exemption. No schema migration.

Discord presence already reads __version__. Package metadata now reads that same
source dynamically; runtime releases must bump it, docs-only commits need not.
Version0.1.1will be visible in Running/Restarting lifecycle states after restart.
All pinned dependencies are unchanged; uv's dynamic local-package lock entry
omits the static version. Initial offline lock refresh failed because the pinned
build backend was not cached; normal locked resolution succeeded.

Local focused verification: first run2failed/6passed (an existing one-outgoing
proposal limit and a test's static-lock assumption); both failing nodes passed
after correction. The two-Bond native flow exercises actual acceptance, explicit
selection, saved review, activation/retry, both edges and withdrawal freshness.
The bypass flow covers private confirmation, unauthorized access, no fabricated
agreements, revocation, stale activation rejection and actual zero-Bond test
activation. Existing lifecycle presence checks pass. Changed-file Ruff/format and
source types pass. CI includes these checks, existing focused pre-live tests and
one-Bond consent/privacy/retry behavior. No full regression or human acceptance
is claimed. Exact source/CI and live evidence follow at release.

Owner check after deployment: propose/accept two Bonds, select both in
`/character review`, save review, then activate. For a setup-only test, confirm
`/campaign bond_test`, reopen/save review and confirm activation separately.


Exact runtime source: `7aefb3de3674fe80cf7b3c951985b3733477b51c`.
[Focused CI43694295895](https://github.com/heyitskat777-netizen/HarpyEngine/actions/runs/43694295895)
passed66tests/0failures/errors/skips in93.686s; changed-source typing/lint/format,
CLI, runtime/planning and repository checks passed. This includes the final
protected Mentor/Pair proposal limit and dashboard routing for the accepted
second Bond. Artifacts retain exact source/base/scope and JUnit. No full run.

Authorized deployment completed: authentication checked before stopping the old
process; fresh0600consistent backup retained; frozen source starts with the
existing policy plus only owner_starting_bond_count=2. One running process,
Running v0.1.1presence,19guild commands and native campaign bond_test registration
are verified. The existing global launch command is preserved. Schema remains
0020; backup is intact. No grants, reviews, Bonds or character activations were
fabricated in the real campaign. Human outcomes remain pending.
