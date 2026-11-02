# M0 architecture decisions

## Scope and source inventory

The owner's instruction authorizes the foundation only. The retained v0.2 handoff
is the planning contract; its previous v0.1 spec is historical. References to
`planning/` are mapped to `GIRLFRAME_Discord_Codex_Handoff_v0.2/` without renaming
or duplicating the hash-verified package. Root instructions make this mapping
explicit. The official PDFs are private external references, not package assets.
The candidate engine and the other chat's bootstrap/verification scripts were not
supplied. Do not infer recovered engine behavior from handoff documents.

## Toolchain

Python 3.12.14, uv 0.12.23, Hatchling packaging, pytest, Ruff for lint/format, and
strict mypy for application source. `uv.lock` records exact resolved versions and
artifact hashes. Direct dependencies are pinned after resolution and validation.
CI and local checks share commands. Only Python 3.12 is claimed supported in M0;
the work order's broader 3.12+ target is narrowed to this tested baseline.

## Dependency and authority boundaries

The pure domain has immutable, strictly validated numeric Discord IDs plus a
campaign/interaction context. An ID is not authentication or authorization.
Adapters must derive identities from authenticated interactions; future services
must resolve roles/membership server-side. No role claims are accepted in the
principal. M0 has no campaign mutations, dice, RNG, or rules registry.

The private response protocol exercises the service/adapter seam with an in-memory
fake. It does not verify ephemeral delivery, disabled mentions, Discord signatures,
interaction acknowledgement, or API retries. The future real adapter must enforce
these contracts. No Discord or AI SDK is imported by the domain.

## Persistence

SQLAlchemy 2 synchronous SQLite with WAL, foreign keys and a busy timeout is the
pilot baseline. Each health operation disposes its engine. No import opens a DB.
No auto-migration or `create_all` at runtime. Alembic metadata and revisions remain
empty until M1. Temporary test tables are synthetic and never application models.
The empty version table is migration infrastructure, not game persistence.

Relative DB paths resolve from the working directory, documented as repository
root. Environment configuration is explicit, with one non-secret variable and no
automatic `.env` loading. Error output deliberately omits raw URLs/exceptions.
PostgreSQL, async DB drivers and multiwriter deployments are unsupported in M0.

## Platform contract

`discord.py` is installed/pinned, but no gateway is constructed. The command pattern
remains native slash interactions; no privileged message-content intent. Real API
behavior is deferred to M1. Official library/platform documentation consulted for
version compatibility and any access limitations are recorded in the acceptance
report. No model SDK/key is needed in M0. AI proposal and roll schemas remain illustrative, not enforcement
implementations; application domain validation is required later.

## Verification boundaries

Executable tests block network connections and cover both positive and negative
foundation paths. Ruff excludes the untouched historical handoff; mypy checks new
application source. Historical schema/fixture checks remain a separate command.
An additive checker scans all publishable files and verifies original manifest
hashes. It corrects the previously observed MFA-pattern coverage gap without
rewriting the historical validator. No comprehensive security certification,
coverage percentage, application migration, live bot, rules or AI claim is made.

## Deferred decisions

M1 requires owner acceptance of M0, private deployment/guild configuration, secure
bot credentials for live checks, and backup/retention choices before real data.
Public code licensing remains undecided. Engine recovery/reconstruction does not
block M0. Rules audits, GM/Handler context filters and scene integrity remain
future milestones, not hidden work inside this scaffold.
