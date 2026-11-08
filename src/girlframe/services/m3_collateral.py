"""Real source-owned collateral effects and concrete world consequences."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_collateral as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def latest(game: GameService, c: Connection, identity: str) -> dict[str, Any]:
    work = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(work)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == identity)
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual source-owned consequence")
    return dict(row)


def append(
    c: Connection, row: dict[str, Any], event: str, body: dict[str, Any], state: str
) -> None:
    c.execute(
        t.m3["m3_required_work"]
        .insert()
        .values(
            **{
                k: v
                for k, v in row.items()
                if k not in ("revision", "body_json", "event_id", "state")
            },
            revision=row["revision"] + 1,
            event_id=event,
            body_json=json.dumps(body, sort_keys=True),
            state=state,
        )
    )


def materialize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    for fact in state.facts:
        if fact.get("kind") != "collateral_stage" or fact.get("event") != event:
            continue
        source = rules.Source.model_validate_json(fact["body"])
        work = t.m3["m3_required_work"]
        if c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == game.store.campaign_id, work.c.id == source.id
            )
        ):
            continue
        choice = game.request(
            c,
            action,
            source.judge,
            "battle_collateral",
            dict(work_id=source.id, source_action=action["id"]),
        )
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            source.id,
            source.judge,
            source.actor_controller,
            "collateral",
            dict(
                source=source.model_dump(mode="json"),
                source_action=action["id"],
                continuation=choice,
                phase="choose",
                immediate=True,
            ),
            event,
        )
        game.save_action(c, action)


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    for request in game.pending(c, action["id"]):
        if request["kind"] != "battle_collateral":
            continue
        row = latest(game, c, json.loads(request["body_json"])["work_id"])
        body = json.loads(row["body_json"])
        if body.get("phase") != "waiting":
            continue
        if any(latest(game, c, x)["state"] != "resolved" for x in body.get("followups", ())):
            continue
        append(c, row, event, body | dict(phase="complete"), "resolved")
        choices = t.m2["m2_choices"]
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == request["id"],
                choices.c.state == "pending",
            )
            .values(state="completed_by_work", revision=choices.c.revision + 1)
        )


class CollateralService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, identity: str) -> tuple[dict[str, Any], rules.Source]:
        row = latest(self.game, c, identity)
        if row["kind"] != "collateral":
            raise WorkflowError("Open the actual printed collateral consequence")
        body = json.loads(row["body_json"])
        source = rules.Source.model_validate(body["source"])
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == source.event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        if original is None or not any(
            x.get("kind") == "collateral_stage"
            and x.get("id") == identity
            and rules.Source.model_validate_json(x["body"]) == source
            for x in original.facts
        ):
            raise WorkflowError("Prove this exact actual collateral source event")
        action = self.game.action(c, source.action)
        responses = t.m2["m2_responses"]
        response = (
            c.execute(
                sa.select(responses).where(
                    responses.c.campaign_id == self.store.campaign_id,
                    responses.c.choice_id == source.choice,
                    responses.c.event_id == source.event,
                )
            )
            .mappings()
            .first()
        )
        if (
            action["data"].get("play") != "all_out_assault"
            or action["data"].get("result", {}).get("tier") != "high"
            or response is None
            or int(response["actor_id"]) != source.judge
            or "collateral_damage" not in json.loads(response["answer_json"])["options"]
        ):
            raise WorkflowError("Prove the original source judge's actual high collateral choice")
        from girlframe.services.m3_battle import proved_judge

        if proved_judge(self.game, c, action)[1:] != (source.judge, source.appointment):
            raise WorkflowError("Recover the original scoped collateral adjudicator")
        return row, source

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row, source = self._proof(c, identity)
            if viewer.user_id != source.judge:
                raise WorkflowError(
                    "Only the actual source adjudicator reads this collateral choice"
                )
            state = load_state(c, self.store.campaign_id)
            action = self.game.action(c, source.action)
            bound = profiles(c, self.store.campaign_id)
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == action["data"]["battle"]["roll_event"],
                )
            )
            frozen = GameState.model_validate_json(raw) if raw else None
            cast = (
                next((x for x in frozen.scene_casts if x.id == action["scene_id"]), None)
                if frozen
                else None
            )
            actors: list[dict[str, Any]] = []
            if cast is None:
                from girlframe.engine.m3_actor_state import SceneCast
                from girlframe.services.m3_tag_markers import context

                tag_context = context(action)
                cast = (
                    SceneCast.model_validate_json(json.dumps(tag_context["cast"]))
                    if tag_context
                    else None
                )
            if cast:
                from girlframe.engine.m3_battle import category, intact_assets
                from girlframe.services.m3_battle import _visible

                for role in cast.roles:
                    if not _visible(state, role.actor, viewer.user_id):
                        continue
                    try:
                        actual = resolve(state, role.actor, bound, require_current_profile=False)
                    except ValueError:
                        continue
                    if actual.offstage_source is not None:
                        continue
                    if (
                        category(state, role.actor) in ("npc", "handler")
                        and actual.rules != "handler_girl"
                    ):
                        actors.append(
                            dict(
                                token=role.actor.token + ":body",
                                actor=role.actor.model_dump(mode="json"),
                                asset=None,
                                label=actual.label + ": damage consequence",
                            )
                        )
                    actors.extend(
                        dict(
                            token=role.actor.token + ":" + asset.id,
                            actor=role.actor.model_dump(mode="json"),
                            asset=asset.id,
                            label=actual.label + ": " + asset.name,
                        )
                        for asset in intact_assets(state, role.actor, bound)
                        if not asset.concealed or actual.controller == viewer.user_id
                    )
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                phase=json.loads(row["body_json"])["phase"],
                source=source.model_dump(mode="json"),
                objects=[
                    dict(id=x.id, name=x.name)
                    for x in state.held_items
                    if x.asset_json is None
                    and x.condition == "intact"
                    and cast
                    and (
                        x.location_mode == "scene"
                        and x.scene_id == action["scene_id"]
                        or x.location_mode == "carried"
                        and any(x.holder == r.actor for r in cast.roles)
                        and _visible(state, x.holder, viewer.user_id)
                    )
                ],
                structures=[
                    dict(id=x.id, name=x.name, cell=x.cell)
                    for x in state.world.locations
                    if x.condition != "destroyed"
                ]
                if state.world
                else [],
                assets=actors,
            )

    def submit(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        choice: rules.Selection,
    ) -> dict[str, Any]:
        choice = rules.Selection.model_validate_json(choice.model_dump_json())

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            row, source = self._proof(c, identity)
            state = load_state(c, self.store.campaign_id)
            body = json.loads(row["body_json"])
            if (
                viewer.user_id != source.judge
                or row["revision"] != revision
                or state.revision != game_revision
                or body["phase"] != "choose"
            ):
                raise WorkflowError(
                    "STALE_COLLATERAL: the actual source judge owns this original choice"
                )
            current = self.get(viewer, identity)
            allowed = {
                (json.dumps(x["actor"], sort_keys=True), x["asset"]) for x in current["assets"]
            }
            if any(
                (json.dumps(x.actor.model_dump(mode="json"), sort_keys=True), x.asset)
                not in allowed
                for x in choice.assets
            ):
                raise WorkflowError("Use actual original-scene owned collateral Assets")
            if not set(choice.objects) <= {x["id"] for x in current["objects"]}:
                raise WorkflowError(
                    "Destroy only actual original-scene source-proved held objects."
                )
            from girlframe.services.m3_items import prove_item

            for item in choice.objects:
                prove_item(c, self.game, state, item)
            event = str(uuid4())
            state, loss = rules.perform(state, source, choice, event)
            followups: list[str] = []
            from girlframe.services.m3_battle import damage_actor, synchronize_damage

            for index, target in enumerate(choice.assets):
                state, required = damage_actor(
                    self.game,
                    c,
                    state,
                    target=target.actor,
                    asset_id=target.asset,
                    source_action=source.action,
                    source_work=identity,
                    event=event,
                    actor=None,
                    opponent=source.actor,
                    chooser_controller=source.actor_controller,
                    occurrence="collateral:" + str(index),
                    indirect=True,
                )
                followups.extend(required)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.collateral_applied",
                state,
                event_id=event,
                source_work=identity,
                source_action=source.action,
            )
            append(
                c,
                row,
                event,
                body | dict(phase="waiting", followups=followups, loss=loss.id if loss else None),
                "pending",
            )
            synchronize_damage(self.game, c, event)
            if loss is not None:
                from girlframe.services.m3_quadrant_loss import materialize_loss

                materialize_loss(self.game, c, loss, event, source.action)
            from girlframe.services.m3_battle import synchronize as sync_battle

            action = self.game.action(c, source.action)
            sync_battle(self.game, c, action, event, viewer, key)
            return dict(id=identity, game_revision=load_state(c, self.store.campaign_id).revision)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.collateral_applied",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    choice=choice.model_dump(mode="json"),
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
