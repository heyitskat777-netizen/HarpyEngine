# M1 phase 1: authorized read-only Discord bot

M0 was accepted by the owner. The explicitly authorized next scope is a read-only
bot, not the entire original M1 ledger/dice work order. No M2 work is authorized.

## Boundaries

Gateway `discord.Client` plus `CommandTree` -> trusted interaction identity ->
read-only authorization service -> existing bounded sandbox projection -> private
interaction response. SDK objects stay in the adapter. Worker threads perform
filesystem reads after ephemeral deferral, keeping heartbeat/acknowledgement work
off the blocking path. There are no command options or arbitrary path selectors.

Only three commands are registered in one configured guild, with no global sync.
Startup checks that the authenticated application matches configuration, then
verifies guild access, then syncs guild commands once per process. Reconnects do
not resync commands or produce game operations. All replies are ephemeral with
mentions disabled, including failures. The SDK cooldown is three uses of each
command per guild/user per ten seconds; these read-only limits reset on restart.

## Authorization and policy persistence

The policy is trusted local JSON with a single guild/campaign/sandbox binding,
numeric allowed status-user IDs, explicit administrator access and explicit status
audience approval. It survives restart and is loaded once at startup. It is not
user-submitted JSON, role-name matching, an HTTP admin API or a player-owned path.

`/help` requires membership in the configured guild. `/campaign_status` additionally
requires explicit user membership or an explicitly enabled guild administrator,
and audience approval. `/health` requires explicitly enabled administrator access.
Health reports only handler responsiveness and sandbox readability, not campaign
fields. Authenticated guild/member identity and administrator permission come from
Discord's interaction payload via the SDK, never from command parameters. The
client requests the nonprivileged guilds intent only.

Reject DMs, wrong guilds and plain User objects without Member proof before
touching the source. This policy deliberately grants administrators read-only
facilitator access; it grants no character ownership or right to act for a player.
There is one binding per process; no cross-campaign lookup endpoint exists yet.
The configured `campaign_id` identifies the binding for future persistence work.

## Credentials and network

The owner-provided `DiscordBot` is delivered as a direct secure environment
variable, loaded separately into `SecretStr`, and used only at login. No values
are stored in JSON or printed. The public key is irrelevant to Gateway transport.
Inherited HTTPS proxy routing is passed to discord.py for REST and WebSocket
traffic; default TLS verification remains enabled. SDK debug logging is not
enabled. Error responses/bodies are never echoed; safe failure categories are
used for invalid credentials, missing guild, denied access and other failures.

Ctrl-C and SIGTERM close the SDK client. Live processes do not survive environment
restoration. `tools/run_discord_dev.sh` records the repeatable startup command;
`start --check` validates local policy/snapshot offline. Tokens remain external.

## Synthetic live development

`tools/setup_discord_dev.py` creates an ignored status-only fixture (turn zero,
paused) and local policy. It is not a full engine bootstrap and cannot run game
commands. It refuses to overwrite an existing destination. The test guild therefore
does not expose the private engine's copied canonical state. A trusted operator
may later select a real disposable runtime and review the audience policy.

The repository contains only a conservative policy example and reviewed adapter
code. Actual policy, roster, fixture and logs live under ignored `var/`; full
engine/private assets remain outside the checkout. No proactive bot messages are
sent. Humans invoke slash commands for manual verification.

## Deferred full M1 work

Database membership/campaign administration, characters, ledger, OS-backed raw
dice, transaction-safe engine adaptation, durable queues, idempotency, revision
conflicts, outbox/reconciliation, backup/restore and crash/replay tests remain
unimplemented. Before writes, settle one authoritative database/event service;
do not create a competing writable JSON source. These read-only tests do not
fulfill the original M1-001 through M1-012 persistence acceptance cases.
