"""Reusable three-chooser standards setup for original active or acquiring Girls."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_standards as rules
from girlframe.engine.creation_details import StandardChoice
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_girl_runtime_state import StandardGrant, has_rule
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "girl_standards"


class StandardsService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                    table.c.kind == KIND,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This original standards setup is unavailable.")
        return dict(row)

    def _body(
        self, c: Connection, row: dict[str, Any]
    ) -> tuple[dict[str, Any], rules.Plan, tuple[StandardGrant, ...]]:
        try:
            body = json.loads(row["body_json"])
            plan = rules.Plan.model_validate_json(json.dumps(body["plan"]))
            source = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == body["source_event"],
                    )
                )
                .mappings()
                .first()
            )
            metadata = json.loads(source["payload_json"]) if source else {}
            if (
                source is None
                or source["kind"] != "m3.standards_requested"
                or source["actor_id"] != plan.owner.entity
                or metadata.get("work_id") != row["id"]
                or metadata.get("plan_sha256") != fingerprint(plan)
                or row["owner_id"] != plan.owner.entity
                or row["subject_id"] != plan.owner.entity
                or not row["campaign_context"]
            ):
                raise ValueError()
            grants = tuple(
                StandardGrant.model_validate_json(json.dumps(x)) for x in body["choices"].values()
            )
            expected = {"own": plan.owner, "peer": plan.peer, "handler": plan.handler}
            if len({x.role for x in grants}) != len(grants):
                raise ValueError()
            for grant in grants:
                if grant.chooser != expected[grant.role]:
                    raise ValueError()
                if grant.role == "own":
                    if grant.choice != plan.own or grant.source_event != body["source_event"]:
                        raise ValueError()
                    continue
                event = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == self.store.campaign_id,
                            t.events.c.id == grant.source_event,
                        )
                    )
                    .mappings()
                    .first()
                )
                data = json.loads(event["payload_json"]) if event else {}
                if (
                    event is None
                    or event["kind"] != "m3.standard_chosen"
                    or event["actor_id"] != grant.chooser.entity
                    or data.get("work_id") != row["id"]
                    or data.get("grant_sha256") != fingerprint(grant)
                ):
                    raise ValueError()
            if body.get("complete"):
                event = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == self.store.campaign_id,
                            t.events.c.id == row["event_id"],
                        )
                    )
                    .mappings()
                    .first()
                )
                data = json.loads(event["payload_json"]) if event else {}
                if (
                    len(grants) != 3
                    or row["state"] != "resolved"
                    or event is None
                    or event["kind"]
                    != ("m3.standards_compiled" if plan.source_work else "m3.standards_activated")
                    or event["actor_id"] != plan.owner.entity
                    or data.get("work_id") != row["id"]
                    or data.get("plan_sha256") != fingerprint(plan)
                ):
                    raise ValueError()
            return body, plan, grants
        except (ValueError, KeyError):
            raise WorkflowError(
                "SOURCE_STANDARDS_MISSING: recover the original owned choices."
            ) from None

    def _actual(self, c: Connection, plan: rules.Plan) -> None:
        state = load_state(c, self.store.campaign_id)
        rules.validate(state, plan, profiles(c, self.store.campaign_id))
        for actor in (plan.owner, plan.peer):
            if not HandlerService(self.store)._member(c, int(actor.entity)):
                raise WorkflowError("Recover the original standard chooser's campaign membership.")
        owner, appointment = MedicalService(self.store)._handler(c)
        if owner != int(plan.handler.entity) or appointment != plan.appointment:
            raise WorkflowError("Recover the standards setup's original Handler appointment.")
        if plan.handler.incarnation is not None and (
            state.handler_persona is None or state.handler_persona.id != plan.handler.incarnation
        ):
            raise WorkflowError("Recover the original standards chooser's Handler persona.")
        if plan.source_work:
            row, body, actor = MedicalService(self.store)._source(c, plan.source_work)
            if (
                actor != plan.owner
                or row["state"] != "pending"
                or body.get("stage") != "standards_setup"
                or body.get("pending_exchange", {}).get("acquired") != rules.RULE
            ):
                raise WorkflowError("Recover the actual pending medical acquisition first.")
        elif not has_rule(state.sheets[plan.owner.entity], rules.RULE, "PRINCESS"):
            raise WorkflowError("This original Girl does not own the standards rule.")

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        body: dict[str, Any],
        event: str,
        *,
        resolved: bool = False,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "event_id", "body_json", "state")
                },
                revision=row["revision"] + 1,
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
                state="resolved" if resolved else "pending",
            )
        )

    def _rows(self, c: Connection) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return list(
            {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.kind == KIND,
                    )
                    .order_by(table.c.revision)
                ).mappings()
            }.values()
        )

    def existing(
        self, c: Connection, actor: ActorRef, source_work: str | None
    ) -> dict[str, Any] | None:
        for row in self._rows(c):
            _, plan, _ = self._body(c, row)
            if (
                plan.owner == actor
                and plan.source_work == source_work
                and row["state"] != "resolved"
            ):
                return row
        return None

    def preview(self, viewer: GuildViewer, source_work: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef(
                kind="pilot",
                entity=str(viewer.user_id),
                incarnation=self.game.character_binding(
                    c, state, viewer.user_id, require_current_profile=False
                ),
            )
            existing = self.existing(c, actor, source_work)
            if existing is None and source_work:
                compiled = self.compiled(c, actor, source_work)
                if compiled:
                    existing = next(
                        (
                            row
                            for row in self._rows(c)
                            if self._body(c, row)[1] == compiled[0]
                            and json.loads(row["body_json"]).get("complete")
                        ),
                        None,
                    )
            peers = []
            for uid, sheet in state.sheets.items():
                if (
                    uid == actor.entity
                    or depth(state, actor, current_ref(state, int(uid))) < 1
                    or not HandlerService(self.store)._member(c, int(uid))
                ):
                    continue
                try:
                    incarnation = self.game.character_binding(
                        c, state, int(uid), require_current_profile=False
                    )
                except WorkflowError:
                    continue
                peers.append(
                    dict(
                        ref=ActorRef(kind="pilot", entity=uid, incarnation=incarnation).model_dump(
                            mode="json"
                        ),
                        label=sheet.callsign,
                    )
                )
            return dict(
                actor=actor.model_dump(mode="json"),
                game_revision=state.revision,
                existing=existing["id"] if existing else None,
                peers=peers,
            )

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        game_revision: int,
        peer: ActorRef,
        own: StandardChoice,
        source_work: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != game_revision:
                raise WorkflowError("STALE_STANDARDS: reopen the current actual Girl and Bond.")
            actor = ActorRef(
                kind="pilot",
                entity=str(viewer.user_id),
                incarnation=self.game.character_binding(
                    c, state, viewer.user_id, require_current_profile=False
                ),
            )
            handler, appointment = MedicalService(self.store)._handler(c)
            plan = rules.Plan(
                owner=actor,
                peer=peer,
                own=own,
                appointment=appointment,
                handler=ActorRef(
                    kind="handler",
                    entity=str(handler),
                    incarnation=state.handler_persona.id if state.handler_persona else None,
                ),
                source_work=source_work,
            )
            self._actual(c, plan)
            if rules.ready(state.sheets[actor.entity]):
                raise WorkflowError("The original Girl already has three sourced standards.")
            existing = self.existing(c, actor, source_work)
            if existing:
                raise WorkflowError(
                    "Resume the original standards request before choosing a different setup."
                )
            identity, event = str(uuid4()), str(uuid4())
            grant = StandardGrant(role="own", choice=own, chooser=actor, source_event=event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.standards_requested",
                event_id=event,
                work_id=identity,
                plan_sha256=fingerprint(plan),
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                viewer.user_id,
                viewer.user_id,
                KIND,
                dict(
                    plan=plan.model_dump(mode="json"),
                    source_event=event,
                    choices={"own": grant.model_dump(mode="json")},
                    immediate=True,
                ),
                event,
            )
            return dict(id=identity, revision=1)

        try:
            peer = ActorRef.model_validate_json(peer.model_dump_json())
            own = StandardChoice.model_validate_json(own.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.standards_requested",
                dict(
                    game_revision=game_revision,
                    peer=peer.model_dump(mode="json"),
                    own=own.model_dump(mode="json"),
                    source_work=source_work,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError(
                "Choose valid actual standard participants and a standard."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _view(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        row = self._row(c, identity)
        body, plan, grants = self._body(c, row)
        actors = {"own": plan.owner, "peer": plan.peer, "handler": plan.handler}
        role = next(
            (name for name, actor in actors.items() if actor.entity == str(viewer.user_id)), None
        )
        if role is None:
            raise WorkflowError("These standards belong to their actual three choosers.")
        try:
            self._actual(c, plan)
            stale = False
        except (ValueError, WorkflowError):
            stale = True
        chosen = {x.role for x in grants}
        return dict(
            id=identity,
            revision=row["revision"],
            game_revision=load_state(c, self.store.campaign_id).revision,
            role=role,
            owner=role == "own",
            stale=stale,
            state=row["state"],
            complete=body.get("complete", False),
            choices=[
                dict(role=x.role, label=x.choice.label, is_order=x.role == "handler")
                for x in grants
            ],
            can_choose=not stale
            and row["state"] == "pending"
            and role in ("peer", "handler")
            and role not in chosen,
            can_finalize=not stale
            and row["state"] == "pending"
            and role == "own"
            and chosen == {"own", "peer", "handler"},
            can_withdraw=role == "own" and row["state"] == "pending",
            source_work=plan.source_work if role == "own" else None,
            compiled=bool(plan.source_work and body.get("complete")),
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._view(c, viewer, identity)

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self.game.authorize(c, viewer, game=False)
            data = self._view(c, viewer, identity)
            if not data["can_withdraw"]:
                raise WorkflowError("Only the original Girl may withdraw this pending setup.")
            _, plan, _ = self._body(c, self._row(c, identity))
            state = load_state(c, self.store.campaign_id)
            if (
                self.game.character_binding(c, state, viewer.user_id, require_current_profile=False)
                != plan.owner.incarnation
            ):
                raise WorkflowError("Recover the original Girl before withdrawing her choices.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            body, plan, _ = self._body(c, row)
            if row["revision"] != revision:
                raise WorkflowError("STALE_STANDARDS: reopen the actual pending setup.")
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.standards_withdrawn",
                work_id=identity,
                plan_sha256=fingerprint(plan),
            )
            self._save(c, row, body | dict(cancelled=True, immediate=False), event, resolved=True)
            return dict(id=identity, cancelled=True)

        return self.store._write(
            viewer,
            key,
            "m3.standards_withdrawn",
            dict(id=identity, revision=revision),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def choose(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, selected: StandardChoice
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self.game.authorize(c, viewer, game=False)
            self._view(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            body, plan, _ = self._body(c, row)
            self._actual(c, plan)
            data = self._view(c, viewer, identity)
            if row["revision"] != revision or not data["can_choose"]:
                raise WorkflowError("STALE_STANDARD: reopen your own current standard choice.")
            role: Literal["own", "peer", "handler"] = data["role"]
            actor = plan.peer if role == "peer" else plan.handler
            event = str(uuid4())
            grant = StandardGrant(
                role=role,
                chooser=actor,
                choice=selected,
                source_event=event,
                appointment=plan.appointment if role == "handler" else None,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.standard_chosen",
                event_id=event,
                work_id=identity,
                grant_sha256=fingerprint(grant),
            )
            self._save(
                c,
                row,
                body | {"choices": body["choices"] | {role: grant.model_dump(mode="json")}},
                event,
            )
            return dict(id=identity, revision=revision + 1)

        try:
            selected = StandardChoice.model_validate_json(selected.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.standard_chosen",
                dict(id=identity, revision=revision, selected=selected.model_dump(mode="json")),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError("Choose one valid standard.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def finalize(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, game_revision: int
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            row = self._row(c, identity)
            _, plan, _ = self._body(c, row)
            if plan.owner.entity != str(viewer.user_id):
                raise WorkflowError("Only the original Girl confirms her complete standards setup.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row = self._row(c, identity)
            body, plan, grants = self._body(c, row)
            state = load_state(c, self.store.campaign_id)
            if (
                row["revision"] != revision
                or state.revision != game_revision
                or not self._view(c, viewer, identity)["can_finalize"]
            ):
                raise WorkflowError("STALE_STANDARDS: review the three actual current choices.")
            MedicalService(self.store)._idle(c)
            updated = rules.grant(state, plan, grants, profiles(c, self.store.campaign_id))
            source = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.standards_compiled" if plan.source_work else "m3.standards_activated",
                updated if not plan.source_work else None,
                work_id=identity,
                plan_sha256=fingerprint(plan),
            )
            self._save(c, row, body | dict(complete=True, immediate=False), source, resolved=True)
            return dict(id=identity, complete=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.standards_completed",
                dict(id=identity, revision=revision, game_revision=game_revision),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError("The standards source needs recovery.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def compiled(
        self, c: Connection, actor: ActorRef, source_work: str
    ) -> tuple[rules.Plan, tuple[StandardGrant, ...]] | None:
        for row in self._rows(c):
            body, plan, grants = self._body(c, row)
            if plan.owner == actor and plan.source_work == source_work and body.get("complete"):
                try:
                    self._actual(c, plan)
                except (ValueError, WorkflowError):
                    continue
                event = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == self.store.campaign_id,
                            t.events.c.id == row["event_id"],
                        )
                    )
                    .mappings()
                    .first()
                )
                data = json.loads(event["payload_json"]) if event else {}
                if (
                    row["state"] != "resolved"
                    or event is None
                    or event["kind"] != "m3.standards_compiled"
                    or event["actor_id"] != actor.entity
                    or data.get("work_id") != row["id"]
                    or data.get("plan_sha256") != fingerprint(plan)
                ):
                    raise WorkflowError(
                        "SOURCE_STANDARDS_COMPLETION_MISSING: recover the original confirmation."
                    )
                return plan, grants
        return None

    def supersede(self, c: Connection, source_work: str, event: str) -> None:
        for row in self._rows(c):
            body, plan, _ = self._body(c, row)
            if plan.source_work == source_work and row["state"] != "resolved":
                self._save(
                    c, row, body | dict(cancelled=True, immediate=False), event, resolved=True
                )

    def _tasks(
        self, c: Connection, viewer: GuildViewer, *, history: bool = False
    ) -> list[dict[str, Any]]:
        result = []
        for row in self._rows(c):
            if not history and row["state"] == "resolved":
                continue
            _, plan, _ = self._body(c, row)
            if str(viewer.user_id) not in (
                plan.owner.entity,
                plan.peer.entity,
                plan.handler.entity,
            ):
                continue
            data = self._view(c, viewer, row["id"])
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    state=row["state"],
                    stale=data["stale"],
                    label="Owned Princess standards",
                    actionable=data["can_choose"] or data["can_finalize"] or data["can_withdraw"],
                )
            )
        return result
