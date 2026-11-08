"""Durable private human rulings bound to real pending work, never arbitrary state setters."""

import json
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import p1_facilitator as rules
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def configured(game: GameService, c: Connection) -> rules.Recipient | None:
    body = (
        c.execute(
            sa.select(t.events.c.id, t.events.c.payload_json)
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "p1.facilitator_configured",
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if body is None:
        return None
    value = json.loads(body["payload_json"])
    return rules.Recipient(kind=value["recipient_kind"], id=value["recipient_id"], event=body["id"])


def recipient_is(viewer: GuildViewer, recipient: rules.Recipient | None) -> bool:
    return recipient is not None and (
        recipient.kind == "user"
        and recipient.id == viewer.user_id
        or recipient.kind == "role"
        and recipient.id in viewer.role_ids
    )


def pending(game: GameService, c: Connection, channel: int | None = None) -> list[rules.Request]:
    table = t.m3["m3_required_work"]
    seen: set[str] = set()
    result = []
    for row in c.execute(
        sa.select(table)
        .where(table.c.campaign_id == game.store.campaign_id, table.c.kind == rules.KIND)
        .order_by(table.c.revision.desc())
    ).mappings():
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        value = rules.Request.model_validate_json(row["body_json"])
        if row["state"] == "pending" and (channel is None or value.channel == channel):
            result.append(value)
    return result


def require_scene_clear(
    game: GameService, c: Connection, channel: int, action: dict[str, Any] | None = None
) -> None:
    for value in pending(game, c, channel):
        if value.status == "awaiting_owned_effect" and action is not None:
            ancestor = action
            while ancestor.get("parent_id"):
                ancestor = game.action(c, ancestor["parent_id"])
            if value.source_kind == "action" and value.source in (action["id"], ancestor["id"]):
                continue
        raise WorkflowError(
            "FACILITATOR_REQUIRED: open request " + value.id + " before proceeding."
        )


class FacilitatorService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                    table.c.kind == rules.KIND,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This campaign has no such adjudication request.")
        return dict(row)

    def _save(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        value: rules.Request,
        scope: WorkScope,
        *,
        index: int = 0,
    ) -> str:
        event = self.game.event(
            c,
            viewer.user_id,
            key,
            "p1.facilitator_request_changed",
            event_index=index,
            request=value.id,
            request_revision=value.revision,
            status=value.status,
        )
        table = t.m3["m3_required_work"]
        recipient = configured(self.game, c)
        owner = recipient.id if recipient and recipient.kind == "user" else value.requester
        c.execute(
            table.insert().values(
                campaign_id=self.store.campaign_id,
                id=value.id,
                revision=value.revision,
                **scope.model_dump(),
                owner_id=str(owner),
                subject_id=str(value.requester),
                kind=rules.KIND,
                state="resolved" if value.status in ("resolved", "declined") else "pending",
                body_json=value.model_dump_json(),
                event_id=event,
            )
        )
        return event

    def _notice(self, c: Connection, value: rules.Request, event: str) -> None:
        assignment = value.recipient.event if value.recipient else "unconfigured"
        identity = str(
            uuid5(NAMESPACE_URL, f"{self.store.campaign_id}:facilitator:{value.id}:{assignment}")
        )
        if c.scalar(
            sa.select(t.p1_notices.c.id).where(
                t.p1_notices.c.campaign_id == self.store.campaign_id, t.p1_notices.c.id == identity
            )
        ):
            return
        c.execute(
            t.p1_notices.insert().values(
                campaign_id=self.store.campaign_id,
                id=identity,
                request_id=value.id,
                request_revision=value.revision,
                channel_id=str(value.channel),
                recipient_json=value.recipient.model_dump_json() if value.recipient else "null",
                event_id=event,
                nonce=str(int(uuid5(NAMESPACE_URL, identity)) % (2**63 - 1)),
                state="pending",
            )
        )

    def configure(
        self, viewer: GuildViewer, key: str, kind: Literal["user", "role"], identity: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            if type(identity) is not int or identity <= 0 or kind not in ("user", "role"):
                raise WorkflowError("Choose one actual facilitator user or role.")
            if kind == "role" and identity == self.store.policy.guild_id:
                raise WorkflowError("The everyone role cannot be the human facilitator.")
            if kind == "user":
                # A facilitator may have no Girl: campaign membership is the actual requirement.
                members = t.members
                if not c.scalar(
                    sa.select(members.c.user_id).where(
                        members.c.campaign_id == self.store.campaign_id,
                        members.c.user_id == str(identity),
                        members.c.active.is_(True),
                    )
                ):
                    raise WorkflowError("The designated human must first join this campaign.")
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "p1.facilitator_configured",
                recipient_kind=kind,
                recipient_id=identity,
            )
            recipient = rules.Recipient(kind=kind, id=identity, event=event)
            for index, value in enumerate(pending(self.game, c), 1):
                row = self._row(c, value.id)
                # A changed recipient receives only a safe notice, not the former private grant.
                updated = value.model_copy(
                    update=dict(
                        revision=value.revision + 1,
                        recipient=recipient,
                        shared=False,
                        status="awaiting_ruling",
                    )
                )
                saved = self._save(
                    c,
                    viewer,
                    key,
                    updated,
                    WorkScope.model_validate({k: row[k] for k in WorkScope.model_fields}),
                    index=index,
                )
                self._notice(c, updated, saved)
            return recipient.model_dump(mode="json")

        return self.store._write(
            viewer,
            key,
            "p1.facilitator_configured",
            dict(kind=kind, identity=identity),
            operation,
            auto_audit=False,
            authorize=lambda c: self.store.administrator(viewer),
        )

    def _source(
        self, c: Connection, viewer: GuildViewer, kind: str, identity: str, channel: int
    ) -> tuple[WorkScope, int, str | None, str | None, bool]:
        scene = self.game.scene(c, channel)
        if kind == "action":
            action = self.game.action(c, identity)
            audience = action["data"].get("private_audience") or action["data"]["participants"]
            if (
                viewer.user_id not in audience
                or action["channel_id"] != str(channel)
                or action["scene_id"] != scene["id"]
                or action["state"] in ("complete", "aborted")
            ):
                raise WorkflowError("Use your actual pending source action in its original scene.")
            receipt = action["data"].get("receipt")
            return (
                WorkScope(scene_id=scene["id"]),
                action["revision"],
                action["actor_id"],
                receipt["id"] if receipt else None,
                bool(receipt or self.game.pending(c, action["id"])),
            )
        if kind == "work":
            table = t.m3["m3_required_work"]
            row = (
                c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["kind"] == rules.KIND
                or row["state"] != "pending"
                or str(viewer.user_id) not in (row["owner_id"], row["subject_id"])
            ):
                raise WorkflowError("Only the actual pending source owner may request this ruling.")
            if viewer.user_id not in scene["participants"]:
                raise WorkflowError("Use an actual joined campaign scene for the notice.")
            return (
                WorkScope.model_validate({k: row[k] for k in WorkScope.model_fields}),
                row["revision"],
                row["subject_id"],
                None,
                True,
            )
        if (
            kind != "scene"
            or identity != scene["id"]
            or viewer.user_id not in scene["participants"]
        ):
            raise WorkflowError("Use your actual joined scene, not a fabricated source.")
        return WorkScope(scene_id=scene["id"]), scene["revision"], None, None, False

    def request(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        source_kind: str,
        source: str,
        rule: str,
        revision: int,
        reason: str,
        *,
        shared: bool = False,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("Reopen the current source before requesting adjudication.")
            from girlframe.services.m3_access import load_registry

            known_rule = rule in {entry.id for entry in load_registry().entries}
            if not known_rule and source_kind == "work":
                table = t.m3["m3_required_work"]
                actual_kind = c.scalar(
                    sa.select(table.c.kind)
                    .where(table.c.campaign_id == self.store.campaign_id, table.c.id == source)
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                known_rule = actual_kind is not None and rule == "work:" + actual_kind
            if not known_rule and source_kind == "action":
                known_rule = any(
                    rule == "choice:" + row["kind"] and row["actor_id"] == str(viewer.user_id)
                    for row in self.game.pending(c, source)
                )
            if not known_rule:
                raise WorkflowError(
                    "Select an actual inventoried rule or owned pending source selector."
                )
            scope, source_revision, actor, receipt, mandatory = self._source(
                c, viewer, source_kind, source, channel
            )
            identity = str(
                uuid5(
                    NAMESPACE_URL,
                    f"{self.store.campaign_id}:{source_kind}:{source}:{rule}:{viewer.user_id}",
                )
            )
            existing = next((x for x in pending(self.game, c) if x.id == identity), None)
            if existing:
                return dict(id=existing.id, status=existing.status)
            recipient = configured(self.game, c)
            value = rules.Request(
                id=identity,
                revision=1,
                requester=viewer.user_id,
                channel=channel,
                rule=rule,
                source_kind=cast(Literal["action", "work", "scene"], source_kind),
                source=source,
                source_revision=source_revision,
                state_revision=state.revision,
                source_actor=actor,
                receipt=receipt,
                mandatory=mandatory,
                reason=reason,
                shared=shared and recipient is not None,
                recipient=recipient,
                status="awaiting_ruling" if recipient else "configuration_required",
            )
            event = self._save(c, viewer, key, value, scope)
            self._notice(c, value, event)
            return dict(id=identity, status=value.status)

        return self.store._write(
            viewer,
            key,
            "p1.facilitator_requested",
            dict(
                channel=channel,
                source_kind=cast(Literal["action", "work", "scene"], source_kind),
                source=source,
                rule=rule,
                revision=revision,
                reason=reason,
                shared=shared,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            value = rules.Request.model_validate_json(self._row(c, identity)["body_json"])
            actual = configured(self.game, c)
            dm = recipient_is(viewer, actual)
            if viewer.user_id != value.requester and not dm:
                raise WorkflowError(
                    "This private request belongs to its original owner and facilitator."
                )
            visible = (
                viewer.user_id == value.requester
                or dm
                and value.shared
                and value.recipient == actual
            )
            payload = value.model_dump(mode="json")
            if not visible:
                for field in ("rule", "source", "source_actor", "receipt", "reason", "ruling"):
                    payload[field] = "Private source details withheld by the original owner."
            jobs = [
                dict(x)
                for x in c.execute(
                    sa.select(
                        t.p1_notices.c.state, t.p1_notices.c.last_error, t.p1_notices.c.message_id
                    ).where(
                        t.p1_notices.c.campaign_id == self.store.campaign_id,
                        t.p1_notices.c.request_id == identity,
                    )
                ).mappings()
            ]
            return dict(
                request=payload,
                can_rule=dm,
                own=viewer.user_id == value.requester,
                revision=value.revision,
                game_revision=load_state(c, self.store.campaign_id).revision,
                delivery=jobs,
            )

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            actual = configured(self.game, c)
            return [
                dict(
                    id=x.id,
                    revision=x.revision,
                    label="Human ruling: " + x.status,
                    pending=(
                        recipient_is(viewer, actual)
                        and x.status in ("awaiting_ruling", "adapter_blocked")
                        or x.requester == viewer.user_id
                        and (
                            not x.shared
                            or x.status in ("configuration_required", "awaiting_owned_effect")
                        )
                    ),
                )
                for x in pending(self.game, c)
                if x.requester == viewer.user_id or recipient_is(viewer, actual)
            ]

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        operation: Literal["share", "rule", "decline", "resume"],
        text: str = "",
        *,
        adapter: Literal["existing_source", "blocked", "fiction_only"] = "blocked",
    ) -> dict[str, Any]:
        def apply(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            value = rules.Request.model_validate_json(row["body_json"])
            state = load_state(c, self.store.campaign_id)
            recipient = configured(self.game, c)
            if (
                value.revision != expected
                or state.revision != game_revision
                or row["state"] != "pending"
            ):
                raise WorkflowError("STALE_ADJUDICATION: reopen the actual request.")
            if adapter not in ("existing_source", "blocked", "fiction_only"):
                raise WorkflowError("Choose a supported, blocked or fiction-only route.")
            dm = recipient_is(viewer, recipient)
            own = viewer.user_id == value.requester
            changes: dict[str, Any] = dict(revision=value.revision + 1)
            if operation == "share" and own:
                if recipient is None:
                    raise WorkflowError("Configure the facilitator first.")
                changes.update(shared=True, recipient=recipient)
            elif operation == "rule" and dm:
                if not text.strip() or len(text) > 1200:
                    raise WorkflowError("Record the actual human ruling and reason.")
                if adapter == "fiction_only" and (value.mandatory or value.source_kind != "scene"):
                    raise WorkflowError("Narration cannot complete a mandatory mechanical effect.")
                changes.update(
                    ruling=text,
                    adapter=adapter,
                    ruling_by=viewer.user_id,
                    status="adapter_blocked" if adapter == "blocked" else "awaiting_owned_effect",
                )
            elif operation == "decline" and (dm or own):
                if value.mandatory or value.source_kind != "scene":
                    raise WorkflowError("A mandatory source cannot be discarded.")
                changes.update(status="declined", ruling=text)
            elif operation == "resume" and (dm or own):
                if value.status != "awaiting_owned_effect" or not value.ruling_by:
                    raise WorkflowError("A real ruling and supported source effect are required.")
                if value.source_kind == "action":
                    action = self.game.action(c, value.source)
                    receipt = action["data"].get("receipt")
                    if (
                        action["state"] != "complete"
                        or action["actor_id"] != value.source_actor
                        or value.receipt
                        and (not receipt or receipt["id"] != value.receipt)
                    ):
                        raise WorkflowError(
                            "Complete the actual original action without replacing its receipt."
                        )
                elif value.source_kind == "work":
                    table = t.m3["m3_required_work"]
                    source = (
                        c.execute(
                            sa.select(table)
                            .where(
                                table.c.campaign_id == self.store.campaign_id,
                                table.c.id == value.source,
                            )
                            .order_by(table.c.revision.desc())
                            .limit(1)
                        )
                        .mappings()
                        .one()
                    )
                    if source["state"] != "resolved" or source["subject_id"] != value.source_actor:
                        raise WorkflowError("Apply the actual supported source effect first.")
                elif value.adapter != "fiction_only":
                    raise WorkflowError(
                        "A scene note is fiction-only; it supplies no mechanical effect."
                    )
                changes.update(status="resolved")
            else:
                raise WorkflowError("Only the actual owner or designated facilitator may do that.")
            updated = value.model_copy(update=changes)
            self._save(
                c,
                viewer,
                key,
                updated,
                WorkScope.model_validate({k: row[k] for k in WorkScope.model_fields}),
            )
            return dict(id=identity, status=updated.status, revision=updated.revision)

        return self.store._write(
            viewer,
            key,
            "p1.facilitator_changed",
            dict(
                id=identity,
                expected=expected,
                game_revision=game_revision,
                operation=operation,
                text=text,
                adapter=adapter,
            ),
            apply,
            auto_audit=False,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
        )

    def candidates(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        from girlframe.services.m3_access import load_registry

        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            scene = self.game.scene(c, channel)
            sources = []
            for kind, identity, label in [("scene", scene["id"], "This actual scene")] + [
                ("action", x["id"], "Pending Play: " + json.loads(x["body_json"])["play"])
                for x in c.execute(
                    sa.select(t.m2["m2_actions"]).where(
                        t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_actions"].c.channel_id == str(channel),
                        t.m2["m2_actions"].c.state.not_in(("complete", "aborted")),
                    )
                ).mappings()
            ]:
                try:
                    self._source(c, viewer, kind, identity, channel)
                except WorkflowError:
                    continue
                sources.append((kind + ":" + identity, label))
            table = t.m3["m3_required_work"]
            seen = set()
            for item in c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id)
                .order_by(table.c.revision.desc())
            ).mappings():
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                try:
                    self._source(c, viewer, "work", item["id"], channel)
                except WorkflowError:
                    continue
                sources.append(
                    ("work:" + item["id"], "Required: " + item["kind"].replace("_", " "))
                )
            if not sources:
                raise WorkflowError("Join the actual affected scene before requesting a ruling.")
            return dict(
                sources=sources,
                game_revision=load_state(c, self.store.campaign_id).revision,
                rules=[
                    (x.id, x.title)
                    for x in load_registry().entries
                    if x.required and x.module == "core"
                ],
            )
