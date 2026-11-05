"""Source-owned Dormant Void and a real required Dive, never an acknowledgment."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_battle_dormant as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, CastRole
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_battle_state import Required
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_void import _append
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def actual_actor(
    game: "GameService", c: Connection, state: GameState, original: ActorRef
) -> ActorRef:
    """Only the recorded actual transformation can carry this original obligation."""
    if original.kind == "external_pilot" or (
        original.entity in state.sheets
        and state.sheets[original.entity].character_id == original.incarnation
    ):
        resolve(state, original, profiles(c, game.store.campaign_id), require_current_profile=False)
        return original
    values = [x for x in state.harpy_states if x.origin == original and x.alive]
    if len(values) != 1:
        raise WorkflowError(
            "Resume the original affected role; a new character is not its replacement authority."
        )
    value = values[0]
    archive = next(
        (
            x
            for x in state.career_archives
            if x.id == value.original_archive
            and x.actor == original
            and x.ending == "harpy"
            and x.source_event == value.source_event
        ),
        None,
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    proof = GameState.model_validate_json(raw) if raw else None
    born = next((x for x in proof.harpy_states if x.id == value.id), None) if proof else None
    if (
        archive is None
        or born is None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("origin", "source_event", "original_archive", "body_vessel", "frame_instance")
        )
    ):
        raise WorkflowError(
            "SOURCE_DORMANT_CONTINUITY_MISSING: recover the actual original Harpy transformation."
        )
    return ActorRef(kind="external_pilot", entity=value.id)


class DormantService:
    def __init__(self, store: OnboardingStore, game: "GameService | None" = None):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, game or GameService(store)

    def _row(self, c: Connection, identity: str, *, first: bool = False) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision if first else table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] != "dormant_void":
            raise WorkflowError("Open the actual original Dormant consequence.")
        return dict(row)

    def _source(
        self, c: Connection, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any], ActorRef]:
        row, first = self._row(c, identity), self._row(c, identity, first=True)
        body, original = json.loads(row["body_json"]), json.loads(first["body_json"])
        required = Required.model_validate_json(json.dumps(original["requirement"]))
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == first["event_id"],
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        fact = (
            next(
                (
                    x
                    for x in proof.facts
                    if x.get("kind") == "battle_damage_stage" and x.get("id") == identity
                ),
                None,
            )
            if proof
            else None
        )
        gorgon = (
            next(
                (
                    x
                    for x in proof.world.gorgons
                    if required.opponent and x.id == required.opponent.entity
                ),
                None,
            )
            if proof and proof.world
            else None
        )
        if (
            required.kind != "dormant_void"
            or required.target.kind not in ("pilot", "external_pilot")
            or required.opponent is None
            or required.opponent.kind != "gorgon"
            or required.source_pdf != 165
            or gorgon is None
            or gorgon.gorgon_class != "dormant"
            or fact is None
            or Required.model_validate_json(fact.get("requirement", "{}")) != required
            or fact.get("source_action") != (original.get("source_action") or "")
            or original.get("owner") != required.target.model_dump(mode="json")
            or any(
                body.get(k) != original.get(k)
                for k in (
                    "owner",
                    "character",
                    "source_action",
                    "source_work",
                    "requirement",
                    "continuation",
                )
            )
        ):
            raise WorkflowError(
                "SOURCE_DORMANT_MISSING: recover the actual original awakening and victim."
            )
        if original.get("source_action"):
            action = self.game.action(c, original["source_action"])
            if (
                not action["data"].get("battle")
                or action["data"]["battle"]["actor"] != original["owner"]
            ):
                raise WorkflowError("Recover this actual Dormant attack's original source Play.")
        return row, body, required.target

    def _owned(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any], ActorRef]:
        self.game.authorize(c, viewer, game=False)
        row, body, actor = self._source(c, identity)
        handler, _ = MedicalService(self.store)._handler(c)
        if viewer.user_id not in (int(row["subject_id"]), handler):
            raise WorkflowError(
                "This consequence belongs to its original affected Girl and human GM."
            )
        return row, body, actor

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        rows = {
            x["id"]: x
            for x in c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id, table.c.kind == "dormant_void"
                )
                .order_by(table.c.revision)
            ).mappings()
        }
        return [
            dict(
                id=x["id"],
                revision=x["revision"],
                state=x["state"],
                actionable=x["owner_id"] == str(viewer.user_id),
            )
            for x in rows.values()
            if x["state"] != "resolved" and str(viewer.user_id) in (x["owner_id"], x["subject_id"])
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, body, actor = self._owned(c, viewer, identity)
            state = load_state(c, self.store.campaign_id)
            try:
                current = actual_actor(self.game, c, state, actor)
                view = resolve(
                    state,
                    current,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                actual = view.alive
            except (WorkflowError, ValueError):
                current, view, actual = actor, None, False
            sheet = state.sheets.get(actor.entity) if current.kind == "pilot" else None
            from girlframe.engine.m3_dive import resources

            actual_assets, identities = resources(state, current) if actual else ((), ())
            action = (
                self.game.action(c, body["source_action"]) if body.get("source_action") else None
            )
            scene = (
                c.execute(
                    sa.select(t.m2["m2_scenes"]).where(
                        t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_scenes"].c.id == row["scene_id"],
                    )
                )
                .mappings()
                .first()
            )
            own = viewer.user_id == int(row["subject_id"])
            detail = dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                phase=body.get("phase", "void"),
                actor=current.model_dump(mode="json"),
                original=actor.model_dump(mode="json"),
                can_act=own and actual and row["state"] != "resolved",
                body=body,
                channel=int(action["channel_id"])
                if action
                else int(scene["channel_id"])
                if scene
                else None,
                sheet_revision=sheet.revision if sheet is not None and actual else None,
                parent=body.get("source_action"),
                assets=[x.model_dump(mode="json") for x in actual_assets if not x.void]
                if own
                else [],
                identities=[x.model_dump(mode="json") for x in identities if not x.marked]
                if own
                else [],
                heat=view.heat if view is not None and own else 0,
                piloting=action["data"]["prepared"]["piloting"] if action else False,
            )
            detail["requires_source_role_resume"] = (
                actual
                and current.kind == "external_pilot"
                and not any(
                    cast.id == row["scene_id"]
                    and cast.open
                    and any(
                        role.actor == current and role.controller == viewer.user_id
                        for role in cast.roles
                    )
                    for cast in state.scene_casts
                )
            )
            if not actual:
                detail["requires_original_role_port"] = True
            return detail

    def resume_converted_role(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        """The actual owner explicitly continues this source's transformed original person."""

        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, body, original = self._owned(c, viewer, identity)
            state = load_state(c, self.store.campaign_id)
            actual = actual_actor(self.game, c, state, original)
            if (
                row["state"] == "resolved"
                or row["revision"] != revision
                or body.get("phase") != "dive"
                or original.kind != "pilot"
                or actual.kind != "external_pilot"
                or viewer.user_id != int(row["subject_id"])
                or not body.get("source_action")
            ):
                raise WorkflowError(
                    "Resume only this original source's actual converted Harpy role."
                )
            parent = self.game.action(c, body["source_action"])
            if (str(viewer.user_id), str(original.incarnation)) not in proved_converted_originals(
                self.game, c, state, parent
            ):
                raise WorkflowError("Recover this exact original source's actual Harpy conversion.")
            cast = next(
                (x for x in state.scene_casts if x.id == parent["scene_id"] and x.open), None
            )
            if cast is None or parent["state"] in ("complete", "aborted"):
                raise WorkflowError("Recover the actual still-held original source scene.")
            if any(x.actor == actual and x.controller == viewer.user_id for x in cast.roles):
                return dict(actor=actual.model_dump(mode="json"), already_joined=True)
            from girlframe.engine.m3_harpy_defeat import harpy

            born = harpy(state, actual)
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == born.source_event,
                )
            )
            source = GameState.model_validate_json(raw) if raw else None
            converted_cast = (
                next((x for x in source.scene_casts if x.id == cast.id), None) if source else None
            )
            if converted_cast is None or fingerprint(converted_cast) != fingerprint(cast):
                raise WorkflowError(
                    "SOURCE_CAST_CHANGED: recover the exact converted original cast."
                )
            if any(x.actor == original for x in cast.roles):
                raise WorkflowError("The old Pilot role must have ended in the real conversion.")
            event = str(uuid4())
            resumed = cast.model_copy(
                update={
                    "roles": cast.roles
                    + (CastRole(actor=actual, controller=viewer.user_id, source_event=event),),
                    "revision": cast.revision + 1,
                }
            )
            state.scene_casts = [resumed if x.id == cast.id else x for x in state.scene_casts]
            state.facts.append(
                dict(
                    kind="dormant_harpy_role_resumed",
                    work=identity,
                    original=original.model_dump_json(),
                    actor=actual.model_dump_json(),
                    event=event,
                    source_conversion=born.source_event,
                    source_action=parent["id"],
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.dormant_harpy_role_resumed",
                state,
                event_id=event,
                work_id=identity,
                actor_ref=actual.model_dump(mode="json"),
            )
            return dict(actor=actual.model_dump(mode="json"), already_joined=False)

        def authorize(c: Connection) -> None:
            self._owned(c, viewer, identity)
            Access(self.store).authorize(c, viewer, "plays")

        return self.store._write(
            viewer,
            key,
            "m3.dormant_harpy_role_resumed",
            dict(work=identity, revision=revision),
            run,
            auto_audit=False,
            authorize=authorize,
        )

    def alter(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        asset: str | None,
        description: str,
        *,
        piloting: bool,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._owned(c, viewer, identity)
            Access(self.store).authorize(c, viewer, "plays")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, body, actor = self._owned(c, viewer, identity)
            state = load_state(c, self.store.campaign_id)
            if (
                row["state"] == "resolved"
                or row["revision"] != revision
                or state.revision != game_revision
                or body.get("phase", "void") != "void"
            ):
                raise WorkflowError("STALE_DORMANT: reopen the original current consequence.")
            if viewer.user_id != int(row["subject_id"]):
                raise WorkflowError(
                    "The original affected Girl chooses her actual uncorrupted Asset."
                )
            required = Required.model_validate_json(json.dumps(body["requirement"]))
            assert required.opponent is not None
            actor = actual_actor(self.game, c, state, actor)
            event = str(uuid4())
            changed, followups = rules.inflict(
                state,
                profiles(c, self.store.campaign_id),
                actor,
                required.opponent,
                identity,
                asset,
                description,
                event,
                piloting=piloting,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.dormant_void_taken",
                changed,
                event_id=event,
                work_id=identity,
            )
            body.update(corruption_event=event, asset=asset, thresholds=[])
            for index, item in enumerate(followups):
                family = "girl" if item.kind == "girl_void_threshold" else "frame"
                work = str(
                    uuid5(NAMESPACE_URL, "girlframe:dormant:void:" + identity + ":" + str(index))
                )
                threshold = dict(
                    owner=actor.model_dump(mode="json"),
                    character=actor.incarnation,
                    source_action=body.get("source_action"),
                    source_work=identity,
                    details=dict(family=family),
                    source_pdf=19,
                    source_event=event,
                    reason="dormant_void",
                    immediate=True,
                )
                if body.get("source_action"):
                    parent = self.game.action(c, body["source_action"])
                    threshold["continuation"] = self.game.request(
                        c,
                        parent,
                        viewer.user_id,
                        "battle_dormant_threshold",
                        dict(work_id=work, owner=threshold["owner"]),
                    )
                    self.game.save_action(c, parent)
                related(
                    c,
                    self.store,
                    row,
                    work,
                    viewer.user_id,
                    viewer.user_id,
                    "void_threshold",
                    threshold,
                    event,
                )
                body["thresholds"].append(work)
            body["phase"] = (
                "thresholds"
                if followups
                else "dive"
                if required.details.get("close") == "true"
                else "complete"
            )
            _append(c, row, event, body, resolved=body["phase"] == "complete")
            _advance(self.game, c, identity, event, viewer, key)
            return dict(id=identity, phase=body["phase"])

        try:
            return self.store._write(
                viewer,
                key,
                "m3.dormant_void_taken",
                dict(
                    work=identity,
                    revision=revision,
                    game_revision=game_revision,
                    asset=asset,
                    description=description,
                    piloting=piloting,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def proved_converted_originals(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> frozenset[tuple[str, str]]:
    """Only this actual Dormant cost may preserve this exact original rolled actor binding."""
    if not action["data"].get("battle") or not action["data"].get("receipt"):
        return frozenset()
    table = t.m3["m3_required_work"]
    rows = {
        x["id"]: x
        for x in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.kind == "dormant_void")
            .order_by(table.c.revision)
        ).mappings()
    }
    found = set()
    for row in rows.values():
        body = json.loads(row["body_json"])
        if body.get("source_action") != action["id"] or not body.get("corruption_event"):
            continue
        _, source, original = DormantService(game.store, game)._source(c, row["id"])
        if original.kind != "pilot" or source["owner"] != action["data"]["battle"]["actor"]:
            continue
        try:
            actual = actual_actor(game, c, state, original)
        except (WorkflowError, ValueError):
            continue
        if actual == original or not any(
            x.actor == original
            and x.stage == "converted"
            and x.resulting_actor == actual
            and any(work in x.source_works for work in source.get("thresholds", []))
            for x in state.void_thresholds
        ):
            continue
        found.add((original.entity, str(original.incarnation)))
    return frozenset(found)


def _advance(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    service = DormantService(game.store, game)
    row, body, actor = service._source(c, identity)
    if row["state"] == "resolved":
        from girlframe.services.m3_battle import complete_damage_work

        complete_damage_work(game, c, row, event, viewer, key)
        return
    if body.get("phase") == "dive" and body.get("source_action"):
        parent = game.action(c, body["source_action"])
        found = next(
            (
                x
                for x in game.pending(c, parent["id"])
                if x["kind"] == "battle_dormant_dive"
                and json.loads(x["body_json"]).get("work_id") == identity
            ),
            None,
        )
        if found is None:
            game.request(
                c,
                parent,
                int(row["subject_id"]),
                "battle_dormant_dive",
                dict(work_id=identity, owner=body["owner"]),
            )
            game.save_action(c, parent)


def prepare_dive_source(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    channel: int,
) -> dict[str, Any]:
    row, body, actor = DormantService(game.store, game)._owned(
        c, viewer, prepared.source_work or ""
    )
    actor = actual_actor(game, c, state, actor)
    if (
        prepared.play != "dive_deep"
        or row["state"] == "resolved"
        or body.get("phase") != "dive"
        or prepared.parent != body.get("source_action")
        or viewer.user_id != int(row["subject_id"])
    ):
        raise WorkflowError("Use the actual original Girl's source-required Dormant Dive.")
    parent = game.action(c, prepared.parent) if prepared.parent else None
    if parent and (
        parent["channel_id"] != str(channel)
        or not any(
            x["kind"] == "battle_dormant_dive"
            and x["actor_id"] == str(viewer.user_id)
            and json.loads(x["body_json"]).get("work_id") == row["id"]
            for x in game.pending(c, parent["id"])
        )
    ):
        raise WorkflowError("Recover the exact held source scene and Dormant Dive continuation.")
    works = t.m3["m3_required_work"]
    latest = {
        x["id"]: x
        for x in c.execute(
            sa.select(works)
            .where(
                works.c.campaign_id == game.store.campaign_id,
                works.c.subject_id == str(viewer.user_id),
            )
            .order_by(works.c.revision)
        ).mappings()
    }
    if any(
        x["id"] != row["id"]
        and x["state"] != "resolved"
        and json.loads(x["body_json"]).get("immediate")
        for x in latest.values()
    ):
        raise WorkflowError("Finish the original Girl's other actual immediate consequences first.")
    return dict(
        work=row["id"],
        actor=actor.model_dump(mode="json"),
        source_event=body["corruption_event"],
        parent=prepared.parent,
    )


def complete_dive(
    game: "GameService",
    c: Connection,
    child: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    source = child["data"].get("dormant_dive_source")
    if source is None:
        return
    row, body, actor = DormantService(game.store, game)._source(c, source["work"])
    if row["state"] == "resolved":
        if body.get("dive_action") != child["id"]:
            raise WorkflowError("This source already owns a different actual completed Dive.")
        return
    if (
        child["state"] != "complete"
        or child["data"].get("dive", {}).get("actor") != source.get("actor")
        or child["data"].get("prepared", {}).get("source_work") != row["id"]
        or child["parent_id"] != body.get("source_action")
        or body.get("phase") != "dive"
        or source["source_event"] != body.get("corruption_event")
        or not child["data"].get("receipt")
    ):
        raise WorkflowError(
            "Finish the real original source-required Dive and all its consequences."
        )
    body.update(phase="complete", dive_action=child["id"], dive_event=event)
    _append(c, row, event, body, resolved=True)
    if body.get("source_action"):
        choices = t.m2["m2_choices"]
        for request in game.pending(c, body["source_action"]):
            if (
                request["kind"] == "battle_dormant_dive"
                and json.loads(request["body_json"]).get("work_id") == row["id"]
            ):
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == game.store.campaign_id,
                        choices.c.id == request["id"],
                    )
                    .values(state="completed_by_work", revision=request["revision"] + 1)
                )
    _advance(game, c, row["id"], event, viewer, key)


def prove_void_source(
    game: "GameService", c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    row, source, original = DormantService(game.store, game)._source(c, body.get("source_work", ""))
    history = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    state = GameState.model_validate_json(history) if history else None
    fact = (
        next(
            (
                x
                for x in state.facts
                if x.get("kind") == "dormant_void_paid"
                and x.get("work") == row["id"]
                and x.get("event") == first["event_id"]
            ),
            None,
        )
        if state
        else None
    )
    paid = rules.Corruption.model_validate_json(fact["body"]) if fact else None
    if (
        paid is None
        or paid.actor != actor
        or original != actor
        or source.get("corruption_event") != first["event_id"]
        or first["id"] not in source.get("thresholds", [])
        or paid.event != first["event_id"]
        or paid.work != row["id"]
    ):
        raise ValueError(
            "SOURCE_DORMANT_VOID_MISSING: recover the actual original paid corruption."
        )


def complete_void(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    works = t.m3["m3_required_work"]
    threshold = (
        c.execute(
            sa.select(works)
            .where(works.c.campaign_id == game.store.campaign_id, works.c.id == identity)
            .order_by(works.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if threshold is None or threshold["state"] != "resolved":
        raise WorkflowError("Finish the actual Dormant Void threshold before continuing.")
    payload = json.loads(threshold["body_json"])
    service = DormantService(game.store, game)
    row, body, _ = service._source(c, payload["source_work"])
    if identity not in body.get("thresholds", []):
        raise WorkflowError("Recover the original source-owned Dormant threshold.")
    if payload.get("continuation") and body.get("source_action"):
        choices = t.m2["m2_choices"]
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == payload["continuation"],
                choices.c.state == "pending",
            )
            .values(state="completed_by_work", revision=choices.c.revision + 1)
        )
    if any(
        c.scalar(
            sa.select(works.c.state)
            .where(works.c.campaign_id == game.store.campaign_id, works.c.id == work)
            .order_by(works.c.revision.desc())
            .limit(1)
        )
        != "resolved"
        for work in body["thresholds"]
    ):
        return
    required = Required.model_validate_json(json.dumps(body["requirement"]))
    body["phase"] = "dive" if required.details.get("close") == "true" else "complete"
    _append(c, row, event, body, resolved=body["phase"] == "complete")
    _advance(game, c, row["id"], event, viewer, key)
